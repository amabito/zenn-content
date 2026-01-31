---
title: "3DGSパイプライン完全ガイド：写真からWeb 3Dモデルまで"
emoji: "📸"
type: "tech"
topics: ["3DGS", "WebGPU", "Python", "CUDA", "パイプライン"]
published: true
published_at: "2026-01-02 18:00"
---

# 結論から言う

**スマホで撮った写真から、ブラウザで閲覧できる3Dモデルを生成するパイプラインを構築した。**

```
写真（30-100枚）→ カメラ推定 → 3DGS学習 → 圧縮 → Web公開
所要時間: 約10分（GPU使用時）
```

全て商用利用可能な技術で構成。この記事では、各ステップの技術と実行方法を解説する。

---

# パイプライン全体像

```
[撮影]          スマホで対象を撮影（1-3分）
   │
   ▼
[前処理]        フレーム抽出、ブレ除去
   │
   ▼
[SfM]           COLMAP でカメラ位置推定（2-3分）
   │
   ▼
[学習]          HyperSplat で3DGS学習（3-5分）
   │
   ▼
[最適化]        Pruning、量子化で圧縮
   │
   ▼
[エクスポート]  PLYファイル出力
   │
   ▼
[表示]          HyperViewer でブラウザ表示
```

---

# Step 1: 撮影

## 良い撮影のコツ

```
推奨:
├── 対象の周りを360°回る
├── 上・中・下の3段階の高さで撮影
├── 一定の距離を保つ
├── 十分な照明
└── 30-100枚程度

避ける:
├── 手ブレ
├── 極端な逆光
├── 動く被写体（人、車の往来）
├── 透明・鏡面が大部分のオブジェクト
└── テクスチャのない面（白い壁だけ等）
```

## 動画からフレーム抽出

動画で撮影した場合、フレームを画像に変換する。

```bash
# ffmpegでフレーム抽出（2FPSで間引き）
ffmpeg -i video.mp4 -vf "fps=2" frames/frame_%04d.jpg
```

**ポイント**: 全フレーム（30FPS）は不要。2FPSで十分な重なりが得られる。

---

# Step 2: カメラ位置推定（SfM）

## COLMAPによる推定

```bash
# COLMAPインストール
# Windows: https://colmap.github.io/ からバイナリ取得
# Linux: apt install colmap

# 自動推定（最も簡単な方法）
colmap automatic_reconstructor \
    --workspace_path ./workspace \
    --image_path ./frames
```

## 出力

```
workspace/
├── sparse/0/
│   ├── cameras.bin    # カメラ内部パラメータ
│   ├── images.bin     # カメラ外部パラメータ（位置・姿勢）
│   └── points3D.bin   # 初期点群
└── dense/             # （使わない）
```

## COLMAP以外の選択肢

| ツール | ライセンス | 特徴 |
|--------|-----------|------|
| COLMAP | BSD | 最も安定、デファクト |
| hloc | Apache 2.0 | 特徴点マッチング改良 |
| OpenMVG | MPL 2.0 | 軽量 |

---

# Step 3: 3DGS学習

## HyperSplatによる学習

```python
from hyper_rasterizer import HyperRasterizer
# ... 省略（詳細はHyperSplat記事参照）

# 基本的な学習ループ
for iteration in range(30000):
    image = rasterizer.forward(...)
    loss = l1_loss(image, gt_image) + 0.2 * ssim_loss(image, gt_image)
    loss.backward()
    optimizer.step()
```

## 学習設定のポイント

| 設定 | 推奨値 | 理由 |
|------|--------|------|
| イテレーション | 30,000 | 十分な収束 |
| 初期Gaussian数 | SfM点群数 | 自然な初期化 |
| 密度化開始 | 500イテレーション | 安定してから開始 |
| 密度化終了 | 15,000イテレーション | 後半は微調整のみ |
| SH degree | 3 | 視点依存の色変化 |

## 学習時間の目安

| シーン規模 | GPU | 時間 |
|-----------|-----|------|
| 小（30枚） | RTX 3090 | 5分 |
| 中（100枚） | RTX 3090 | 15分 |
| 大（300枚） | RTX 3090 | 45分 |
| 小（30枚） | RTX 5090 | 2分 |
| 中（100枚） | RTX 5090 | 5分 |

---

# Step 4: 圧縮・最適化

## なぜ圧縮が必要か

```
学習直後のPLY:
├── 200K Gaussians × 62属性 × 4bytes = 約50MB
└── Webで配信するには大きすぎる

目標: 5MB以下
```

## 圧縮手法

### Pruning（不要Gaussianの削除）

```python
# opacity が低いGaussianを削除
mask = opacities > 0.01  # 閾値
means3d = means3d[mask]
# ... 他の属性も同様にフィルタ

# 効果: 30-50%のGaussianを削除
```

### SH degree削減

```python
# SH degree 3 → 1 に削減
# 色の視点依存性は減るが、サイズ大幅削減
shs = shs[:, :4]  # degree 1: 4係数のみ

# 効果: SH部分が75%削減
```

### 量子化

```python
# FP32 → FP16
means3d = means3d.half()
# FP32 → INT8（さらに積極的）
scales_uint8 = ((scales - min_val) / (max_val - min_val) * 255).byte()

# 効果: 50-75%のサイズ削減
```

## 圧縮結果の例

