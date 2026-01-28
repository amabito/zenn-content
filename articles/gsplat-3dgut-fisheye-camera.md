---
title: "gsplat + 3DGUT：歪みカメラ対応で3DGSの制約が消えた"
emoji: "📸"
type: "tech"
topics: ["3DGS", "gsplat", "nerfstudio", "CUDA", "カメラ"]
published: true
published_at: "2026-02-03 07:00"
---

# 結論から言う

**NVIDIAの3DGUT（3D Gaussian Unscented Transform）がgsplatにネイティブ統合され、3DGSが魚眼カメラ・ローリングシャッター・F-Thetaカメラに対応した。** undistort前処理は不要になり、COLMAPの歪みパラメータだけで学習できる。Apache 2.0。

**対象読者:**
- 3D Gaussian Splattingを実務で使っている人
- 魚眼カメラや広角カメラのデータを扱っている人
- gsplat / nerfstudioユーザー

**この記事で得られること:**
- 従来3DGSのカメラモデル制約と、3DGUTがどう解決するか
- gsplat 1.5.3の主要アップデートと性能改善
- 実際の導入方法と設定例

---

## 従来3DGSの限界：ピンホールカメラ前提

3D Gaussian Splattingの原論文（SIGGRAPH 2023）は、EWA（Elliptical Weighted Average）スプラッティングをベースにしている。この手法は射影変換をアフィン近似（ヤコビアン）で線形化するため、**ピンホールカメラモデルが前提**になっている。

### ピンホール前提で何が困るか

| 現象 | 影響 |
|------|------|
| 魚眼レンズの歪み | 画像周辺部でGaussianの形状が崩れる |
| ローリングシャッター | 動きのあるシーンで幾何学的な歪みが発生 |
| F-Thetaカメラ | 広角イマーシブキャプチャが使えない |
| 反射・屈折 | 非線形光線経路をモデル化できない |

### undistort前処理の問題

従来のワークアラウンドは、歪んだ画像をピンホールモデルにundistortすることだった。

```
[歪み画像] → undistort → [ピンホール画像] → 3DGS学習
```

これには3つの問題がある。

1. **画素補間による画質劣化** — undistort時のバイリニア/バイキュービック補間で細部が失われる
2. **有効画角の縮小** — 180度以上のFOVをピンホールに射影すると情報が大幅に欠落する
3. **前処理パイプラインの複雑化** — カメラモデルごとにundistortロジックを実装する必要がある

---

## 3DGUTの解決策：Unscented Transformで非線形射影をサポート

3DGUT（3D Gaussian Unscented Transform）は、NVIDIAがCVPR 2025でOral発表した手法だ。

### 核心アイデア

EWAスプラッティングのヤコビアン線形化を、**Unscented Transform（UT）**に置き換える。

```
従来（EWA）:
  3D Gaussian → ヤコビアンで線形近似 → 2D Gaussian
  ※線形近似なのでピンホール前提

3DGUT:
  3D Gaussian → Sigma点を生成 → 各Sigma点を非線形射影 → 2D Gaussianを再推定
  ※任意の射影関数を適用可能
```

### Unscented Transformとは

Unscented Kalman Filter（UKF）に由来する手法で、確率分布を代表する少数の**Sigma点**を選択し、非線形関数を通した後の分布を再推定する。

3DGSの文脈では：

1. 3D GaussianからSigma点（代表点）を生成
2. 各Sigma点に**任意の射影関数**を適用して画像平面に投影
3. 投影されたSigma点から2D Gaussianを再推定

射影関数が線形であれば従来のEWAと等価になり、非線形（魚眼、F-Theta等）でも正確に動作する。

### ヤコビアン不要の利点

従来のFisheyeGSのような手法は、特定のカメラモデルに対するヤコビアンを手動で導出する必要があった。カメラモデルが変わればヤコビアンを再導出しなければならない。

3DGUTはSigma点を射影関数に通すだけなので、**カメラモデルに依存しない汎用的な実装**になっている。

---

## 魚眼200度でも安定した品質

実画像での評価論文（2025年）では、180度を超えるFOVの魚眼画像で3DGUTとFisheyeGSを比較している。

| 指標 | 3DGUT | FisheyeGS |
|------|-------|-----------|
| SSIM（周辺部） | 高い | 低下が顕著 |
| LPIPS（周辺部） | 安定 | 劣化 |
| Gaussians数 | **0.38M** | 1.07M |
| 200度FOV | 安定動作 | 品質低下 |

3DGUTはFisheyeGSの**半分以下のGaussians数**で、より高い知覚品質を達成している。画像周辺部（歪みが最大の領域）での品質差が特に顕著だ。

---

## gsplat 1.5.3への統合

gsplatのコアメンテナであるRuilong Liが、3DGUTをgsplatにネイティブ実装した。

### 有効化方法

```python
from gsplat import rasterization

# 3DGUTを有効化
rendered = rasterization(
    means=means,
    quats=quats,
    scales=scales,
    opacities=opacities,
    colors=colors,
    viewmats=viewmats,
    Ks=Ks,
    width=width,
    height=height,
    # 3DGUT設定
    with_ut=True,        # Unscented Transformを使用
    with_eval3d=True,    # 3D空間でGaussian応答を評価
)
```

### 魚眼カメラの設定

```python
rendered = rasterization(
    ...,
    camera_model="fisheye",     # 魚眼カメラモデル
    radial_coeffs=radial_coeffs,  # 放射歪みパラメータ
    with_ut=True,
    with_eval3d=True,
)
```

