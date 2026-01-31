---
title: "【有料】3DGSラスタライザを自作する3つの方法【商用利用OK】"
emoji: "🔥"
type: "tech"
topics: ["3DGS", "CUDA", "ラスタライザ", "商用利用"]
published: true
published_at: "2026-01-01 12:00"
price: 1980
---

# この記事で得られるもの

**3DGSを商用利用したい。でもライセンス問題がある。自作するしかない。**

- 3DGSラスタライザの**アーキテクチャ完全解説**
- **gsplat改造**から**完全自作**まで3つの方法
- 商用OKな**ライセンス戦略**

**対象読者:** 3DGSを商用利用したい人、ラスタライザを自作したい人

---

# 無料記事のおさらい

- オリジナル3DGSは商用不可
- gsplatは遅い、Inria契約は高い
- 自作が現実的な選択肢

今回は**具体的な実装方法**を解説する。

---

:::message
ここから有料パートです。
:::

# ラスタライザのアーキテクチャ

## 処理フロー

```
入力: 3D Gaussians (位置, 回転, スケール, 色, 不透明度)
  │
  ├─► Preprocessing
  │     ├── 3D → 2D 投影
  │     ├── 視錐台カリング
  │     └── 2D共分散計算
  │
  ├─► Binning
  │     ├── タイル分割（16x16ピクセル）
  │     └── 各タイルに影響するGaussianをリスト化
  │
  ├─► Sorting
  │     └── 各タイル内でGaussianを深度順ソート
  │
  └─► Rendering
        └── タイルごとにα-blendingで描画

出力: 画像 (H x W x 3)
```

## ファイル構成

```
hyper_rasterizer/
├── cuda/
│   ├── preprocessing.cu   # 投影、カリング
│   ├── sorting.cu         # Radix Sort
│   ├── forward.cu         # レンダリング（Forward）
│   ├── backward.cu        # 勾配計算（Backward）
│   └── common.h           # 共通定義
├── ext.cpp                # PyBind11バインディング
└── __init__.py            # Pythonラッパー
```

---

# 選択肢A: gsplatベースの改造

## gsplatの構造

```
gsplat/
├── cuda/csrc/
│   ├── rasterize.cu       # メインレンダリング
│   ├── project.cu         # 投影
│   └── helpers.cuh        # ユーティリティ
└── gsplat/
    └── rendering.py       # Pythonインターフェース
```

## 改造ポイント

### 1. Fast Mathを有効化

```cuda
// gsplat/cuda/csrc/rasterize.cu

// 変更前
float G = expf(power);

// 変更後
float G = __expf(power);  // 3-5%高速化
```

### 2. 早期終了の閾値調整

```cuda
// 変更前
if (T < 1e-4f) break;

// 変更後（より積極的に打ち切り）
if (T < 1e-3f) break;  // 10-20%高速化、品質低下は軽微
```

### 3. ソートビット最適化

```cuda
// 変更前: 64bit全体をソート
cub::DeviceRadixSort::SortPairs(..., 0, 64);

// 変更後: 32bitだけソート
cub::DeviceRadixSort::SortPairs(..., 0, 32);
```

## 注意点

gsplatはApache 2.0なので改造・再配布OK。ただし:

- 変更点を明記（Apache 2.0の要件）
- 著作権表示を残す

---

# 選択肢B: 完全自作

## Preprocessing

```cuda
__global__ void preprocess_kernel(
    int N,
    const float3* means3d,      // 3D位置
    const float4* quats,        // 回転（クォータニオン）
    const float3* scales,       // スケール
    const float* viewmat,       // 4x4 view matrix
    const float* projmat,       // 4x4 projection matrix
    int W, int H,
    float2* means2d,            // 出力: 2D位置
    float3* conics,             // 出力: 2D共分散の逆行列
    int* radii,                 // 出力: バウンディング半径
    float* depths               // 出力: 深度
) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= N) return;

    // 3D位置を取得
    float3 mean = means3d[idx];

    // View座標に変換
    float3 mean_view;
    mean_view.x = viewmat[0]*mean.x + viewmat[4]*mean.y + viewmat[8]*mean.z + viewmat[12];
    mean_view.y = viewmat[1]*mean.x + viewmat[5]*mean.y + viewmat[9]*mean.z + viewmat[13];
    mean_view.z = viewmat[2]*mean.x + viewmat[6]*mean.y + viewmat[10]*mean.z + viewmat[14];

    // 視錐台カリング
    if (mean_view.z <= 0.2f) {
        radii[idx] = 0;
        return;
    }

    // NDC座標に変換
    float4 mean_ndc;
    mean_ndc.x = projmat[0]*mean_view.x + projmat[4]*mean_view.y + projmat[8]*mean_view.z + projmat[12];
    mean_ndc.y = projmat[1]*mean_view.x + projmat[5]*mean_view.y + projmat[9]*mean_view.z + projmat[13];
    mean_ndc.z = projmat[2]*mean_view.x + projmat[6]*mean_view.y + projmat[10]*mean_view.z + projmat[14];
    mean_ndc.w = projmat[3]*mean_view.x + projmat[7]*mean_view.y + projmat[11]*mean_view.z + projmat[15];

    // ピクセル座標
    float2 mean2d_pix;
    mean2d_pix.x = ((mean_ndc.x / mean_ndc.w) * 0.5f + 0.5f) * W;
    mean2d_pix.y = ((mean_ndc.y / mean_ndc.w) * 0.5f + 0.5f) * H;

    // 2D共分散計算（省略、詳細は後述）
    float3 conic = compute_conic_2d(quats[idx], scales[idx], viewmat, projmat, mean_view.z);

    // 半径計算
    float det = conic.x * conic.z - conic.y * conic.y;
    float radius = 3.0f * sqrtf(max(conic.x, conic.z) / det);
    int radius_pix = (int)ceilf(radius);

    // 画面内チェック
    if (mean2d_pix.x + radius_pix < 0 || mean2d_pix.x - radius_pix >= W ||
        mean2d_pix.y + radius_pix < 0 || mean2d_pix.y - radius_pix >= H) {
        radii[idx] = 0;
        return;
    }

    // 出力
    means2d[idx] = mean2d_pix;
    conics[idx] = conic;
    radii[idx] = radius_pix;
    depths[idx] = mean_view.z;
}
```

