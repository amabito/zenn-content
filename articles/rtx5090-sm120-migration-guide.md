---
title: "RTX 5090 sm_120移行ガイド：Blackwell対応の全手順"
emoji: "⚡"
type: "tech"
topics: ["RTX5090", "CUDA", "GPU", "Blackwell", "sm120"]
published: true
---

# 結論から言う

**RTX 5090（sm_120, Blackwell）はsm_89（Ada）からアーキテクチャが大きく変わり、既存のCUDAコードは「動くが最適ではない」状態になる。** 移行にはビルド設定の変更と、一部のカーネル最適化が必要。

**対象読者:**
- RTX 5090を購入した/購入予定のCUDA開発者
- sm_89（RTX 4090）からの移行を考えている人
- Blackwellアーキテクチャの変更点を知りたい人

**この記事で得られること:**
- sm_120の主要な変更点
- 移行時に必要な作業リスト
- 実測ベンチマーク比較

---

## sm_120（Blackwell）の主要変更点

### アーキテクチャ比較

| 項目 | sm_89 (Ada/RTX 4090) | sm_120 (Blackwell/RTX 5090) |
|------|----------------------|----------------------------|
| CUDA Cores | 16,384 | 21,760 |
| VRAM | 24GB GDDR6X | 32GB GDDR7 |
| メモリ帯域 | 1,008 GB/s | 1,792 GB/s |
| L2キャッシュ | 72MB | 128MB |
| TDP | 450W | 575W |
| Compute Capability | 8.9 | 12.0 |

### 注目すべき変更

**1. メモリ帯域が1.8倍**

メモリバウンドなカーネルが大幅に高速化する。sm_89で帯域がボトルネックだったカーネルは、コード変更なしで恩恵を受ける。

**2. L2キャッシュが128MBに拡大**

ワーキングセットがL2に収まるケースが増える。特にソート処理やルックアップテーブルを多用するカーネルで効果が大きい。

**3. Compute Capabilityが8.9→12.0に跳躍**

9.0を飛ばして12.0。これはアーキテクチャの世代が大きく変わったことを意味する。PTXレベルでの新命令が追加されている。

---

## 移行作業リスト

各作業の難易度と所要時間の目安:

| 作業 | 難易度 | 所要時間 | 必須度 |
|------|--------|---------|--------|
| CUDA Toolkit更新 | 低 | 30分 | **必須** |
| ビルドターゲット追加 | 低 | 5-10分 | **必須** |
| 後方互換ビルド設定 | 低 | 5分 | **必須** |
| ブロックサイズ再チューニング | 中 | 2-4時間 | 推奨 |
| メモリアクセス見直し | 高 | 1-2日 | 推奨 |
| Occupancy確認 | 中 | 1-2時間 | 推奨 |

**トータル:** 最小45分（必須のみ）、最大3日（推奨含む全実施）

### 必須（これをやらないと動かない/遅い）

#### 1. CUDA Toolkitを12.8以降に更新

sm_120はCUDA 12.8以降でのみサポート。12.7以前では`Unsupported gpu architecture`エラー。

```bash
nvcc --version
# release 12.8 以降であること
```

#### 2. ビルドターゲットにsm_120を追加

```bash
# 環境変数
set TORCH_CUDA_ARCH_LIST=12.0

# CMakeの場合
cmake -DCMAKE_CUDA_ARCHITECTURES=120 ..

# setup.pyの場合
import os
os.environ["TORCH_CUDA_ARCH_LIST"] = "12.0"
```

:::message alert
sm_120を指定しないと、sm_89向けバイナリがJITコンパイルで実行される。初回起動が遅くなり、最適化も効かない。必ず明示指定する。
:::

#### 3. 後方互換ビルド（4090と5090の両対応）

```bash
set TORCH_CUDA_ARCH_LIST=8.9;12.0
```

バイナリサイズは増えるが、両方のGPUで最適なコードが実行される。

---

### 推奨（パフォーマンス最適化）

#### 4. ブロックサイズの再チューニング

sm_120ではSMあたりのレジスタ数とスレッド数の上限が変わっている。sm_89で最適だったブロックサイズがsm_120では最適でない場合がある。

```python
# 自動チューニングの例
for block_size in [128, 256, 512, 1024]:
    time = benchmark_kernel(block_size)
    print(f"Block size {block_size}: {time:.3f} ms")
```

実測では、sm_89で256が最適だったカーネルがsm_120では512が最適だったケースがある。

#### 5. メモリアクセスパターンの見直し

