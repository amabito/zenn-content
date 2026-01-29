---
title: "【有料】建設現場3DGS実践ガイド：品質向上と商用ワークフロー"
emoji: "🔥"
type: "tech"
topics: ["3DGS", "建設", "デジタルツイン", "ドローン", "測量"]
published: true
price: 1480
---

# この記事で得られるもの

- 建設現場に特化した**撮影ノウハウ**
- **品質向上テクニック**（floater除去、色補正）
- 商用利用可能な**完全ワークフロー**
- 発注者向けの**納品形式**

**対象読者:** 建設・土木業界の人、3Dスキャンを業務に活かしたい人

---

# 無料記事のおさらい

- ドローン撮影 → COLMAP → 3DGS で現場を3D化
- 動く物体、反射面、スケールに注意
- 商用利用にはApache 2.0ライセンスの実装が必要

今回は**実践的なノウハウ**を解説する。

---

:::message
ここから有料パートです。
:::

# 撮影計画

## 現場タイプ別の撮影パターン

### 橋梁

```
パターン: 上空周回 + 橋下斜め
高度: 30m（上空）、10m（橋下）
枚数: 300-500枚
ポイント: 橋脚、桁下を重点的に
```

### 道路

```
パターン: 縦断飛行 + 横断オーバーラップ
高度: 50m
枚数: 200-400枚
ポイント: 舗装面の反射に注意
```

### 建築

```
パターン: 周回飛行 + 上空
高度: 建物高 × 1.5
枚数: 400-600枚
ポイント: 窓ガラスを避ける
```

## 撮影チェックリスト

```markdown
□ 天候確認（曇り推奨、雨天中止）
□ 風速確認（5m/s以下）
□ GCP設置（最低4点）
□ スケール参照物（メジャー、コーン）
□ 動く物体の排除（重機停止、作業員退避）
□ 飛行許可確認
□ バッテリー充電確認
```

---

# 品質向上テクニック

## 1. Floater（浮遊物）除去

3DGSでよく発生する問題: 空中に浮かぶ「ゴミ」のようなGaussian。

### 原因

- 動く物体（作業員、重機）
- 鳥、虫
- レンズの汚れ

### 解決: Adaptive Floater Suppression

```python
def remove_floaters(gaussians, k=20, threshold=0.1):
    """
    近傍密度が低いGaussianを除去
    """
    from sklearn.neighbors import NearestNeighbors

    positions = gaussians['xyz']

    # k近傍を計算
    nn = NearestNeighbors(n_neighbors=k)
    nn.fit(positions)
    distances, _ = nn.kneighbors(positions)

    # 平均距離が大きい = 孤立している = floater
    mean_distances = distances.mean(axis=1)
    threshold_distance = np.percentile(mean_distances, 95) * threshold

    valid_mask = mean_distances < threshold_distance
    return {k: v[valid_mask] for k, v in gaussians.items()}
```

## 2. 色補正

ドローン画像は露出がバラつきがち。

### 解決: Histogram Matching

```python
def match_histogram(images, reference_idx=0):
    """
    全画像のヒストグラムを参照画像に合わせる
    """
    from skimage import exposure

    reference = images[reference_idx]

    corrected = []
    for img in images:
        matched = exposure.match_histograms(img, reference, channel_axis=-1)
        corrected.append(matched)

    return corrected
```

## 3. スケール校正

### GCPを使った校正

```python
def calibrate_scale(model_points, real_points):
    """
    モデル座標と実測座標からスケールを計算

    model_points: 3DGSモデル上のGCP座標 [(x,y,z), ...]
    real_points: 実測座標（測量成果）[(X,Y,Z), ...]
    """
    # モデル上の距離
    model_dist = np.linalg.norm(model_points[1] - model_points[0])

    # 実測距離
    real_dist = np.linalg.norm(real_points[1] - real_points[0])

    # スケール係数
    scale = real_dist / model_dist

    return scale
```

---

# 商用ワークフロー

## 全体フロー

```
1. 事前調査
   └── 現場確認、飛行計画、許可取得

2. 現場作業（半日）
   ├── GCP設置・測量
   ├── ドローン撮影
   └── 撮影確認

3. 処理（1-2日）
   ├── 画像整理・選別
   ├── COLMAP処理
   ├── 3DGS学習
   └── 品質確認・補正

4. 納品
   ├── PLYファイル
   ├── ビューアURL
   └── 報告書
```

