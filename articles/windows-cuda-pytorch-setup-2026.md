---
title: "Windows×CUDA×PyTorch環境構築完全ガイド2026：RTX 5090対応"
emoji: "🔧"
type: "tech"
topics: ["CUDA", "PyTorch", "Windows", "GPU", "RTX5090"]
published: true
published_at: "2026-01-29 07:00"
---

# 結論から言う

**Windows 11 + CUDA 12.8 + PyTorch 2.8.0 + MSVC 14.44が2026年1月時点の最適解。** PyTorch 2.9.0以降はMSVC衝突が発生するため、2.8.0で固定する。

この記事では、RTX 5090（Blackwell, sm_120）環境でCUDA開発を始めるための全手順を解説する。

**対象読者:**
- WindowsでCUDA開発を始めたい人
- RTX 5090/50シリーズを購入した人
- PyTorch + CUDA拡張をビルドしたい人

**この記事で得られること:**
- 環境構築の全手順（コピペで完了）
- PyTorch 2.9.0で発生するMSVC衝突の回避方法
- sm_120対応のビルド設定

---

## 前提環境

| 項目 | バージョン |
|------|-----------|
| OS | Windows 11 |
| GPU | NVIDIA GeForce RTX 5090 (32GB VRAM) |
| CPU | AMD Ryzen 9 9950X3D |
| Python | 3.11.9 |
| CUDA Toolkit | 12.8 |
| PyTorch | 2.8.0+cu128 |
| MSVC | 14.44 (VS Build Tools 2022) |
| ドライバ | 591.74 |

---

## Step 1: NVIDIAドライバのインストール

最新のGame Ready DriverまたはStudio Driverをインストール。

RTX 5090の場合、**591.x以降**が必要。

```bash
nvidia-smi
```

出力で`CUDA Version: 12.8`と表示されればOK。

:::message
ドライバのCUDAバージョンは「対応可能な最大バージョン」を示す。実際に使うCUDA Toolkitのバージョンとは異なる。ドライバ ≧ Toolkit のバージョン関係を守ること。
:::

---

## Step 2: CUDA Toolkit 12.8のインストール

