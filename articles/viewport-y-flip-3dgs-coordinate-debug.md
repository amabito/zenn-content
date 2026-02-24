---
title: "VIEWPORT_Y_FLIP: 4日かかった3DGS座標系デバッグの全記録"
emoji: "🔄"
type: "tech"
topics: ["webgpu", "3dgs", "typescript", "debugging", "graphics"]
published: true
published_at: "2026-03-02 07:00"
---

## 計測マーカーがカメラ回転でズレる

WebGPUベースの3DGSビューア（HyperViewer）を開発中、奇妙なバグに遭遇した。

3DGSシーン上に計測マーカー（距離・面積測定用のピン）を配置すると、カメラを回転させるたびにマーカーが少しずつズレていく。

```
カメラ正面 → マーカーが特徴点の上に正確に配置
カメラを45度回転 → マーカーが特徴点から10〜20pxズレる
カメラを90度回転 → さらにズレが広がる
```

カメラが動いてもマーカーはシーン上の固定点に留まるべきだ。しかし何かが狂っている。

4日間のデバッグの末、原因が判明した。**VIEWPORT_Y_FLIPという座標変換の不一致**だった。

---

## Day 1〜2: 的外れな仮説たち

### 仮説1: Three.jsカメラの同期タイミング

最初に疑ったのはタイミング問題だ。

WebGPUレンダラーはカスタム実装で、Three.jsのカメラ行列を毎フレーム渡している。「render後にカメラ行列を取得しているのでは？」と思い、`requestAnimationFrame`コールバックの後にカメラ同期を追加した。

**結果**: 変化なし。

### 仮説2: Gaussianの中心点と表面の視差

3DGSのGaussianは楕円体だ。ユーザーがクリックした「表面の点」と「Gaussian中心」は異なる。カメラ角度が変わると、中心に基づくスクリーン座標が表面の位置からズレるのでは？

深度バッファから正確な3D座標を取得するdepth-guided selectionを実装した。

**結果**: 18pxのエラーが残る。

### Day 3: 「reproj_err = 0なのにズレる」謎

深度から取得したワールド座標をスクリーンに再投影し、元のクリック位置との誤差（reproj_err）を計算した。

```
reproj_err = 0px  ← 完全一致
```

「完璧だ。保存した3D座標は正確」と思い、このワールド座標をマーカー位置として保存した。

しかし、カメラを回転させると**やはりズレる**。

reproj_errが0なのにズレる。意味がわからない。

---

## Day 4: 本当の原因

### レンダリングパイプラインの確認

グラフィックスの基本に立ち返ることにした。「レンダラーはどのようにピクセルを配置しているか？」をソースから追った。

```glsl
// GPUが受け取るカメラ行列
camera.proj = VIEWPORT_Y_FLIP * P
// VIEWPORT_Y_FLIP = diag(1, -1, 1, 1)  ← Yを反転

// シェーダー内
pos2d = camera.proj * camspace_position
// NDC Y は反転している

// WebGPUのフレームバッファ変換
// クリップ座標 → スクリーン座標
y_fb = (1 - clip.y) / 2 * height
// Y_FLIPがある場合:
// clip.y = -ndc_y
// y_fb = (1 - (-ndc_y)) / 2 * h = (1 + ndc_y) / 2 * h
```

**Y_FLIPが適用されている。** これによりフレームバッファのY座標は `(1 + ndcY) / 2 * h` で計算される。

### CPU側のコードを確認

CPU側の座標変換コードを全て調べると、**全員が間違っていた**。

```typescript
// BEFORE: 全ての関数がY_FLIPなし(Three.js標準)の式を使用

// MeasurementManager.ts - projectToScreen
screenY = (-ndcY + 1) / 2 * height;  // ← WRONG

// LabelRenderer.ts
canvasY = (-ndcY + 1) / 2 * height;   // ← WRONG

// depth-picker.ts - depthToWorldPosition
ndcY = -(2 * y / height - 1);         // ← WRONG

// adaptive-gaussian-picker.ts - pickByProjection
sy = -ndcY * halfH + centerY;         // ← WRONG
```

全ての関数がY_FLIPを考慮していなかった。本来は `(ndcY + 1) / 2 * h` であるべき。

---

## なぜreproj_err = 0が嘘をついたか

ここが最もトリッキーだった。

projectToScreenとDepthPickerが**同じバグ**を持っていた。

```
[正しいフロー]
クリック座標(x, y_fb) → DepthPicker → NDC(正しい) → ワールド座標W

[バグありフロー]
クリック座標(x, y_fb) → DepthPicker(バグ) → NDC(誤) → ワールド座標W'
```

バグありの場合、保存されるワールド座標W'はYが鏡映反転している（カメラ平面に対して）。

しかし検証時にも同じバグのある`projectToScreen`を使う：

