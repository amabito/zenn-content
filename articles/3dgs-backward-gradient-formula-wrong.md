---
title: "3DGS Backwardの勾配公式を間違えてPSNRが17→24dBになった話"
emoji: "📐"
type: "tech"
topics: ["CUDA", "3DGS", "機械学習", "数学", "深層学習"]
published: false
published_at: "2026-03-01 12:00"
---

## 間違った公式でも「なんとなく動く」

3D Gaussian Splattingのbackward passを自前実装していた。論文の公式を見ながら実装し、テストも通った。PSNRも少しずつ改善する。

でも何かが遅い。DGRのコードと比べると明らかに収束が遅い。

ある日、backwardの`dL/dα`（アルファ値の勾配）を計算する箇所を丁寧に見直した。

---

## 正しい公式と間違った公式

### アルファブレンディングのforward

3DGSのレンダリングは以下の積み重ねで行われる。

```
C = sum_i (c_i * alpha_i * T_i)

ここで:
  c_i = Gaussianのカラー
  alpha_i = 透明度（0〜1）
  T_i = 透過率（前のGaussianがどれだけ通したか）
  T_i = product_{j<i} (1 - alpha_j)
```

### dL/dαの正しい導出

損失`L`からα_iへの勾配を求める。

```
dL/dalpha_i = dL/dC * dC/dalpha_i

dC/dalpha_i を展開すると...

C = c_i * alpha_i * T_i  (i番目の寄与)
  + sum_{j>i} c_j * alpha_j * T_j  (それ以降の寄与)

T_jは alpha_i に依存する（T_j = T_i * (1-alpha_i) * ... ）

整理すると:
dC/dalpha_i = c_i * T_i - sum_{j>i} c_j * alpha_j * T_j / (1 - alpha_i)
```

ここで `dot_after_i = sum_{j>i} c_j * alpha_j * T_j / (1 - alpha_i)` と定義すると：

```
dL/dalpha_i = T_i * (dL/dC * c_i) - dot_after_i * (dL/dC)
            = T_i * dot_c - dot_after_i
```

ここで:
- `dot_c = dL/dC * c_i`（損失のカラー方向）
- `dot_after_i`：i番目以降のGaussianの合計色 / (1 - alpha_i)

### 自分が実装した（間違った）公式

```cpp
// WRONG
float dot_remaining = ...;  // 残りのGaussianの色の合計

// 間違い: dot_remaining / (1 - a)  を直接引いた
dL_dalpha = T * (dot_c - dot_remaining / (1 - a));
```

**この式の何が間違いか？**

`dot_remaining` と `dot_after` は微妙に違う。

```
dot_remaining = sum_{j>=i} c_j * alpha_j * T_j / (1 - alpha_i)
              = 自分自身の寄与 + i以降の寄与

dot_after     = sum_{j>i} c_j * alpha_j * T_j / (1 - alpha_i)
              = i以降のみの寄与（自分を含まない）
```

正しい公式では「i以降（自分を含まない）」が必要なのに、「i以降（自分を含む）」を使っていた。

---

## 数式で見る差異

```
dot_remaining = c_i * alpha_i * T_i / (1 - alpha_i) + dot_after
             = weight / (1 - alpha_i) + dot_after
```

ここで `weight = c_i * alpha_i * T_i`（自分の重み）とすると：

```
dot_remaining / (1 - a) = weight / (1-a)^2 + dot_after / (1-a)
```

これは正しい `dot_after / (1-a)` とは異なる。

**正しい計算：**

```cpp
// CORRECT
float dot_after = dot_remaining - weight * dot_c / T;
// weight = c_i * alpha_i * T_i
// T_i は forwardから保存

dL_dalpha = T * dot_c - dot_after;
```

`dot_remaining` から自分自身の寄与（`weight * dot_c / T`）を引くことで`dot_after`が得られる。

---

## コードの修正

```cpp
// before: WRONG
__global__ void backward_kernel(...) {
    float dot_remaining = ...; // accumulated from forward

    // WRONG: 自分の寄与が含まれたままの項を使用
    float dL_dalpha = T * (dot_c - dot_remaining / (1.0f - alpha + EPSILON));
}
```

```cpp
// after: CORRECT
__global__ void backward_kernel(...) {
    float dot_remaining = ...; // accumulated from forward
    float weight = alpha * T * color;  // 自分の寄与

    // 自分の寄与を引いてdot_afterを得る
    float dot_after = dot_remaining - weight * dot_c;

    // CORRECT
    float dL_dalpha = T * dot_c - dot_after / (1.0f - alpha + EPSILON);
}
```

---

## PSNRへの影響

```
WRONG formula: 17.63 dB  (1000 iterations)
CORRECT formula: 24.16 dB (1000 iterations)

差: +6.53 dB
```

**同じ反復回数で6.53 dB の差。**これは間違った勾配が「それっぽいノイズ」として機能しており、学習は進むが最適解には遠い方向に向かっていたことを意味する。

収束曲線を比較すると：

