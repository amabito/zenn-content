---
title: "HyperRasterizerでトレーニング：DGRより50%高速"
emoji: "🚀"
type: "tech"
topics: ["CUDA", "3DGS", "PyTorch", "GPU", "機械学習"]
published: true
---

# 結論から言う

**HyperRasterizerをトレーニングに統合した結果、DGRより50%高速で動作した。**

| 指標 | DGR | HyperRasterizer | 差分 |
|------|-----|-----------------|------|
| 速度 | 45-50 it/s | **77 it/s** | **+50%** |
| 商用利用 | ❌ 要契約 | ✅ Apache 2.0 | - |
| ライセンス | Inria/MPG | Apache 2.0 | - |

ただし、統合過程で**3つの致命的なバグ**に遭遇した。この記事ではその原因と解決法を共有する。

**この記事で得られること:**
- HyperRasterizerのトレーニング統合方法
- 遭遇した3つのバグと解決法
- 速度最適化のポイント

---

# HyperRasterizerとは

[HyperRasterizer](https://github.com/amabito/hyper-rasterizer)は、3D Gaussian Splatting用の商用利用可能なCUDAラスタライザ。

```
特徴:
├── Apache 2.0ライセンス（商用OK）
├── 推論: 4169 FPS（DGR比1.45x）
├── Hash-based Forward（ソート60%削減）
└── RTX 5090 (Blackwell) 最適化
```

詳細は前回記事を参照:
→ [HyperRasterizer完全解説：4169 FPS達成の全技術](https://zenn.dev/amabito/articles/hyper-rasterizer-zenn)

---

# トレーニング統合

## 基本的な使い方

```python
from hyper_rasterizer import HyperRasterizer

rasterizer = HyperRasterizer()

# Forward
image, radii, depth = rasterizer.forward(
    means3D=gaussians.get_xyz(),
    scales=gaussians._scaling,      # 重要: 生データを渡す
    rotations=gaussians._rotation,
    opacities=gaussians._opacity,
    shs=gaussians.get_features(),
    camera=camera,
)

# Backward（自動微分）
loss = l1_loss(image, gt_image)
loss.backward()
```

## DGRとの違い

| 項目 | DGR | HyperRasterizer |
|------|-----|-----------------|
| scales入力 | `get_scaling()` (exp済み) | `_scaling` (生データ) |
| opacities入力 | `get_opacity()` (sigmoid済み) | `_opacity` (生データ) |
| rotations入力 | `get_rotation()` (正規化済み) | `_rotation` (生データ) |

**重要**: HyperRasterizerは内部で`exp()`や`sigmoid()`を適用するため、生データを渡す必要がある。

---

# 遭遇した3つのバグ

## Bug 1: Double-Exp Bug（致命的）

### 症状

```
学習開始直後に全Gaussianが消失
勾配がゼロになり、損失が下がらない
```

### 原因

```python
# Python側（DGRの慣習）
scales = gaussians.get_scaling()  # 内部で exp(_scaling) を実行

# CUDA側（HyperRasterizer）
float scale = exp(scales[idx]);   # さらに exp() を適用

# 結果: exp(exp(x)) → 巨大な値 → 画面外にカリング
```

`exp(exp(x))`が発生し、Gaussianのスケールが爆発。全てが画面外にカリングされ、勾配がゼロになった。

### 解決

```python
# ❌ 間違い
scales = gaussians.get_scaling()

# ✅ 正解: 生データを渡す
scales = gaussians._scaling
```

### 教訓

**ラスタライザが内部で何をしているか確認する。** DGRとHyperRasterizerでは入力の期待値が異なる。

---

## Bug 2: LPIPS速度低下

### 症状

```
77 it/s → 1.5 it/s に急激に低下
GPUメモリ使用量も増加
```

### 原因

```python
# 毎イテレーションVGG特徴抽出が走る
loss = l1_loss(image, gt) + 0.1 * lpips_loss(image, gt)
```

LPIPSはVGGネットワークで特徴抽出を行うため、計算コストが高い。

### 解決

```python
# LPIPSは最終段階のみ、かつ間引いて実行
if scale >= 0.9 and iteration % 100 == 0:
    loss += 0.1 * lpips_loss(image, gt)
```

### 効果

| 設定 | 速度 |
|------|------|
| 毎回LPIPS | 1.5 it/s |
| 100回ごと | **77 it/s** |

---

## Bug 3: 勾配爆発（loss=nan）

### 症状

```
数千イテレーション後に突然 loss=nan
学習が破綻
```

### 原因

特定のGaussianで勾配が異常に大きくなり、パラメータが発散。

### 解決

```python
# 勾配クリッピング
torch.nn.utils.clip_grad_norm_(gaussians.parameters(), max_norm=1.0)

# NaNスキップ
if torch.isnan(loss):
    print(f"NaN detected at iteration {i}, skipping")
    optimizer.zero_grad()
    continue
```

### 追加対策

```python
# 学習率を保守的に
optimizer = torch.optim.Adam([
    {'params': gaussians._xyz, 'lr': 1e-4},       # 位置は低め
    {'params': gaussians._scaling, 'lr': 5e-3},
    {'params': gaussians._rotation, 'lr': 1e-3},
    {'params': gaussians._opacity, 'lr': 5e-2},
    {'params': gaussians._features_dc, 'lr': 2.5e-3},
])
```

:::message
**バグの根本原因をもっと深く理解したい方へ**

上記3つのバグは「表面的な修正」です。有料記事では、**なぜこのバグが起きるのか**を数学的背景から解説しています:

- Forward-Order Backward Passの数学（除算→乗算で130倍高速化）
- Quad Reductionのwarp同期問題と完全な解決コード
- メモリプールのbinning推定が破綻するケースと対策

→ [【有料】Backward Passを130倍高速化した方法](https://zenn.dev/amabito/articles/hyper-rasterizer-impl-paid)
:::

---

# 速度比較

## ベンチマーク環境

```
GPU: RTX 5090 (32GB)
Dataset: NeRF Synthetic (Lego)
Resolution: 800x800
Gaussians: 100K
```

## 結果

| ラスタライザ | 速度 | メモリ |
|-------------|------|--------|
| DGR | 45-50 it/s | 8.2 GB |
| gsplat | 15-20 it/s | 6.8 GB |
| **HyperRasterizer** | **77 it/s** | **7.5 GB** |

**HyperRasterizerはDGRより50%高速、メモリ効率も良好。**

---

# トレーニングコード全体

```python
import torch
from hyper_rasterizer import HyperRasterizer
from gaussian_model import GaussianModel

# 初期化
gaussians = GaussianModel()
gaussians.load_ply("input.ply")
rasterizer = HyperRasterizer()

optimizer = torch.optim.Adam(gaussians.parameters(), lr=1e-3)

for i in range(30000):
    optimizer.zero_grad()

    # Forward（生データを渡す）
    image, radii, depth = rasterizer.forward(
        means3D=gaussians.get_xyz(),
        scales=gaussians._scaling,
        rotations=gaussians._rotation,
        opacities=gaussians._opacity,
        shs=gaussians.get_features(),
        camera=camera,
    )

    # Loss
    loss = l1_loss(image, gt_image)
    if scale >= 0.9 and i % 100 == 0:
        loss += 0.1 * lpips_loss(image, gt_image)

    # NaNチェック
    if torch.isnan(loss):
        continue

    # Backward
    loss.backward()
    torch.nn.utils.clip_grad_norm_(gaussians.parameters(), max_norm=1.0)
    optimizer.step()
```

---

# まとめ

| 項目 | 内容 |
|------|------|
| 速度 | DGR比 **+50%** (77 it/s) |
| 商用利用 | ✅ Apache 2.0 |
| 注意点 | 生データ(`_scaling`等)を渡す |

**遭遇したバグ:**

1. **Double-Exp**: `exp(exp(x))` で爆発 → 生データを渡す
2. **LPIPS低下**: 毎回実行で1.5 it/s → 100回ごとに制限
3. **勾配爆発**: loss=nan → clip_grad_norm + NaNスキップ

---

# 関連記事

## 段階的に学ぶ

1. 📖 **基礎**: [HyperRasterizer完全解説](https://zenn.dev/amabito/articles/hyper-rasterizer-zenn) - 4169 FPS達成の全技術
2. 🔧 **トレーニング**: この記事（DGR比+50%高速な学習）
3. ⚡ **高速化の核心**: [【有料】Backward Passを130倍高速化した方法](https://zenn.dev/amabito/articles/hyper-rasterizer-impl-paid) - Forward-Order実装、Quad Reduction

## 事業化する

- [3DGS商用化ガイド](https://zenn.dev/amabito/articles/3dgs-commercial-guide) - ライセンス問題の整理
- [【有料】3DGSラスタライザ自作ガイド](https://zenn.dev/amabito/articles/3dgs-commercial-guide-paid) - 商用化の全手順
- [ブラウザで3DGSを表示する](https://zenn.dev/amabito/articles/hyper-viewer-webgpu) - WebGPUビューア

---

:::message
**HyperRasterizer** は Apache 2.0 ライセンスで公開しています。

GitHub: https://github.com/amabito/hyper-rasterizer
:::
