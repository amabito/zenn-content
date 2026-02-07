---
title: "RTX 5090 (sm_120) CUDA移行の実体験：Blackwellで変わったこと・変わらないこと"
emoji: "⚡"
type: "tech"
topics: ["RTX5090", "CUDA", "Blackwell", "GPU"]
published: false
---

## はじめに

2026年1月、RTX 5090（32GB）を購入し、Ryzen 9 9950X3Dと組み合わせた開発環境を構築しました。

RTX 4090（sm_89）からRTX 5090（sm_120）への移行で、**何が変わって、何が変わらなかったのか**。

3DGS（3D Gaussian Splatting）のカスタムCUDAカーネル実装を通じた、リアルな移行体験をまとめます。

## 環境スペック

### ハードウェア

- **CPU**: AMD Ryzen 9 9950X3D（16コア/32スレッド）
- **GPU**: NVIDIA GeForce RTX 5090 32GB（sm_120, Blackwellアーキテクチャ）
- **RAM**: 128GB DDR5-6000
- **OS**: Windows 11 Pro（WSL2 Ubuntu 24.04併用）

### ソフトウェア

- **CUDA**: 12.8
- **Driver**: 591.74（WSL2対応版）
- **Python**: 3.11.9
- **PyTorch**: 2.8.0+cu128
- **MSVC**: 14.44（Visual Studio 2022 Build Tools）

## RTX 5090 (sm_120) の基本スペック

### 従来モデルとの比較

| 項目 | RTX 4090 (sm_89) | RTX 5090 (sm_120) | 変化率 |
|------|------------------|-------------------|--------|
| CUDAコア | 16,384 | 21,760 | +33% |
| Tensorコア | 512 (Gen 4) | 680 (Gen 5) | +33% |
| VRAM | 24GB GDDR6X | 32GB GDDR7 | +33% |
| メモリ帯域幅 | 1,008 GB/s | 1,792 GB/s | +78% |
| TDP | 450W | 575W | +28% |
| アーキテクチャ | Ada Lovelace | Blackwell | - |

**最大の変化点**: VRAMが32GBになったことで、大規模な3DGSシーンのトレーニングが可能に。

## 変わったこと

### 1. Compute Capability: sm_89 → sm_120

**影響**: カーネルの再コンパイルが**必須**。

```bash
# RTX 4090用
nvcc -arch=sm_89 kernel.cu

# RTX 5090用
nvcc -arch=sm_120 kernel.cu
```

PyTorchの`setup.py`を修正：

```python
# Before (RTX 4090)
extra_compile_args = {
    "nvcc": ["-arch=sm_89"]
}

# After (RTX 5090)
extra_compile_args = {
    "nvcc": ["-arch=sm_120"]
}
```

**互換性**: sm_89でコンパイルしたバイナリはsm_120で実行できない。逆も同様。

### 2. 新しい命令セット

Blackwellでは、以下の新命令が追加されています：

- **FP4/FP6サポート**: AI推論の低精度演算
- **改良されたTensorコア**: FP8とFP16のネイティブサポート
- **非同期バリア**: `__syncthreads()`の高速化

ただし、**これらは明示的に使わない限り自動適用されない**。

既存のCUDAコードは、再コンパイルするだけでパフォーマンスが向上する場合もあります（コンパイラの最適化による）。

### 3. Occupancy特性の変化

`__launch_bounds__`で指定する最適値が変わる可能性があります。

**RTX 4090での最適値**:

```cpp
__global__ void __launch_bounds__(256, 2)
kernel(...) {
    // ...
}
```

**RTX 5090での再検証が必要**:

```bash
# Occupancy計算
nvcc --ptxas-options=-v kernel.cu

# 出力例
ptxas info : Used 64 registers, 12288 bytes smem, 384 bytes cmem[0]
ptxas info : Compiling entry function 'kernel' for 'sm_120'
ptxas info : Function properties for kernel
    0 bytes stack frame, 0 bytes spill stores, 0 bytes spill loads
```

実際の計測では、**RTX 5090では`__launch_bounds__(256, 4)`の方が高速**なケースもありました（CUDAコアが33%増えたため）。

### 4. メモリ帯域幅の劇的向上

1,792 GB/sのメモリ帯域幅は、メモリバウンドなカーネルで大きな影響があります。

**3DGS Rasterization Forward Kernel**（メモリバウンド）:

- RTX 4090: 81 it/s
- RTX 5090: 84 it/s（+3.7%）

**予想より小さい理由**: ボトルネックが帯域幅ではなく、Compute（演算）に移行したため。

### 5. 32GB VRAMの威力

