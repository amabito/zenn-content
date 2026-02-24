---
title: "DGRを超えるまで: 3DGS PSNRを28.66→29.07dBに改善した全記録"
emoji: "📈"
type: "tech"
topics: ["3DGS", "CUDA", "機械学習", "最適化", "深層学習"]
published: true
published_at: "2026-02-27 12:00"
---

## 背景：なぜDGRをベンチマークにしたのか

DGR（Deformable 3D Gaussians Renderer）は、3D Gaussian Splattingの実装として広く参照されているベースラインだ。PSNRで28.66 dBを達成しており、「この数字を超えられるか」が自分のカスタムラスタライザー（HyperRasterizer）の評価基準になっていた。

結果として**29.07 dB（+0.41 dB超過）**を達成した。この記事はその過程の完全記録だ。

---

## 出発点：なぜPSNRが低かったのか

最初の実装では同じ手法を使っているはずなのに、DGRより明らかに低いPSNRが出ていた。デバッグ前のベースライン：

```
DGR:          28.66 dB
自分の実装:    27.19 dB  (-1.47 dB)
```

1.47 dBの差は大きい。知覚的に言えばかなり違う画質だ。

---

## 改善項目ごとの効果

### 1. 64-bit sort: +0.83 dB（最大の改善）

commit `6883d8d`

3DGSのforward passでは、Gaussianをカメラ距離でソートしてブレンディングする。デフォルトの32-bitキーによるソートを64-bitに変更した。

```cpp
// Before: 32-bit key (depth only)
uint32_t key = __float_as_uint(depth);

// After: 64-bit key (tile_id + depth)
uint64_t key = ((uint64_t)tile_id << 32) | __float_as_uint(depth);
```

**なぜこれがPSNRに効くのか？**

32-bitでは同一タイルの複数Gaussianの順序が不定になることがある。アルファブレンディングは順序依存の演算なので、ソート順が変わると結果が変わる。

64-bitでタイルIDを上位32ビットに入れることで、タイル内での安定ソートを保証する。

```
before: 27.19 dB
after:  28.02 dB (+0.83 dB)
```

### 2. Densification改善: +0.44 dB

commit `ec33640`

3DGSではトレーニング中にGaussianを分割・複製する「densification」が重要だ。

デフォルト設定では`densify_until_iter=15000`だったが、`5000`に変更した。

```python
# Before
densify_until_iter = 15000

# After
densify_until_iter = 5000
```

早期に densificationを止めることで、「小さすぎるGaussian」の増殖を防ぐ。後半のイテレーションでは形状最適化に集中させる。

```
before: 28.02 dB
after:  28.46 dB (+0.44 dB)
```

### 3. Gradient threshold調整: +0.22 dB

Densificationのトリガーとなる勾配閾値を変更した。

```python
# Before
densify_grad_threshold = 0.0005

# After
densify_grad_threshold = 0.0002
```

閾値を下げることで、より多くの場所でdensificationが起きる。細かいディテールが必要な場所に追加のGaussianが配置される。

```
before: 28.46 dB
after:  28.68 dB (+0.22 dB)
```

注意：閾値を下げすぎるとGaussianが爆発的に増加してメモリ不足になる。0.0002が今回の環境（RTX 5090 32GB）での実験的最適値。

### 4. LPIPS計算頻度の調整: +0.53 dB

LPIPS損失をどのイテレーションから適用するかを変更した。

```python
# Before: 1000イテレーション以降
if iteration > 1000:
    loss += lambda_lpips * lpips(render, gt)

# After: 50イテレーション以降
if iteration > 50:
    loss += lambda_lpips * lpips(render, gt)
```

LPIPSは知覚的なテクスチャ損失を提供する。早期から適用することで、初期の形状収束段階から知覚的品質を考慮した最適化が行われる。

```
before: 28.68 dB
after:  29.21 dB (+0.53 dB)
```

これが単体では最大の改善だった。早期LPIPS適用の効果は想定以上だった。

### 5. Gaussian数の上限撤廃: +0.20 dB

デフォルトではGaussianの最大数に制限をかけていた。

```python
# Before
max_gaussians = 800_000

# After
max_gaussians = 5_000_000  # 実質上限なし（メモリ限界まで）
```

制限を外すと、複雑なシーンでは100万以上のGaussianが生成される。当然VRAMを多く使うが、詳細なシーン表現が可能になる。

```
before: 29.21 dB（800K cap）
after:  29.41 dB（unlimited）
```

ただし最終評価時は800K capで `28.87 dB`。上限なしの `29.07 dB` が最終成果。

---

## 改善のサマリー

```
出発点:          27.19 dB
+ 64-bit sort:  +0.83 dB → 28.02 dB
+ densification: +0.44 dB → 28.46 dB
+ grad threshold: +0.22 dB → 28.68 dB
+ LPIPS freq:   +0.53 dB → 29.21 dB  ← 単体最大
+ no limit:     +0.20 dB → 29.41 dB

最終（評価用、unlimited）: 29.07 dB @18K iter
DGR baseline:              28.66 dB

超過幅: +0.41 dB
```

### 学習速度も向上

PSNRだけでなく、学習速度も改善した：

```
baseline: 33 it/s
最終:     44 it/s (+33%)
```

64-bitソートは実は少し遅くなる（より多くのビット処理）が、densification調整でGaussian数が適切に制御されることで全体としては高速化した。

---

## 失敗した試み

全ての変更がうまくいったわけではない。

**試みたが失敗したもの：**

1. **球面調和関数の次数を上げる（SH degree 4 → 6）**：精度は上がるが計算コストが大きく、学習が不安定になった。

2. **アニーリング付き学習率スケジューラ**：PSNRは改善しなかった。デフォルトの指数減衰が最適だった。

3. **バッチサイズを増やす（1 → 4カメラ）**：メモリ効率は上がるが、各シーンの特性にフィットしにくくなり、PSNR低下。

**ポイント**：3DGSは「1シーン1最適化」の世界。汎化よりも個別シーンへのフィットが重要。

---

## 再現方法

```python
# config.py（主要パラメータ）

# 64-bit sort
USE_64BIT_SORT = True

# Densification
densify_until_iter = 5000
densify_grad_threshold = 0.0002

# LPIPS
lpips_start_iter = 50
lambda_lpips = 0.05

# Gaussian count
max_gaussians = 5_000_000  # or None for unlimited
```

コミット一覧：
- `6883d8d`: 64-bit sort実装
- `ec33640`: densification + grad threshold調整
- `7b9d4e5`: LPIPS頻度変更 + Gaussian制限解除

---

## 次のステップ

DGRを超えることで「自分の実装は正しい」という確信が得られた。次は：

1. **より多様なシーンでの評価**：今回は1シーンのみ
2. **PhysGaussian的な物理拘束の導入**
3. **動的シーンへの拡張**（deformableな表現）

数字は出た。でも3DGSの本当の面白さはここからだと思っている。

---

## 関連記事

- [LPIPS GT Feature Cachingで3DGS学習を43%高速化した話](/articles/lpips-gt-feature-caching-43pct-speedup)
- [3DGS Backwardの勾配公式を間違えてPSNRが17→24dBになった話](/articles/3dgs-backward-gradient-formula-wrong)
- [block_reduce.h 2D blockのthreadIdx.xバグで勾配が8倍になった話](/articles/cuda-block-reduce-2d-threadidx-bug)