```
iter 100:  WRONG 14.2dB / CORRECT 18.7dB (+4.5dB)
iter 500:  WRONG 16.8dB / CORRECT 22.4dB (+5.6dB)
iter 1000: WRONG 17.6dB / CORRECT 24.2dB (+6.6dB)
iter 3000: WRONG 19.1dB / CORRECT 27.3dB (+8.2dB)
```

長く訓練するほど差が広がる。間違った勾配が早期の最適化を妨げ、その影響が蓄積していく。

---

## なぜ「なんとなく動く」のか

間違った公式でも完全に間違いではなく、**近似的に正しい場合がある**。

alpha_iが小さい（ほとんど透明なGaussian）とき：

```
weight = alpha * T * color ≈ 0  (alpha ≈ 0)

dot_after ≈ dot_remaining  (自分の寄与が小さい)

WRONG公式 ≈ CORRECT公式
```

不透明なGaussian（alpha ≈ 1）の場合に大きな誤差が生じる。シーンの中心にある重要なGaussianが不透明なことが多いため、全体的な品質に影響する。

---

## 単体テストで検証する方法

こういうバグを防ぐための単体テスト：

```python
import torch

def numerical_gradient_check(alpha: float, colors: list[float]) -> None:
    """数値微分と解析微分を比較してbackwardの正しさを検証"""

    # PyTorchの自動微分でgroundtruth勾配を計算
    alpha_tensor = torch.tensor(alpha, requires_grad=True)
    colors_tensor = torch.tensor(colors)

    # アルファブレンディングのforward
    T = torch.cumprod(1.0 - alpha_tensor * torch.ones(len(colors)), dim=0)
    C = (colors_tensor * alpha_tensor * T).sum()

    loss = C.sum()
    loss.backward()
    gt_grad = alpha_tensor.grad.item()

    # 数値微分
    eps = 1e-5
    C_plus = blend(alpha + eps, colors)
    C_minus = blend(alpha - eps, colors)
    numerical_grad = (C_plus - C_minus) / (2 * eps)

    print(f"Analytical gradient: {gt_grad:.6f}")
    print(f"Numerical gradient:  {numerical_grad:.6f}")
    print(f"Relative error:      {abs(gt_grad - numerical_grad) / abs(gt_grad):.6f}")
    assert abs(gt_grad - numerical_grad) < 1e-4, "Gradient check failed!"
```

単体テストで `numerical_gradient_check` を実装から分離してチェックしていれば、このバグは発見できた。

---

## デバッグの教訓

### 1. 解析微分と数値微分を常に比較する

```
解析微分（実装した公式）と数値微分（限りなく差分に近い有限差分）が一致するか確認する。
不一致 → 公式が間違っている or 実装が間違っている
```

### 2. PSNRが「遅い」は危険信号

収束はするが遅い → 勾配の方向は合っているが大きさがずれているかも。

### 3. 参照実装との比較は数値で行う

```python
# 参照実装（DGR）のbackwardと、自分の実装の出力を数値で比較
ref_grad = dgr_backward(alpha, T, color)
my_grad  = my_backward(alpha, T, color)
print(f"Difference: {abs(ref_grad - my_grad):.6f}")  # should be < 1e-5
```

コードを読んで「同じに見える」だけでは不十分。実際の数値を比較する。

---

## 正しい公式の最終形

```
dL/dalpha_i = T_i * dot_c - dot_after_i

ここで:
  T_i = product_{j<i} (1 - alpha_j)    (i番目のGaussianの透過率)
  dot_c = sum_channel (dL/dC_channel * c_i_channel)  (損失のカラー方向内積)
  dot_after_i = sum_{j>i} w_j * dot_c_j / (1 - alpha_i)  (i以降のGaussianの寄与)
  w_j = alpha_j * T_j  (j番目Gaussianの重み)
```

実装：

```cpp
float dL_dalpha = T * dot_c - dot_after / (1.0f - alpha + 1e-5f);
// ただし dot_after = dot_remaining - w * dot_c
//                   = dot_remaining - alpha * T * dot_c
```

---

## まとめ

| 観点 | 内容 |
|------|------|
| 間違い | `dot_remaining`（自分を含む）vs `dot_after`（自分を含まない） |
| 影響 | PSNR 17.63 → 24.16 dB（+6.53 dB、1000 iter） |
| 見つけた方法 | DGRのPSNRとの差が大きすぎたため再チェック |
| 防止策 | 解析微分 vs 数値微分の単体テスト |
| 教訓 | 「なんとなく動く」は「正しい」ではない |

数式1つの符号ミスが6dBの差になる。3DGSの実装は細部への注意が要求される。

---

## 関連記事

- [DGRを超えるまで: 3DGS PSNRを28.66→29.07dBに改善した全記録](/articles/3dgs-psnr-dgr-surpassed)
- [3DGS Forward/BackwardのIndex semantics不一致で勾配が4887倍ロストした話](/articles/3dgs-index-semantics-gradient-loss-4887x)
- [LPIPS GT Feature Cachingで3DGS学習を43%高速化した話](/articles/lpips-gt-feature-caching-43pct-speedup)