**RTX 4090での制約**:

```python
# バッチサイズを小さくする必要があった
batch_size = 4
max_sh_degree = 3  # SH次数を下げる
```

**RTX 5090では余裕**:

```python
batch_size = 8  # 2倍
max_sh_degree = 4  # 高次球面調和関数も可能
```

3DGSの大規模シーン（1M+ Gaussians）のトレーニングが、OOM（Out of Memory）エラーなしで実行できるようになりました。

## 変わらなかったこと

### 1. 基本的なCUDAプログラミングモデル

**Warp size**: 依然として32スレッド。

```cpp
// RTX 4090でも5090でも同じ
int lane_id = threadIdx.x % 32;
__syncwarp();
```

**Shared memory limit**: 依然として48KB/ブロック（静的確保の場合）。

```cpp
// 48KB制限は変わらず
__shared__ float buffer[12288];  // 48KB = 12288 floats
```

この制限を超えるとコンパイルエラー：

```
ptxas error: Entry function 'kernel' uses too much shared data (0xcc20 bytes, 0xc000 max)
```

### 2. カーネルコードの互換性

**sm_89で書いたコードは、再コンパイルだけでsm_120で動く**。

例：HyperRasterizerの1万行以上のCUDAコード。

```cpp
// このコードは何も変更不要
__global__ void rasterize_forward(
    const int P,
    const float2* means2D,
    const float* opacities,
    // ... 50個以上の引数
) {
    // Warp-level処理
    const int lane_id = threadIdx.x % 32;

    // Shared memory
    __shared__ float3 shared_buffer[256];

    // Atomic operations
    atomicAdd(&counter, 1);

    // 全て問題なく動作
}
```

**変更が必要だったのは、`setup.py`のアーキテクチャ指定のみ**。

### 3. PyTorchとの統合

PyTorch 2.8.0は、sm_120をネイティブサポート。

```python
import torch

print(torch.cuda.is_available())        # True
print(torch.cuda.get_device_name(0))    # NVIDIA GeForce RTX 5090
print(torch.cuda.get_device_capability(0))  # (12, 0) = sm_120

# カスタム拡張も問題なく動作
from hyper_rasterizer import _C as _C
```

**既存のPyTorch拡張コードは、そのまま動作**。

### 4. デバッグツール

`cuda-gdb`, `cuda-memcheck`, `compute-sanitizer`は、すべてsm_120をサポート。

```bash
# Memory leak検出
compute-sanitizer --tool memcheck python train.py

# Race condition検出
compute-sanitizer --tool racecheck python train.py
```

使い方は、RTX 4090と全く同じです。

## 移行チェックリスト

RTX 4090 → RTX 5090への移行で、実際に行った作業：

### 必須作業

- [x] CUDA 12.8以上にアップデート
- [x] PyTorch 2.8以上にアップデート（sm_120サポート）
- [x] NVIDIAドライバを最新版に更新（591.74以上）
- [x] `setup.py`の`-arch=sm_89`を`-arch=sm_120`に変更
- [x] 全カスタムカーネルを再コンパイル

### 推奨作業

- [x] `__launch_bounds__`の再検証（Occupancy最適化）
- [x] メモリ使用量の再測定（32GB活用の余地）
- [x] ベンチマーク実行（パフォーマンス確認）
- [ ] Blackwell固有最適化の適用（FP4/FP6等）— 未実施

### 不要だった作業

- ❌ カーネルコードの書き換え（再コンパイルのみでOK）
- ❌ PyTorchコードの変更
- ❌ データローダーの変更
- ❌ トレーニングスクリプトの変更

## 実測ベンチマーク

### 3DGS Rasterization（HyperRasterizer）

**設定**: 解像度1920×1080, 約500K Gaussians, SH degree 3

| カーネル | RTX 4090 (sm_89) | RTX 5090 (sm_120) | 速度向上 |
|---------|------------------|-------------------|----------|
| Forward | 81 it/s | 84 it/s | +3.7% |
| Backward | 78 it/s | 86 it/s | +10.3% |
| Full (forward+backward) | 43 it/s | 47 it/s | +9.3% |

**Backward kernelの向上が大きい理由**: Gradient計算は演算バウンド。CUDAコア数+33%の恩恵を受けた。

### 3DGS Training（300K Gaussians）

**設定**: Mip-NeRF 360 dataset, "garden" scene

| フェーズ | RTX 4090 | RTX 5090 | 速度向上 |
|---------|----------|----------|----------|
| Iteration (it/s) | 43.2 | 47.1 | +9.0% |
| Training time (30K it) | 11.6 min | 10.6 min | -8.6% |
| VRAM usage | 18.3 GB | 19.1 GB | +4.4% |