```
W' → projectToScreen(バグ) → スクリーン座標 → reproj_err = 0
```

バグが対称的なため、往復でキャンセルされてreproj_errが0になる。W'がWではないのに、検証がパスしてしまう。

**なぜカメラ回転後にズレるか：**

- W'はWのY鏡映反転点（カメラ平面基準）
- カメラが正面を向いているとき、この違いは小さい
- カメラを回転させると、W'とWは異なるスクリーン座標に投影される
- 特にNDC Yが大きく変化するほど、ズレが大きくなる

---

## 修正: 6箇所のY計算を全て統一

修正は単純だ。Y_FLIPの式 `y = (1 + ndcY) / 2 * h` に統一する。

| ファイル | 修正前 | 修正後 |
|---------|--------|--------|
| MeasurementManager.ts - projectToScreen | `(-ndcY+1)/2*h` | `(ndcY+1)/2*h` |
| LabelRenderer.ts | `(-ndcY+1)/2*h` | `(ndcY+1)/2*h` |
| adaptive-gaussian-picker.ts - pickByProjection | `-ndcY*halfH+centerY` | `ndcY*halfH+centerY` |
| adaptive-gaussian-picker.ts - pickMultipleByProjection | 同上 | 同上 |
| adaptive-gaussian-picker.ts - unprojectToWorld | `-(2*y/h-1)` | `2*y/h-1` |
| depth-picker.ts - depthToWorldPosition | `-(2*y/h-1)` | `2*y/h-1` |

commit `f4d9d6f`で修正した。

修正後：カメラをどの方向に回転させてもマーカーが特徴点に張り付いたまま動かなくなった。

---

## なぜY_FLIPが必要か

COLMAPとWebGPUの座標系の違いに起因する。

```
COLMAP:  Y軸が下向き、Z軸が前向き
WebGPU:  Y軸が上向き（NDC）、フレームバッファはY軸が下向き
```

COLMAP由来のカメラ行列をそのままWebGPUに渡すと、レンダリング結果が上下反転する。

解決策として、投影行列に `VIEWPORT_Y_FLIP = diag(1, -1, 1, 1)` を掛ける。これでNDC Yが反転し、フレームバッファ上で正しく表示される。

しかしこれにより、CPU側でスクリーン座標とNDC座標を変換する全ての関数が、Y_FLIPを考慮した計算式を使わなければならなくなる。

Three.jsの標準的な式（Y_FLIPなし）が `y = (1 - ndcY) / 2 * h` で、Y_FLIPありは `y = (1 + ndcY) / 2 * h` だ。符号一つの違いだが、これを見落とすと今回のような4日間のデバッグが待っている。

---

## 教訓

### 1. reproj_err = 0 は正確性の証明にならない

順変換（スクリーン→NDC→ワールド）と逆変換（ワールド→NDC→スクリーン）が同じバグを持っていると、往復のテストはパスする。

**正確性の検証は独立した経路で行う必要がある。**

### 2. デバッグはレンダラーから始める

「このピクセルはレンダラーがどう配置したか？」から逆算する。CPU側の「きっとこうなっているはず」という仮定を捨てる。

具体的には：

```
1. シェーダーコードを読む（座標変換の式を確認）
2. GPU→CPUの座標変換式を導出する
3. CPU側の全関数がその式に一致しているか確認
```

### 3. 座標系は1箇所で定義する

`screenToNDC`のような共通関数を1つ作り、全ての変換をそこに集約する。今回はWebGPU+Y_FLIPという特殊事情があったため、Three.jsの標準関数をそのまま使えなかった。

プロジェクト固有の座標系変換は、**共通ユーティリティを新たに定義**して全ての変換を通過させるのが正しい。

### 4. コメントに座標系を明記する

```typescript
// Y_FLIP有効時のスクリーン→NDC変換
// WebGPU: y_fb = (1 + ndcY) / 2 * h
// ∴ ndcY = 2 * y_fb / h - 1  (Y_FLIP, COLMAP+WebGPU環境)
// ≠ -(2 * y_fb / h - 1)  (Y_FLIPなし, Three.js標準)
function screenToNDC_YFLIP(y_fb: number, height: number): number {
    return 2 * y_fb / height - 1;
}
```

---

## まとめ

4日間のデバッグを一言で言えば：

**「6箇所のY座標計算がY_FLIPを考慮していなかった」**

これだけのことが4日かかった理由は：

1. reproj_errが0で「座標は正確」という偽陽性が出た
2. カメラ正面では誤差が小さく、回転後にしか顕在化しなかった
3. バグが複数の関数に分散していた

座標系の不一致は、グラフィックスプログラミングで最も発見しにくいバグの一つだ。

**COLMAP、WebGPU、Three.jsを組み合わせる場合は、Y_FLIPの扱いを最初に設計段階で決めておくこと。**
