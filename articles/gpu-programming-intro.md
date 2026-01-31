---
title: "GPUプログラミング入門：CPUより100倍速い世界への第一歩"
emoji: "⚡"
type: "tech"
topics: ["GPU", "CUDA", "Python", "NVIDIA", "高速化"]
published: true
published_at: "2026-02-12 21:00"
---

# 結論から言う

**GPUを使えば、CPUの100倍以上速くなる処理がある。**

「GPUって機械学習用でしょ？」

違う。**画像処理、数値計算、シミュレーション**...CPUでは数時間かかる処理が、GPUなら数分で終わる。

この記事では、GPUプログラミングの基礎を、Pythonの知識だけで理解できるように解説する。

**この記事で得られること:**
- GPUが速い理由
- Pythonから GPUを使う方法
- 実際に100倍高速化するデモ

---

# なぜGPUは速いのか

## CPUとGPUの違い

```
CPU（頭脳派）:
├── コア数: 8-24個
├── 1コアの性能: 非常に高い
├── 得意: 複雑な分岐処理、逐次処理
└── 例え: 天才が1人で計算

GPU（並列派）:
├── コア数: 数千〜数万個
├── 1コアの性能: 低い
├── 得意: 単純な計算を大量に並列実行
└── 例え: 小学生1万人で計算
```

## 具体例

```
問題: 100万個の数字を2倍にする

CPU:
for i in range(1000000):
    result[i] = data[i] * 2
→ 1個ずつ処理 → 遅い

GPU:
全要素を同時に処理
→ 100万個を一瞬で処理 → 速い
```

**単純な計算を大量に行う = GPUの得意分野**

---

# PythonからGPUを使う方法

## 選択肢

| ライブラリ | 難易度 | 速度 | 用途 |
|-----------|--------|------|------|
| **NumPy (CPU)** | 低 | 基準 | 比較用 |
| **CuPy** | 低 | 50-100x | NumPy互換でGPU |
| **PyTorch** | 中 | 50-100x | 機械学習向け |
| **Numba** | 中 | 10-50x | 既存コードの高速化 |
| **CUDA (C++)** | 高 | 最速 | 極限の最適化 |

**おすすめ: CuPy（NumPyを知っていれば即使える）**

---

# CuPyで体験する100倍高速化

## インストール

```bash
# CUDA 12.x の場合
pip install cupy-cuda12x

# CUDA 11.x の場合
pip install cupy-cuda11x
```

## NumPy vs CuPy 比較

```python
import numpy as np
import cupy as cp
import time

# 1億個の配列
size = 100_000_000

# --- NumPy (CPU) ---
data_cpu = np.random.randn(size).astype(np.float32)

start = time.time()
result_cpu = np.sin(data_cpu) + np.cos(data_cpu)
cpu_time = time.time() - start
print(f"CPU: {cpu_time:.3f}秒")

# --- CuPy (GPU) ---
data_gpu = cp.random.randn(size).astype(cp.float32)

# ウォームアップ（初回はコンパイルが入る）
_ = cp.sin(data_gpu) + cp.cos(data_gpu)
cp.cuda.Stream.null.synchronize()

start = time.time()
result_gpu = cp.sin(data_gpu) + cp.cos(data_gpu)
cp.cuda.Stream.null.synchronize()
gpu_time = time.time() - start
print(f"GPU: {gpu_time:.3f}秒")

print(f"高速化: {cpu_time / gpu_time:.1f}倍")
```

## 実行結果（RTX 3080の例）

```
CPU: 2.340秒
GPU: 0.023秒
高速化: 101.7倍
```

**コードはほぼ同じ。`np` を `cp` に変えただけで100倍速い。**

---

# 実践例: 画像処理

## ガウシアンブラー（ぼかし処理）

```python
import cupy as cp
from cupyx.scipy import ndimage
import numpy as np
from scipy import ndimage as ndimage_cpu
from PIL import Image
import time

# 画像読み込み（4K画像を想定）
img = np.array(Image.open("large_image.jpg")).astype(np.float32)

# --- CPU版 ---
start = time.time()
blurred_cpu = ndimage_cpu.gaussian_filter(img, sigma=5)
cpu_time = time.time() - start
print(f"CPU: {cpu_time:.3f}秒")

# --- GPU版 ---
img_gpu = cp.asarray(img)

start = time.time()
blurred_gpu = ndimage.gaussian_filter(img_gpu, sigma=5)
cp.cuda.Stream.null.synchronize()
gpu_time = time.time() - start
print(f"GPU: {gpu_time:.3f}秒")

print(f"高速化: {cpu_time / gpu_time:.1f}倍")
```

## 結果

```
CPU: 3.2秒
GPU: 0.05秒
高速化: 64倍
```

---

# GPUが効く処理、効かない処理

## 効く処理 ✅