**VRAM使用量が増えた理由**: バッチサイズを4→8に増やしたため。

### Large Scene Training（1.2M Gaussians）

**設定**: カスタム大規模シーン, 360°カメラ

| 項目 | RTX 4090 | RTX 5090 |
|------|----------|----------|
| 実行可否 | ❌ OOM | ✅ 成功 |
| VRAM usage | N/A | 28.7 GB |
| Iteration speed | N/A | 12.3 it/s |

**これがRTX 5090の真価**: 24GBでは不可能だったシーンがトレーニング可能に。

## ハマったポイント

### 1. MSVC 14.44 との互換性問題

**症状**:

```
error: 'cusparseGetErrorString': redefinition; different type modifiers
```

**原因**: PyTorch 2.8.0 + CUDA 12.8 + MSVC 14.44の組み合わせで発生。

**解決**: WSL2でビルド（詳細は別記事参照）。

### 2. `__launch_bounds__`の最適値変更

**症状**: RTX 4090と同じ設定では、Occupancyが低い。

**対策**: Nsight Computeでプロファイリング。

```bash
ncu --set full -o profile python train.py
```

結果を見て、`__launch_bounds__(256, 4)`に変更→10%高速化。

### 3. Driver Timeout Detection (TDR)

**症状**: 長時間カーネル（>2秒）でWindowsがGPUリセット。

**対策**: レジストリでTDRを無効化（開発環境のみ推奨）。

```
HKEY_LOCAL_MACHINE\System\CurrentControlSet\Control\GraphicsDrivers
TdrDelay = 60 (秒)
TdrLevel = 0 (無効化)
```

## Blackwell固有最適化（今後の課題）

まだ手を付けていない最適化領域：

### 1. FP8 Tensor Cores

現在はFP16/FP32を使用。FP8に移行すれば、さらに高速化の余地。

```cpp
// 現在（FP16）
__half* data;

// 今後（FP8）
__nv_fp8_e4m3* data;  // 要CUDA 12.8+
```

### 2. 非同期バリア

`__syncthreads()`の高速版が利用可能。

```cpp
// 従来
__syncthreads();

// Blackwell最適化版
__syncthreads_async();  // 要検証
```

### 3. Warp Matrix Operations

新しいWMMA命令セット（Tensor Core活用）。

```cpp
#include <mma.h>
using namespace nvcuda::wmma;

// FP8 WMMA（Blackwell専用）
fragment<...> a, b, c;
load_matrix_sync(a, ...);
mma_sync(c, a, b, c);
```

## まとめ

### 変わったこと

1. **Compute Capability**: sm_89 → sm_120（再コンパイル必須）
2. **VRAM**: 24GB → 32GB（大規模シーン対応）
3. **メモリ帯域幅**: +78%（演算バウンドに移行）
4. **新命令セット**: FP4/FP6, 改良Tensor Core（明示的利用が必要）
5. **Occupancy最適化**: `__launch_bounds__`の調整

### 変わらなかったこと

1. **Warp size**: 32スレッド
2. **Shared memory制限**: 48KB/block
3. **基本的なCUDAコード**: 再コンパイルのみでOK
4. **PyTorch統合**: そのまま動作
5. **デバッグツール**: 使い方は同じ

### 速度向上の実測

- Forward kernel: +3.7%
- Backward kernel: +10.3%
- Full training: +9.3%

**期待値（+33% CUDAコア）より低い理由**: メモリバウンドから演算バウンドへの移行で、理論値通りの向上は得られない。

### 32GB VRAMの価値

**これが最大のメリット**。1M+ Gaussiansの大規模シーンが、OOMなしでトレーニング可能。

研究・開発用途では、RTX 4090からの乗り換え価値は十分にあります。

### 移行の容易さ

**コード変更はほぼ不要**。`setup.py`のアーキテクチャ指定を変えて再コンパイルするだけ。

PyTorch 2.8以上を使っていれば、1時間以内に移行完了します。

---

**参考リンク**:
- [NVIDIA Blackwell Architecture Whitepaper](https://www.nvidia.com/en-us/data-center/technologies/blackwell-architecture/)
- [CUDA 12.8 Release Notes](https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/index.html)
- [PyTorch 2.8.0 Release](https://github.com/pytorch/pytorch/releases/tag/v2.8.0)

RTX 5090は、CUDAカーネル開発者にとって**順当な進化**でした。劇的な変化はないが、確実に速く、大きなシーンを扱える。

この安心感が、開発環境としての価値だと感じています。