COLMAPで推定された歪みパラメータをそのまま渡すだけでよい。undistort処理は不要。

### F-Thetaカメラの設定

```python
rendered = rasterization(
    ...,
    camera_model="ftheta",        # F-Thetaカメラモデル
    ftheta_coeffs=ftheta_coeffs,  # F-Theta歪み係数
    with_ut=True,
    with_eval3d=True,
)
```

F-Thetaカメラは広角・イマーシブキャプチャシステムで使われるモデルだ。

---

## gsplat 1.5.3のその他の主要アップデート

3DGUT統合以外にも、gsplat 1.5.3には実用上重要な改善が含まれている。

### Arbitrary Batching

複数シーン・複数視点のバッチレンダリングが1パスで可能になった。

```
従来: 1シーン × N視点のバッチ
1.5.3: M シーン × N視点のバッチ（任意の組み合わせ）
```

大規模なデータパイプラインや、マルチシーン学習で効果を発揮する。

### Fused Bilagrid

Bilateral Guided Radiance Field Processing（SIGGRAPH 2024）のフュージョン実装。

| 指標 | 改善 |
|------|------|
| 学習時間 | **14.7%高速** |
| VRAM使用量 | **26%削減** |

Bilateral Gridによるフォトメトリック補正は、nerfstudioで最も有用な機能の一つだ。そのCUDAフュージョン版は、実用上の大きな改善になる。

### コンパイル速度改善（1.5.0〜）

gsplat 1.5.0でコードリファクタリングによりコンパイル時間が3.5倍高速化された。

```
gsplat 1.4: 4分19秒
gsplat 1.5: 1分22秒
```

CUDAカスタムカーネルのコンパイルは開発体験を大きく左右するため、この改善は地味ながら重要だ。

---

## Eagle（LiDAR+4カメラ）パイプラインとの親和性

3DMakerPro Eagle（LiDAR + 4カメラ）のようなマルチセンサーデバイスでは、3DGUTの恩恵が特に大きい。

### Eagleの構成

```
Eagle:
├── LiDAR → 点群（幾何学）
└── 4カメラ → 画像（テクスチャ）
    ├── カメラ0（広角・歪みあり）
    ├── カメラ1（広角・歪みあり）
    ├── カメラ2（広角・歪みあり）
    └── カメラ3（広角・歪みあり）
```

### 従来の問題

各カメラの魚眼歪みをundistortする前処理が必要だった。4カメラ分の歪み補正は品質劣化の原因になり、カメラ間のキャリブレーション精度にも影響を与えていた。

### 3DGUTによる改善

```
Before:
  [歪み画像×4] → undistort×4 → COLMAP → 3DGS学習

After:
  [歪み画像×4] → COLMAP（歪みパラメータ付き） → 3DGS学習（3DGUT）
```

undistort工程が消えることで：

- 画質劣化がなくなる
- パイプラインが単純化される
- 広角カメラのFOVを最大限活用できる

---

## ライセンス

| コンポーネント | ライセンス |
|--------------|-----------|
| gsplat | Apache 2.0 |
| 3DGUT（gsplat内） | Apache 2.0 |
| 3DGRUT（NVIDIA公式リポジトリ） | Apache 2.0 |

すべて商用利用可能。

---

## まとめ

| 項目 | 詳細 |
|------|------|
| **何が変わったか** | 3DGSが任意のカメラモデル（魚眼、F-Theta、ローリングシャッター）に対応 |
| **技術的な核** | Unscented TransformによるSigma点射影 |
| **実用的な効果** | undistort前処理が不要、広角FOVの活用、パイプライン単純化 |
| **導入方法** | gsplat 1.5.3で `with_ut=True` を指定するだけ |
| **ライセンス** | Apache 2.0（商用利用可能） |

ピンホールカメラ前提という3DGS最大の制約の一つが、3DGUTによって解消された。魚眼カメラやマルチカメラリグを使っている人は、今すぐgsplat 1.5.3を試す価値がある。

---

## 関連記事

- [3DGSラスタライザ比較2026](https://zenn.dev/amabito/articles/3dgs-rasterizer-comparison) - ラスタライザ選定ガイド
- [HyperRasterizer完全解説](https://zenn.dev/amabito/articles/hyper-rasterizer-zenn) - 自作ラスタライザの実装
- [NVIDIAが公開したPPISP](https://zenn.dev/amabito/articles/nvidia-ppisp-3dgs-photometric) - 3DGSの色ズレを物理ベースで解決

---

## 参考

- [3DGUT プロジェクトページ（NVIDIA）](https://research.nvidia.com/labs/toronto-ai/3DGUT/) - デモ動画あり
- [3DGUT 論文（CVPR 2025 Oral）](https://arxiv.org/abs/2412.12507) - arXiv
- [gsplat GitHub](https://github.com/nerfstudio-project/gsplat) - ソースコード
- [gsplat 3DGUT ドキュメント](https://github.com/nerfstudio-project/gsplat/blob/main/docs/3dgut.md) - 統合ガイド
- [NVIDIA 3DGRUT リポジトリ](https://github.com/nv-tlabs/3dgrut) - 公式実装
- [NVIDIA Technical Blog: 3DGUT in gsplat](https://developer.nvidia.com/blog/revolutionizing-neural-reconstruction-and-rendering-in-gsplat-with-3dgut/) - 解説記事

---

ご質問・ご相談はコメント欄へ。