メモリ帯域が1.8倍になったことで、コンピュートバウンドだったカーネルがメモリバウンドに変わる場合がある（逆も然り）。

Nsight Computeでボトルネック分析を再実行すること。

```bash
ncu --set full ./your_cuda_app
```

#### 6. Occupancyの確認

```python
import torch

props = torch.cuda.get_device_properties(0)
print(f"Max threads per SM: {props.max_threads_per_multi_processor}")
print(f"SM count: {props.multi_processor_count}")
print(f"Max shared memory per SM: {props.max_shared_memory_per_multiprocessor}")
```

---

## 実測ベンチマーク

### 測定環境

| 項目 | 詳細 |
|------|------|
| OS | Windows 11 Pro (23H2) |
| CPU | AMD Ryzen 9 9950X3D |
| CUDA Toolkit | 12.8 |
| PyTorch | 2.8.0+cu128 |
| ドライバ | 591.74 (Game Ready) |
| 測定ツール | 自作3DGSラスタライザ (HyperRasterizer v1.2) |
| 測定方法 | 100回実行の平均値（ウォームアップ10回除外） |
| 解像度 | 800x800 |

自作の3DGSラスタライザで比較した結果:

### レンダリング性能

| シーン | RTX 4090 (sm_89) | RTX 5090 (sm_120) | 高速化率 |
|--------|-------------------|---------------------|---------|
| 小規模（100K点） | 650 FPS | 1,200 FPS | **1.85x** |
| 中規模（500K点） | 280 FPS | 580 FPS | **2.07x** |
| 大規模（2M点） | 85 FPS | 195 FPS | **2.29x** |

**大規模シーンほど高速化率が高い。** メモリ帯域とL2キャッシュの拡大が効いている。

### ソート処理

| 要素数 | RTX 4090 | RTX 5090 | 高速化率 |
|--------|----------|----------|---------|
| 100K | 0.12 ms | 0.07 ms | 1.71x |
| 1M | 0.85 ms | 0.41 ms | 2.07x |
| 10M | 7.2 ms | 3.1 ms | 2.32x |

### 学習（3DGS Training）

| 指標 | RTX 4090 | RTX 5090 | 改善率 |
|------|----------|----------|--------|
| 1イテレーション | 42 ms | 21 ms | 2.0x |
| 30K iterations | 21分 | 10.5分 | 2.0x |
| VRAM使用量 | 18GB / 24GB | 18GB / 32GB | 余裕14GB |

---

## 移行時のハマりポイント

### 1. PTXの互換性

sm_120向けにコンパイルしたPTXはsm_89では動かない。配布バイナリを作る場合は両方のアーキテクチャを含める必要がある。

### 2. サードパーティライブラリの対応

2026年1月時点で、一部のCUDAライブラリはsm_120に未対応。事前に確認すること:

| ライブラリ | sm_120対応 |
|-----------|-----------|
| cuBLAS | 対応済み |
| cuDNN | 対応済み |
| Thrust | 対応済み |
| CUB | 対応済み |
| CUTLASS | 一部対応 |

### 3. 電力と温度

TDP 575Wは従来の450Wから大幅増。電源と冷却の見直しが必要。850W以上の電源を推奨。

---

## まとめ

| 作業 | 必須度 | 効果 |
|------|--------|------|
| CUDA 12.8以降に更新 | **必須** | sm_120サポート |
| ビルドターゲット追加 | **必須** | 最適バイナリ生成 |
| ブロックサイズ再チューニング | 推奨 | 5-20%改善 |
| メモリアクセス見直し | 推奨 | ボトルネック変化への対応 |
| Occupancy確認 | 推奨 | 並列度の最適化 |

**RTX 5090の移行は「ビルド設定変更」が必須、「カーネル最適化」が推奨。** コード変更なしでも1.8-2.3倍の高速化が得られるが、最適化すればさらに伸びる。

---

## 関連記事

- [無料] [RTX 5090 CUDA最適化ガイド](https://zenn.dev/amabito/articles/rtx5090-cuda-optimization) - 最適化手法の詳細
- [有料] [RTX 5090ベンチマーク詳細](https://zenn.dev/amabito/articles/rtx5090-cuda-optimization-paid) - 全テスト結果
- [無料] [CUDA warp同期の罠](https://zenn.dev/amabito/articles/cuda-warp-sync-trap) - warp関連の注意点
- [無料] [Windows CUDA環境構築](https://zenn.dev/amabito/articles/windows-cuda-pytorch-setup-2026) - 環境構築から始める

---

ご質問・ご相談はコメント欄へ。