## 自動化スクリプト

```python
#!/usr/bin/env python3
"""
建設現場3DGS処理パイプライン
"""

import subprocess
from pathlib import Path

def run_pipeline(input_dir: Path, output_dir: Path):
    # 1. 画像整理
    print("Step 1: Organizing images...")
    organize_images(input_dir / "raw", input_dir / "images")

    # 2. COLMAP
    print("Step 2: Running COLMAP...")
    run_colmap(input_dir / "images", output_dir / "sparse")

    # 3. 3DGS学習
    print("Step 3: Training 3DGS...")
    run_3dgs_training(input_dir, output_dir / "3dgs")

    # 4. 品質向上
    print("Step 4: Post-processing...")
    remove_floaters(output_dir / "3dgs" / "point_cloud.ply")

    # 5. ビューア用変換
    print("Step 5: Converting for viewer...")
    convert_for_viewer(output_dir / "3dgs", output_dir / "viewer")

    print("Done!")

def organize_images(raw_dir, output_dir):
    """ブレ画像除去、連番リネーム"""
    import cv2

    output_dir.mkdir(parents=True, exist_ok=True)
    images = sorted(raw_dir.glob("*.jpg"))

    idx = 0
    for img_path in images:
        img = cv2.imread(str(img_path))
        if not is_blurry(img):
            new_path = output_dir / f"image_{idx:04d}.jpg"
            cv2.imwrite(str(new_path), img)
            idx += 1

    print(f"  Kept {idx}/{len(images)} images")

def is_blurry(image, threshold=100):
    """ラプラシアン分散でブレ検出"""
    import cv2
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    variance = cv2.Laplacian(gray, cv2.CV_64F).var()
    return variance < threshold

def run_colmap(image_dir, output_dir):
    """COLMAP SfM処理"""
    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = output_dir / "database.db"

    subprocess.run([
        "colmap", "feature_extractor",
        "--database_path", str(db_path),
        "--image_path", str(image_dir)
    ])

    subprocess.run([
        "colmap", "exhaustive_matcher",
        "--database_path", str(db_path)
    ])

    subprocess.run([
        "colmap", "mapper",
        "--database_path", str(db_path),
        "--image_path", str(image_dir),
        "--output_path", str(output_dir)
    ])

def run_3dgs_training(input_dir, output_dir):
    """3DGS学習（HyperSplat使用）"""
    subprocess.run([
        "python", "train_hypersplat.py",
        "-s", str(input_dir),
        "-m", str(output_dir),
        "--iterations", "30000"
    ])
```

---

# 納品形式

## 発注者向けパッケージ

```
deliverable/
├── model/
│   ├── point_cloud.ply      # 3DGSモデル
│   └── cameras.json         # カメラ情報
├── viewer/
│   ├── index.html           # Webビューア
│   └── assets/
├── docs/
│   ├── report.pdf           # 報告書
│   └── calibration.csv      # スケール校正結果
└── raw/
    └── images.zip           # 元画像（オプション）
```

## 簡易ビューア（HTML）

```html
<!DOCTYPE html>
<html>
<head>
    <title>3DGS Viewer - 現場名</title>
    <script src="https://cdn.jsdelivr.net/npm/three@0.150.0/build/three.min.js"></script>
    <script src="splat-viewer.js"></script>
</head>
<body>
    <div id="viewer" style="width:100%; height:100vh;"></div>
    <script>
        const viewer = new SplatViewer('#viewer');
        viewer.load('model/point_cloud.ply');
    </script>
</body>
</html>
```

---

# 料金設定の目安

| 現場規模 | 撮影 | 処理 | 合計 |
|---------|------|------|------|
| 小（500m²以下） | 3万円 | 5万円 | 8万円 |
| 中（500-5000m²） | 5万円 | 10万円 | 15万円 |
| 大（5000m²以上） | 10万円 | 20万円 | 30万円 |

※ドローン飛行許可取得費用は別途

---

# まとめ

建設×3DGSの実践ポイント:

| 項目 | ポイント |
|------|---------|
| 撮影 | 現場タイプ別のパターン、GCP設置 |
| 品質 | floater除去、色補正、スケール校正 |
| ワークフロー | 自動化スクリプトで効率化 |
| 納品 | Webビューア + 報告書 |

**建設DXの第一歩、3DGSで始めよう。**
