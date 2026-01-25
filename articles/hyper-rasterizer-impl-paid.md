---
title: "【有料】3DGSラスタライザをCUDAで実装する：1000FPS達成の全技術"
emoji: "🔥"
type: "tech"
topics: ["cuda", "3dgs", "gpu", "機械学習", "グラフィックス"]
published: true
price: 1980
---

# この記事で得られるもの

- 3DGSラスタライザのBackward Pass実装方法
- **130倍高速化**を実現したForward-Order手法の詳細
- **1M Gaussians @ 1080p = 1000 FPS**を達成した最適化技術
- 実際に動くCUDAコード（コピペ可）
- ハマった罠とその解決策

**対象読者:** CUDAの基礎がわかる人、3DGSを商用利用したい人

---

# 無料パートのおさらい

前回の記事で、3DGSの商用利用には自作ラスタライザが必要だと説明した。

- diff-gaussian-rasterization: 商用不可
- gsplat: 商用OK、でも10倍遅い
- **HyperRasterizer**: 商用OK、1M Gaussians @ 1080p = 1000 FPS

今回は「どうやって1000 FPSを達成したのか」を、コード付きで完全解説する。

---

# 3DGSレンダリングの数学

## α-blending の式

3DGSは、各ピクセルの色を以下の式で計算する。

$$
C = \sum_{i=1}^{N} c_i \cdot \alpha_i \cdot T_i
$$

ここで:
- $c_i$: i番目のGaussianの色
- $\alpha_i$: i番目のGaussianの不透明度（0〜1）
- $T_i$: i番目のGaussianに到達する光の透過率

$$
T_i = \prod_{j=1}^{i-1} (1 - \alpha_j)
$$

つまり「手前のGaussianをどれだけ透過してきたか」。

## Forward Pass（順方向）

Forward Passは単純。前から順番に計算すればいい。

```cuda
__device__ void forward_pixel(
    int N,                    // Gaussianの数
    const float* colors,      // 各Gaussianの色 [N, 3]
    const float* alphas,      // 各Gaussianのα [N]
    float* out_color          // 出力色 [3]
) {
    float T = 1.0f;           // 透過率（最初は100%）
    float C[3] = {0, 0, 0};   // 累積色

    for (int i = 0; i < N; i++) {
        float alpha = alphas[i];
        float weight = alpha * T;

        // 色を加算
        C[0] += weight * colors[i * 3 + 0];
        C[1] += weight * colors[i * 3 + 1];
        C[2] += weight * colors[i * 3 + 2];

        // 透過率を更新
        T *= (1.0f - alpha);

        // 早期終了
        if (T < 0.0001f) break;
    }

    out_color[0] = C[0];
    out_color[1] = C[1];
    out_color[2] = C[2];
}
```

これは問題ない。**問題はBackward Pass。**

---

:::message
ここから有料パートです。1000 FPSを達成した全技術を解説します。
:::

# Backward Passの難しさ

## 勾配の連鎖律

学習時、損失関数 $L$ から各パラメータへの勾配を計算する必要がある。

$$
\frac{\partial L}{\partial c_i}, \quad \frac{\partial L}{\partial \alpha_i}
$$

連鎖律より:

$$
\frac{\partial L}{\partial c_i} = \frac{\partial L}{\partial C} \cdot \frac{\partial C}{\partial c_i} = \frac{\partial L}{\partial C} \cdot \alpha_i \cdot T_i
$$

ここで $\frac{\partial L}{\partial C}$ は上流から来る勾配（既知）。

**問題は $T_i$ の計算。**

## 従来手法：逆順処理

オリジナル実装は、$T_i$ を逆順に計算する。

```cuda
// 従来手法（逆順）
float T_final = /* forward passで計算した最終透過率 */;
float T = T_final;

for (int i = N - 1; i >= 0; i--) {
    // T_i を復元（除算！）
    T = T / (1.0f - alphas[i]);

    // 勾配計算...
}
```

### 問題1: 数値不安定

$\alpha_i \approx 1$ のとき、$(1 - \alpha_i) \approx 0$ で除算が爆発する。

```
α = 0.999 → 1 / 0.001 = 1000
α = 0.9999 → 1 / 0.0001 = 10000
```

実際のコードでは `max(1 - alpha, 1e-6)` のようなクランプが必要になり、勾配が不正確になる。

### 問題2: 遅い

- 除算は乗算より遅い（約4倍）
- 逆順アクセスはキャッシュ効率が悪い
- Forward Passと逆順なので、データの再読み込みが発生

---

# Forward-Order Backward Pass

## 発想の転換

逆順で $T_i$ を復元するのではなく、**順方向で $T_i$ を再計算**する。

「えっ、Forward Passと同じことをもう一度やるの？無駄じゃない？」

実はそうでもない。理由:

1. 乗算のみで数値的に安定
2. キャッシュ効率が良い（順方向アクセス）
3. Forward Passの中間値を保存する必要がない（メモリ節約）

## 実装のポイント

Forward-Order Backwardの実装には以下の要素が必要:

1. **順方向でT_iを再計算**: Forward Passと同じ順序でループ
2. **色への勾配**: `∂L/∂c_i = ∂L/∂C * α_i * T_i` を順方向で計算
3. **αへの勾配**: prefix sumを使って効率的に計算

詳細な実装コードはHyperRasterizerソースコードを参照。

**結果: 8000ms → 60ms（130倍高速化）**

---

# Quad Reduction: Atomic操作を4分の1に

## 問題

Backward Passでは、複数ピクセルが同じGaussianに勾配を書き込む。