| 手法 | サイズ | 品質影響 |
|------|--------|----------|
| 圧縮なし | 50MB | - |
| Pruning | 30MB | 低opacity除去のみ |
| + SH削減 | 12MB | 視点依存色が減少 |
| + 量子化 | **4MB** | ほぼ知覚不能 |

---

# Step 5: Web公開

## HyperViewerで表示

```bash
# ローカルで確認
git clone https://github.com/amabito/hyper-viewer.git
cd hyper-viewer
npm install
npm run dev
# → http://localhost:5000 でPLYファイルをドロップ
```

## GitHub Pagesで公開

```
1. HyperViewerをフォーク
2. data/ にPLYファイルを配置
3. GitHub Pagesを有効化
4. URLを共有
```

## 自分のWebサイトに埋め込む

```html
<!-- iframe埋め込み -->
<iframe
  src="https://your-site.github.io/hyper-viewer/?model=car.ply"
  width="800"
  height="600"
  frameborder="0">
</iframe>
```

---

# 全パイプラインの自動化

## スクリプト例

```bash
#!/bin/bash
# 3DGS Pipeline: 写真 → Web公開

INPUT_DIR=$1
OUTPUT_DIR=$2

echo "=== Step 1: Frame extraction ==="
# 動画の場合
if [ -f "$INPUT_DIR/video.mp4" ]; then
    mkdir -p "$INPUT_DIR/frames"
    ffmpeg -i "$INPUT_DIR/video.mp4" -vf "fps=2" "$INPUT_DIR/frames/frame_%04d.jpg"
    INPUT_DIR="$INPUT_DIR/frames"
fi

echo "=== Step 2: SfM (COLMAP) ==="
colmap automatic_reconstructor \
    --workspace_path "$OUTPUT_DIR/colmap" \
    --image_path "$INPUT_DIR"

echo "=== Step 3: 3DGS Training ==="
python train.py \
    --source "$OUTPUT_DIR/colmap/sparse/0" \
    --output "$OUTPUT_DIR/model" \
    --iterations 30000

echo "=== Step 4: Compression ==="
python compress.py \
    --input "$OUTPUT_DIR/model/point_cloud.ply" \
    --output "$OUTPUT_DIR/compressed.ply" \
    --target_size_mb 5

echo "=== Done! ==="
echo "PLY: $OUTPUT_DIR/compressed.ply"
echo "View: drag & drop to https://amabito.github.io/hyper-viewer/"
```

---

# よくある問題と対策

## COLMAP が失敗する

```
原因:
├── 写真の重なりが不足
├── テクスチャが少ない（白い壁等）
├── 照明が不均一
└── 動いている物体が写っている

対策:
├── 撮影枚数を増やす（50枚以上）
├── テクスチャのある場所で撮影
├── 均一な照明を確保
└── 動く物体を避ける
```

## 学習結果にノイズが多い

```
原因:
├── SfMの点群が不正確
├── 密度化パラメータが不適切
├── 学習イテレーションが不足
└── 画像にブレがある

対策:
├── ブレた画像を除外
├── 密度化閾値を上げる（0.0002以上）
├── イテレーションを増やす（30000以上）
└── Pruningで低opacity Gaussianを除去
```

## Webで表示が遅い

```
原因:
├── PLYファイルが大きすぎる
├── Gaussian数が多すぎる
├── WebGPU非対応ブラウザ
└── GPUが低スペック

対策:
├── 圧縮パイプラインを実行
├── Pruningでgaussian数を削減（100K以下推奨）
├── Chrome/Edge最新版を使用
└── .splatフォーマットに変換（より小さい）
```

---

# まとめ

| ステップ | ツール | 所要時間 |
|---------|--------|----------|
| 撮影 | スマホ | 1-3分 |
| SfM | COLMAP | 2-3分 |
| 学習 | HyperSplat | 3-5分 |
| 圧縮 | Python | 1分 |
| 表示 | HyperViewer | 即座 |
| **合計** | | **約10分** |

**スマホで撮影して10分後にはブラウザで3Dモデルが見れる。**

---

# 関連記事

## 3DGSシリーズ
- [HyperRasterizer完全解説](https://zenn.dev/amabito/articles/hyper-rasterizer-zenn) - 4169FPS達成
- [ブラウザで3DGS表示](https://zenn.dev/amabito/articles/hyper-viewer-webgpu) - WebGPUビューア
- [HyperRasterizerでトレーニング](https://zenn.dev/amabito/articles/hyper-rasterizer-training) - 学習統合
- [3DGS圧縮技術比較](https://zenn.dev/amabito/articles/3dgs-compression-comparison) - 圧縮手法
- [3DGSストリーミング](https://zenn.dev/amabito/articles/3dgs-streaming) - 配信技術

## 業界応用
- [3DGSを商用利用したい人へ](https://zenn.dev/amabito/articles/3dgs-commercial-guide) - ライセンス
- [建設現場×3DGS](https://zenn.dev/amabito/articles/construction-3dgs) - 建設
- [不動産×3DGS](https://zenn.dev/amabito/articles/realestate-3dgs) - 不動産
- [EC×3DGS](https://zenn.dev/amabito/articles/ecommerce-3dgs-product-visualization) - EC商品3D化

## 技術詳細
- [RTX 5090 CUDA最適化](https://zenn.dev/amabito/articles/rtx5090-cuda-optimization) - GPU最適化
- [CUDAメモリ管理の罠](https://zenn.dev/amabito/articles/cuda-memory-management) - メモリ管理