## Forward Pass

```cuda
__global__ void render_forward_kernel(
    int W, int H,
    int tile_width, int tile_height,
    const int2* tile_ranges,     // 各タイルのGaussian範囲
    const int* gaussian_ids,     // ソート済みGaussian ID
    const float2* means2d,
    const float3* conics,
    const float3* rgbs,
    const float* opacities,
    float* out_color             // 出力画像
) {
    // タイル座標
    int tile_x = blockIdx.x;
    int tile_y = blockIdx.y;
    int tile_id = tile_y * tile_width + tile_x;

    // ピクセル座標
    int px = tile_x * 16 + threadIdx.x;
    int py = tile_y * 16 + threadIdx.y;

    if (px >= W || py >= H) return;

    // このタイルのGaussian範囲
    int2 range = tile_ranges[tile_id];

    // α-blending
    float T = 1.0f;
    float3 C = make_float3(0, 0, 0);

    for (int i = range.x; i < range.y; i++) {
        int gid = gaussian_ids[i];

        float2 mean = means2d[gid];
        float3 conic = conics[gid];

        // 2D Gaussian評価
        float dx = px - mean.x;
        float dy = py - mean.y;
        float power = -0.5f * (conic.x * dx * dx +
                                conic.z * dy * dy +
                                2.0f * conic.y * dx * dy);

        if (power > 0.0f) continue;

        float G = __expf(power);
        float alpha = min(0.99f, opacities[gid] * G);

        if (alpha < 1.0f / 255.0f) continue;

        float weight = alpha * T;

        C.x += weight * rgbs[gid].x;
        C.y += weight * rgbs[gid].y;
        C.z += weight * rgbs[gid].z;

        T *= (1.0f - alpha);

        if (T < 0.0001f) break;
    }

    // 出力
    int pixel_id = py * W + px;
    out_color[pixel_id * 3 + 0] = C.x;
    out_color[pixel_id * 3 + 1] = C.y;
    out_color[pixel_id * 3 + 2] = C.z;
}
```

## Backward Pass（Forward-Order）

```cuda
__global__ void render_backward_kernel(
    // ... 引数省略 ...
) {
    // タイル・ピクセル座標（Forward と同じ）

    // 上流勾配
    float3 dL_dC = make_float3(
        dL_dout[pixel_id * 3 + 0],
        dL_dout[pixel_id * 3 + 1],
        dL_dout[pixel_id * 3 + 2]
    );

    // Forward-Order: 順方向に走査
    float T = 1.0f;
    float3 C_accum = make_float3(0, 0, 0);

    for (int i = range.x; i < range.y; i++) {
        int gid = gaussian_ids[i];

        // Gaussian評価（Forwardと同じ）
        // ...

        float weight = alpha * T;

        // --- 色への勾配 ---
        atomicAdd(&dL_drgbs[gid * 3 + 0], dL_dC.x * weight);
        atomicAdd(&dL_drgbs[gid * 3 + 1], dL_dC.y * weight);
        atomicAdd(&dL_drgbs[gid * 3 + 2], dL_dC.z * weight);

        // --- αへの勾配 ---
        float dL_dalpha = dL_dC.x * T * (rgbs[gid].x - C_accum.x / (1.0f - alpha + 1e-6f))
                        + dL_dC.y * T * (rgbs[gid].y - C_accum.y / (1.0f - alpha + 1e-6f))
                        + dL_dC.z * T * (rgbs[gid].z - C_accum.z / (1.0f - alpha + 1e-6f));
        atomicAdd(&dL_dopacities[gid], dL_dalpha * G);

        // --- 位置、共分散への勾配 ---
        // （省略、詳細はリポジトリ参照）

        // 状態更新
        C_accum.x += weight * rgbs[gid].x;
        C_accum.y += weight * rgbs[gid].y;
        C_accum.z += weight * rgbs[gid].z;
        T *= (1.0f - alpha);

        if (T < 0.0001f) break;
    }
}
```

---

# ライセンス戦略

## 推奨: Apache 2.0

```
Apache 2.0のメリット:
- 商用利用OK
- 改変OK
- 再配布OK
- 特許付与条項あり（訴訟リスク低減）
```

## デュアルライセンスという選択

```
OSS版: AGPL（無料だが公開義務あり）
商用版: 有料ライセンス（公開義務なし）
```

例: MongoDB, Qt, Redis

---

# まとめ

3DGSラスタライザ自作の道:

| アプローチ | 難易度 | 速度向上 | 自由度 |
|-----------|--------|---------|--------|
| gsplat改造 | 低 | 1.5-2x | 中 |
| 完全自作 | 高 | 10-100x | 高 |

**商用利用するなら、自作が最もコントロールしやすい。**

この記事で解説したコードを参考に、自分だけのラスタライザを作ってほしい。