| 処理 | 理由 |
|------|------|
| 行列演算 | 大量の並列計算 |
| 画像処理 | ピクセル単位で並列化可能 |
| 機械学習 | 行列演算の塊 |
| 物理シミュレーション | 粒子/格子点を並列計算 |
| 暗号化/ハッシュ | 同じ計算を大量に |

## 効かない処理 ❌

| 処理 | 理由 |
|------|------|
| 逐次処理 | 前の結果に依存 |
| 複雑な分岐 | GPUは分岐が苦手 |
| 少量データ | 転送オーバーヘッドの方が大きい |
| I/O待ち | ディスク/ネットワーク律速 |

## 判断基準

```
データ数 > 10万 かつ 単純な計算の繰り返し
→ GPUを検討する価値あり

データ数 < 1万 または 複雑な条件分岐
→ CPUのままでOK
```

---

# よくある落とし穴

## 1. データ転送を忘れる

```python
# ❌ 毎回転送（遅い）
for i in range(100):
    data_gpu = cp.asarray(data_cpu)  # CPU→GPU転送
    result = cp.sum(data_gpu)
    result_cpu = cp.asnumpy(result)  # GPU→CPU転送

# ✅ 最初と最後だけ転送（速い）
data_gpu = cp.asarray(data_cpu)  # 1回だけ転送
for i in range(100):
    result = cp.sum(data_gpu)      # GPU内で計算
result_cpu = cp.asnumpy(result)    # 1回だけ転送
```

## 2. 同期を忘れる

```python
# ❌ 計測が不正確
start = time.time()
result = cp.sin(data_gpu)
gpu_time = time.time() - start  # GPU計算が終わってない！

# ✅ 同期してから計測
start = time.time()
result = cp.sin(data_gpu)
cp.cuda.Stream.null.synchronize()  # GPU計算の完了を待つ
gpu_time = time.time() - start
```

## 3. メモリ不足

```python
# GPUメモリは限られている（RTX 3080で10GB）
# 大きすぎる配列は分割処理

# ❌ 一度に処理（メモリ不足）
huge_array = cp.random.randn(1_000_000_000)  # 約4GB

# ✅ 分割処理
chunk_size = 100_000_000
for i in range(0, 1_000_000_000, chunk_size):
    chunk = cp.random.randn(chunk_size)
    # 処理...
    del chunk  # 明示的に解放
    cp.get_default_memory_pool().free_all_blocks()
```

---

# 次のステップ

## Level 1: CuPy で十分

NumPy互換の処理をGPUで高速化したいだけなら、CuPyで十分。

## Level 2: PyTorch / JAX

機械学習や自動微分が必要なら、PyTorchやJAXを学ぶ。

## Level 3: CUDA (C++)

極限の性能が必要なら、CUDAでカーネルを自作。

```
CuPy: 手軽に50-100倍
PyTorch: 機械学習に最適化
CUDA: 理論限界まで追い込む
```

:::message alert
**実務でGPUを使いこなしたい方へ**

この記事はLevel 1（CuPy）までの内容です。実務では**メモリ転送の最適化**、**カーネル設計**、**プロファイリング**が性能を10倍左右します。

有料記事では、CuPy→CUDA→実務レベルまでの具体的な最適化テクニックを解説しています:

- メモリコピー最小化で30%高速化する方法
- ブロック/スレッド設計で占有率を最大化
- 共有メモリとL2キャッシュの使い分け
- Nsight Computeでボトルネックを特定する手順

→ [【有料】GPU高速化実践ガイド：CUDA/PyTorchで実務を10倍速にする](https://zenn.dev/amabito/articles/gpu-programming-paid)
:::

---

# まとめ

| 項目 | 内容 |
|------|------|
| GPUの強み | 単純計算を大量に並列実行 |
| 高速化の目安 | 50-100倍（条件次第） |
| おすすめツール | CuPy（NumPy互換） |
| 注意点 | データ転送、同期、メモリ |

**GPUプログラミングは「使える人」と「使えない人」で生産性が桁違い。**

---

# 関連記事

## 次に読むべき記事

**🎯 実務で使いたい方:**
- [【有料】GPU高速化実践ガイド](https://zenn.dev/amabito/articles/gpu-programming-paid) - メモリ最適化、カーネル設計、プロファイリング
- [【有料】RTX 5090ベンチマーク詳細](https://zenn.dev/amabito/articles/rtx5090-cuda-optimization-paid) - 最新GPU実測データ

**📚 無料で深掘り:**
- [RTX 5090 CUDA最適化](https://zenn.dev/amabito/articles/rtx5090-cuda-optimization) - 最新GPU活用
- [CUDAメモリ管理の罠](https://zenn.dev/amabito/articles/cuda-memory-management) - first-frame bugと73GB問題
- [CUDA warp同期の罠](https://zenn.dev/amabito/articles/cuda-warp-sync-trap) - __shfl_xor_syncの落とし穴

**💡 GPU活用事例:**
- [4169FPS達成の3DGSラスタライザ](https://zenn.dev/amabito/articles/hyper-rasterizer-zenn) - GPU活用の実例