[NVIDIA CUDA Toolkit Archive](https://developer.nvidia.com/cuda-toolkit-archive)からCUDA 12.8をダウンロード。

**インストール時の注意:**

1. **カスタムインストール**を選択
2. **Visual Studio Integration**にチェック
3. インストール先はデフォルト（`C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8`）

```bash
nvcc --version
# Cuda compilation tools, release 12.8
```

### 環境変数の確認

以下がPATHに含まれていること:

```
C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8\bin
C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8\libnvvp
```

---

## Step 3: Visual Studio Build Tools 2022

PyTorchのCUDA拡張ビルドにはMSVCコンパイラが必要。

[Visual Studio Build Tools 2022](https://visualstudio.microsoft.com/visual-cpp-build-tools/)をインストール。

**必須コンポーネント:**
- MSVC v143 - VS 2022 C++ x64/x86 build tools (v14.44)
- Windows 11 SDK
- C++ CMake tools for Windows

```bash
cl
# Microsoft (R) C/C++ Optimizing Compiler Version 19.44.xxxxx for x64
```

:::message alert
**MSVCバージョン管理が重要。** v14.44を使うこと。これより新しいバージョンではPyTorch 2.8.0のCUDA拡張ビルドで問題が発生する場合がある。Visual Studio Installerで特定バージョンを選択できる。
:::

---

## Step 4: Pythonセットアップ

Python 3.11.xを推奨。3.12はライブラリ互換性問題が残る。

```bash
# condaの場合
conda create -n cuda-dev python=3.11.9
conda activate cuda-dev

# venvの場合
python -m venv cuda-dev
cuda-dev\Scripts\activate
```

---

## Step 5: PyTorch 2.8.0のインストール

**ここが最大の落とし穴。**

```bash
pip install torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cu128
```

### 動作確認

```python
import torch

print(f"PyTorch: {torch.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")
print(f"CUDA version: {torch.version.cuda}")
print(f"GPU: {torch.cuda.get_device_name(0)}")
print(f"VRAM: {torch.cuda.get_device_properties(0).total_mem / 1024**3:.1f} GB")
```

期待される出力:

```
PyTorch: 2.8.0+cu128
CUDA available: True
CUDA version: 12.8
GPU: NVIDIA GeForce RTX 5090
VRAM: 32.0 GB
```

---

## なぜPyTorch 2.8.0なのか

### PyTorch 2.9.0以降のMSVC衝突問題

PyTorch 2.9.0以降で、CUDA拡張のビルド時にMSVCとの互換性問題が発生する。

**症状:**
```
error C2039: 'max_align_t': is not a member of 'std'
```
または
```
fatal error C1189: #error: "C++ versions less than C++17 are not supported."
```

**原因:** PyTorch 2.9.0がC++17を要求する一方、CUDAのnvccが渡すフラグとMSVCの解釈が衝突する。

**解決策:** PyTorch 2.8.0で固定する。2026年1月時点で未修正。

:::message
PyTorchのバージョンを上げたい衝動に駆られるが、CUDA拡張のビルドが必要なら2.8.0が安全。「最新」は「最適」ではない。
:::

---

## Step 6: CUDA拡張のビルド確認

環境が正しく構築されたか確認する。

```python
import torch
from torch.utils.cpp_extension import load_inline

cuda_source = """
__global__ void add_kernel(float* a, float* b, float* c, int n) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx < n) c[idx] = a[idx] + b[idx];
}

torch::Tensor add_cuda(torch::Tensor a, torch::Tensor b) {
    auto c = torch::empty_like(a);
    int n = a.numel();
    int threads = 256;
    int blocks = (n + threads - 1) / threads;
    add_kernel<<<blocks, threads>>>(
        a.data_ptr<float>(), b.data_ptr<float>(), c.data_ptr<float>(), n
    );
    return c;
}
"""

cpp_source = "torch::Tensor add_cuda(torch::Tensor a, torch::Tensor b);"

module = load_inline(
    name="test_cuda",
    cpp_sources=cpp_source,
    cuda_sources=cuda_source,
    functions=["add_cuda"],
    verbose=True,
)

a = torch.randn(1000, device="cuda")
b = torch.randn(1000, device="cuda")
c = module.add_cuda(a, b)

print(f"Result matches: {torch.allclose(c, a + b)}")
print("CUDA extension build: SUCCESS")
```

`SUCCESS`と表示されれば環境構築完了。

---

## sm_120（Blackwell）のビルド設定

RTX 5090はsm_120アーキテクチャ。CUDA拡張ビルド時に明示的に指定する。

```bash
# 環境変数で設定
set TORCH_CUDA_ARCH_LIST=12.0

# 複数GPUサポート
set TORCH_CUDA_ARCH_LIST=8.9;12.0
```

```python
# setup.pyの場合
import os
os.environ["TORCH_CUDA_ARCH_LIST"] = "12.0"
```

:::message
sm_120を指定しないとsm_89向けコードがJITコンパイルされ、初回実行が遅くなる。明示指定を推奨。
:::

---

## トラブルシューティング

### `nvcc fatal : Unsupported gpu architecture 'compute_120'`

CUDA Toolkit 12.8未満を使っている。12.8以降にアップデート。

### `torch.cuda.is_available()` が `False`

1. NVIDIAドライバ確認（`nvidia-smi`）
2. PyTorchがCUDA版か確認（`torch.version.cuda`がNoneでないこと）
3. `pip install torch`はCPU版。`--index-url`を指定してインストールし直す

### ビルド時に `cl.exe not found`

Developer Command Promptを使うか、MSVCのパスをPATHに追加。

### `RuntimeError: CUDA error: no kernel image is available`

sm_120向けにビルドされていない。`TORCH_CUDA_ARCH_LIST=12.0`を設定してリビルド。

---

## まとめ

| 項目 | 推奨バージョン |
|------|--------------|
| CUDA Toolkit | **12.8** |
| PyTorch | **2.8.0+cu128** |
| MSVC | **14.44** |
| Python | **3.11.x** |
| アーキテクチャ | `TORCH_CUDA_ARCH_LIST=12.0` |

**最重要:** PyTorchは最新版ではなく2.8.0。CUDA拡張ビルドが安定する唯一の組み合わせ。

---

## 関連記事

- [無料] [RTX 5090 CUDA最適化ガイド](https://zenn.dev/amabito/articles/rtx5090-cuda-optimization) - 性能を引き出す
- [無料] [CUDA最適化入門](https://zenn.dev/amabito/articles/cuda-optimization-basics) - CUDA開発の基礎
- [無料] [CUDAメモリ管理の罠](https://zenn.dev/amabito/articles/cuda-memory-management) - メモリ関連の注意点
- [有料] [RTX 5090ベンチマーク詳細](https://zenn.dev/amabito/articles/rtx5090-cuda-optimization-paid) - 実測データ集

---

ご質問・ご相談はコメント欄へ。