```cuda
atomicAdd(&dL_drgbs[gaussian_id * 3 + 0], dL_drgb_local[0]);
atomicAdd(&dL_drgbs[gaussian_id * 3 + 1], dL_drgb_local[1]);
atomicAdd(&dL_drgbs[gaussian_id * 3 + 2], dL_drgb_local[2]);
```

1M Gaussians × 100万ピクセル = 数十億回のAtomic操作。これがボトルネック。

## 解決: Quad（2x2ピクセル）で事前集約

Quad Reductionの基本アイデア:
- 4ピクセル（2x2）で勾配を集約してから1回のAtomicを実行
- `__shfl_xor_sync`を使ってwarp内でデータを交換
- 4スレッドのうち1つだけがAtomic実行

**効果: Atomic操作が4分の1に削減**

## 落とし穴: warp同期問題

`__shfl_xor_sync`は**全スレッドが参加**しないとデッドロックする。

**NG**: 条件分岐内でshfl_xor_syncを呼ぶ
**OK**: 条件分岐の外でshflを呼び、結果を条件分岐内で使う

詳細は [CUDA warp同期の罠](https://zenn.dev/amabito/articles/cuda-warp-sync-trap) を参照。

---

# メモリプール: 1M Gaussians対応

## 問題1: cudaMallocオーバーヘッド

毎フレームcudaMallocを呼ぶと、数msのオーバーヘッドが発生。

```cuda
// NG: 毎フレームアロケート
void render_frame() {
    float* buffer;
    cudaMalloc(&buffer, size);  // 2-5ms のオーバーヘッド
    // ... レンダリング ...
    cudaFree(buffer);
}
```

## 解決: フレームベースメモリプール

メモリプールの基本構造:
- 起動時に大きなバッファを1回だけ確保
- フレームごとにオフセットをリセットして再利用
- アライメントに注意（256バイト境界推奨）

## 問題2: first-frame bug

最初のフレームだけ出力が真っ黒になる問題。

**原因**: cudaMallocはメモリを初期化しない
**解決**: `cudaMemset`でゼロ初期化

## 問題3: binning推定の爆発

1M Gaussians @ 1080pで、メモリ推定が**73GB**になった。

**原因**: タイルカバレッジの過大推定

**解決のポイント**:
- 現実的なタイルカバレッジ推定
- Gaussian当たりのタイル数にキャップを設ける
- 全体にハードキャップを設ける

**結果: 0.1 FPS → 1000 FPS**

---

# Lazy SH評価: 推論をさらに高速化

## 従来: 全Gaussianを事前評価

```cuda
// preprocessing.cu
for (int i = 0; i < N; i++) {
    rgb[i] = eval_sh(sh_coeffs[i], view_dir);  // 100万回
}
```

しかし、実際にレンダリングされるのは一部だけ（視錐台カリングで50%以上が除外）。

## Lazy: 必要な時だけ評価

Lazy SH評価の実装ポイント:
- レンダリングループ内でSH評価（前処理ではなく）
- カメラ位置を共有メモリにキャッシュして高速化
- 視錐台カリングで除外されるGaussianの評価をスキップ

**効果: 推論時15-25%高速化（カリング率に依存）**

**制限**: Backward Passではpre-computed RGBが必要なため、学習時は従来パスを使用。

---

# 試したが効果がなかったもの

## Warp Reduction

理論上はQuad Reductionをさらに拡張して、32スレッド（1 warp）で集約すれば、Atomic操作を32分の1にできる。

```cuda
// 理論上は良さそう
float warp_sum = warp_reduce(local_grad);
if (lane_id == 0) {
    atomicAdd(&global_grad, warp_sum);
}
```

**実測結果**:
- 直接Atomic: 61ms
- Warp Reduction: **400ms**（6.5倍遅い！）

**原因**: RTX 5090のL2キャッシュ（96MB）とAtomicユニットが強力すぎて、Warp内で集約するオーバーヘッドの方が大きくなった。

**教訓: 最新GPUでは、古い最適化テクニックが逆効果になることがある。必ず実測すること。**

---

# GPU別最適化

GPU世代ごとに最適なパラメータを自動選択する仕組み:
- SM (Compute Capability) を検出
- バッチサイズとFast Math設定を調整

| GPU | SM | Batch | FastMath |
|-----|-----|-------|----------|
| RTX 5090 | ≥120 | 大 | ON |
| RTX 4090 | ≥89 | 大 | ON |
| RTX 3090 | ≥86 | 中 | ON |
| RTX 2080 | ≥75 | 中 | ON |
| GTX 1080 | ≥60 | 小 | OFF |

---

# まとめ

1000 FPSを達成した技術:

| 技術 | 効果 |
|------|------|
| Forward-Order Backward | 130x高速化 |
| Quad Reduction | Atomic 4x削減 |
| メモリプール | cudaMallocオーバーヘッド排除 |
| binning推定最適化 | 73GB → 適正サイズ |
| Lazy SH評価 | 推論15-25%高速化 |
| GPU自動検出 | 世代別最適化 |

**結果: gsplat比130倍以上高速、1M Gaussians @ 1080p = 1000 FPS**

---

# おわりに

この記事で解説した手法は、HyperRasterizerの核心部分。

「既存実装が遅いなら、自分で作ればいい」

そのための知識を、この記事で提供した。

質問があればコメントへ。

---

# 参考文献

- [3D Gaussian Splatting for Real-Time Radiance Field Rendering](https://repo-sam.inria.fr/fungraph/3d-gaussian-splatting/)
- [CUDA C++ Programming Guide](https://docs.nvidia.com/cuda/cuda-c-programming-guide/)
- [Efficient Differentiation of Pixel-Level Computations](https://arxiv.org/abs/2505.18764)
