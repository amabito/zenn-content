---
title: "【有料】3DGS画像前処理完全ガイド：ブラー除去から露出補正まで"
emoji: "🖼️"
type: "tech"
topics: ["3dgs", "画像処理", "python", "opencv", "機械学習"]
published: false
price: 1480
---

# この記事で得られるもの

- 3DGS品質を左右する**画像前処理パイプライン**
- **モーションブラー**の検出と除去（Deblur-GS手法）
- **露出補正**の実装（公式3DGS exposure compensation）
- **RAW現像**のベストプラクティス
- **COLMAP品質向上**のパラメータ設定
- 実際の**Pythonコード**

**対象読者:** 3DGSで高品質なモデルを作りたい人、撮影データの品質に悩んでいる人

---

# 無料記事のおさらい

- 3DGSは画像品質に敏感
- ブラー、露出ムラ、ノイズが品質を劣化させる
- 適切な前処理で大幅な改善が可能

今回は**具体的な処理手法とコード**を解説する。

---

:::message
ここから有料パートです。
:::

# Part 1: 画像品質がなぜ重要か

## 3DGSパイプラインにおける画像の役割

```
入力画像
    ↓ ← ここの品質が全てに影響
COLMAP (SfM)
    ├─ 特徴点抽出
    ├─ マッチング
    └─ カメラポーズ推定
    ↓
3DGS学習
    ├─ 初期点群からガウス生成
    ├─ レンダリング vs 入力画像の比較
    └─ パラメータ最適化
    ↓
出力3Dモデル
```

**画像品質が悪いと:**
- 特徴点が取れない → マッチング失敗
- カメラポーズがずれる → 歪んだ3Dモデル
- 学習時の比較が不正確 → ぼやけたモデル

---

## 品質劣化の3大原因

| 原因 | 影響 | 発生しやすい状況 |
|------|------|----------------|
| モーションブラー | 特徴点抽出失敗、ぼやけ | 手持ち撮影、暗所 |
| 露出ムラ | 色の不整合、アーティファクト | 自動露出、HDRシーン |
| ノイズ | 偽の特徴点、テクスチャ劣化 | 高ISO、暗所 |

---

# Part 2: モーションブラー対策

## ブラー検出

まず画像がブラーしているかを検出する。

```python
import cv2
import numpy as np
from pathlib import Path

def detect_blur(image_path: str, threshold: float = 100.0) -> tuple[bool, float]:
    """
    ラプラシアン分散でブラーを検出

    Args:
        image_path: 画像パス
        threshold: ブラー判定閾値（低いほど厳しい）

    Returns:
        (is_blurry, variance)
    """
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"Cannot read image: {image_path}")

    # ラプラシアンでエッジ検出
    laplacian = cv2.Laplacian(img, cv2.CV_64F)
    variance = laplacian.var()

    is_blurry = variance < threshold
    return is_blurry, variance


def filter_blurry_images(image_dir: str, threshold: float = 100.0) -> list[str]:
    """
    ディレクトリ内のブラー画像をフィルタリング

    Returns:
        シャープな画像のパスリスト
    """
    image_dir = Path(image_dir)
    extensions = {'.jpg', '.jpeg', '.png', '.JPG', '.JPEG', '.PNG'}

    sharp_images = []
    blurry_count = 0

    for img_path in image_dir.iterdir():
        if img_path.suffix not in extensions:
            continue

        is_blurry, variance = detect_blur(str(img_path), threshold)

        if is_blurry:
            print(f"Blurry: {img_path.name} (variance={variance:.1f})")
            blurry_count += 1
        else:
            sharp_images.append(str(img_path))

    print(f"\nTotal: {len(sharp_images)} sharp, {blurry_count} blurry")
    return sharp_images
```

### 使い方

```python
# ブラー画像を除外
sharp_images = filter_blurry_images("./images", threshold=100.0)

# シャープな画像だけをCOLMAPに渡す
```

---

## Deblur-GS手法

2024年に発表されたDeblur-GSは、ブラー画像からでも高品質な3DGSを構築する手法。

### 原理

```
ブラー = シャッター時間中のカメラ移動による複数フレームの合成

解決策:
1. カメラ軌跡をモデル化
2. 軌跡上の複数時点でレンダリング
3. 合成結果とブラー画像を比較
4. 逆算でシャープなシーンを復元
```

### 実装（SpectacularAI版）

```bash
# インストール
git clone https://github.com/SpectacularAI/3dgs-deblur
cd 3dgs-deblur
pip install -e .

# ビデオからの処理（モーションブラー補正）
./process_and_train_video.sh your_video.mp4 --motion-blur
```

### 自前実装のヒント

```python
import torch
import torch.nn.functional as F

def simulate_motion_blur(
    gaussians,
    camera_poses: list[torch.Tensor],
    num_samples: int = 5
) -> torch.Tensor:
    """
    カメラ軌跡に沿った複数レンダリングの合成でブラーをシミュレート

    Args:
        gaussians: 3DGSモデル
        camera_poses: シャッター時間中のカメラポーズリスト
        num_samples: サンプル数

    Returns:
        ブラー画像
    """
    images = []

    for pose in camera_poses:
        # 各ポーズでレンダリング
        rendered = render(gaussians, pose)
        images.append(rendered)

    # 平均合成（単純なモーションブラーモデル）
    blurred = torch.stack(images).mean(dim=0)

    return blurred


def optimize_with_blur_model(
    gaussians,
    blurry_image: torch.Tensor,
    initial_pose: torch.Tensor,
    num_iterations: int = 1000
):
    """
    ブラーモデルを考慮した最適化
    """
    # カメラ軌跡パラメータ（学習可能）
    trajectory_params = torch.nn.Parameter(
        torch.zeros(6)  # 6DoF: tx, ty, tz, rx, ry, rz
    )

    optimizer = torch.optim.Adam(
        list(gaussians.parameters()) + [trajectory_params],
        lr=0.001
    )

    for i in range(num_iterations):
        optimizer.zero_grad()

        # 軌跡からポーズリストを生成
        poses = generate_trajectory_poses(initial_pose, trajectory_params)

        # ブラーシミュレーション
        rendered_blur = simulate_motion_blur(gaussians, poses)

        # 損失計算
        loss = F.mse_loss(rendered_blur, blurry_image)

        loss.backward()
        optimizer.step()
```

---

## ローリングシャッター補正

CMOSセンサー特有の歪み。上から順にスキャンするため、動くと歪む。

### SpectacularAI版

```bash
# ローリングシャッターモード
./process_and_train_video.sh your_video.mp4 --rolling-shutter
```

### 補正の原理

```
通常: 全ピクセルが同時刻
ローリングシャッター: 行ごとに時刻がずれる

解決:
1. 各行の露光時刻を推定
2. 時刻ごとのカメラポーズを計算
3. 行ごとに異なるポーズでレンダリング
```

---

# Part 3: 露出補正

## 問題: 自動露出による色ムラ

スマートフォンや一般的なカメラは自動露出。

```
明るい方向 → 暗く撮影
暗い方向 → 明るく撮影

→ 同じ物体が画像ごとに異なる色に見える
→ 3DGSが混乱
```

## 公式3DGS exposure compensation

公式リポジトリに実装済み。

### 有効化

```bash
python train.py \
    -s your_data \
    --exposure_lr_init 0.001 \
    --exposure_lr_final 0.0001 \
    --exposure_lr_delay_steps 5000 \
    --exposure_lr_delay_mult 0.001 \
    --train_test_exp
```

### 原理

```
各画像に対してアフィン変換を学習:
output_color = a * rendered_color + b

a, b は画像ごとに異なる学習パラメータ
```

### 自前実装

```python
import torch
import torch.nn as nn

class ExposureCompensation(nn.Module):
    """
    画像ごとの露出補正パラメータ
    """
    def __init__(self, num_images: int):
        super().__init__()
        # 各画像に対するスケール（a）とバイアス（b）
        self.scales = nn.Parameter(torch.ones(num_images, 3))   # RGB
        self.biases = nn.Parameter(torch.zeros(num_images, 3))  # RGB

    def forward(self, rendered: torch.Tensor, image_idx: int) -> torch.Tensor:
        """
        露出補正を適用

        Args:
            rendered: レンダリング結果 [H, W, 3]
            image_idx: 画像インデックス

        Returns:
            補正後の画像
        """
        scale = self.scales[image_idx].view(1, 1, 3)
        bias = self.biases[image_idx].view(1, 1, 3)

        return rendered * scale + bias


class GaussianTrainer:
    def __init__(self, num_images: int):
        self.exposure_comp = ExposureCompensation(num_images)
        # ... その他の初期化

    def compute_loss(
        self,
        gaussians,
        camera,
        gt_image: torch.Tensor,
        image_idx: int
    ) -> torch.Tensor:
        # レンダリング
        rendered = render(gaussians, camera)

        # 露出補正
        rendered_compensated = self.exposure_comp(rendered, image_idx)

        # 損失計算
        loss = F.l1_loss(rendered_compensated, gt_image)

        return loss
```

---

## 撮影時の露出固定

最も確実な方法は**撮影時に露出を固定**すること。

### iPhoneでの設定

1. カメラアプリで被写体をタップ
2. 露出を調整（スライダー）
3. 長押しで「AE/AFロック」を有効化

### Androidでの設定

Pro/マニュアルモードでISO、シャッター速度、絞りを固定。

### ドローンでの設定

DJI機の場合:
1. カメラ設定 → 自動 → マニュアル
2. ISO: 100-400
3. シャッター速度: 1/500以上（ブラー防止）
4. ホワイトバランス: 固定（太陽光 or カスタム）

---

# Part 4: RAW現像

## なぜRAWか

| フォーマット | ビット深度 | ダイナミックレンジ | 後処理耐性 |
|------------|----------|-----------------|----------|
| JPEG | 8bit | 狭い | 低 |
| RAW | 12-14bit | **広い** | **高** |

3DGSは「同じ物体は同じ色」という前提で学習する。

RAWから統一的に現像することで、色の一貫性を確保できる。

## RAW現像パイプライン

```python
import rawpy
import numpy as np
from pathlib import Path

def process_raw_for_3dgs(
    raw_path: str,
    output_path: str,
    white_balance: str = "camera",  # "camera", "daylight", "auto"
    exposure_correction: float = 0.0,
    denoise: bool = True
) -> None:
    """
    3DGS向けRAW現像

    Args:
        raw_path: RAWファイルパス
        output_path: 出力JPEGパス
        white_balance: ホワイトバランス設定
        exposure_correction: 露出補正（EV単位）
        denoise: ノイズ除去の有無
    """
    with rawpy.imread(raw_path) as raw:
        # 現像パラメータ
        params = {
            "use_camera_wb": white_balance == "camera",
            "use_auto_wb": white_balance == "auto",
            "bright": 2 ** exposure_correction,  # 露出補正
            "no_auto_bright": True,  # 自動明るさ調整を無効化
            "output_bps": 8,  # 8bit出力
            "demosaic_algorithm": rawpy.DemosaicAlgorithm.AHD,
        }

        if white_balance == "daylight":
            params["use_camera_wb"] = False
            params["use_auto_wb"] = False
            # 日光のRGB倍率（概算）
            params["user_wb"] = [1.0, 1.0, 1.0, 1.0]

        rgb = raw.postprocess(**params)

    # ノイズ除去（オプション）
    if denoise:
        import cv2
        rgb = cv2.fastNlMeansDenoisingColored(rgb, None, 3, 3, 7, 21)

    # 保存
    import imageio
    imageio.imwrite(output_path, rgb, quality=95)


def batch_process_raw(
    raw_dir: str,
    output_dir: str,
    **kwargs
) -> list[str]:
    """
    ディレクトリ内のRAWファイルを一括現像
    """
    raw_dir = Path(raw_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_extensions = {'.arw', '.cr2', '.cr3', '.nef', '.dng', '.raf', '.orf'}

    output_paths = []

    for raw_path in raw_dir.iterdir():
        if raw_path.suffix.lower() not in raw_extensions:
            continue

        output_path = output_dir / f"{raw_path.stem}.jpg"

        try:
            process_raw_for_3dgs(str(raw_path), str(output_path), **kwargs)
            output_paths.append(str(output_path))
            print(f"Processed: {raw_path.name}")
        except Exception as e:
            print(f"Error processing {raw_path.name}: {e}")

    return output_paths
```

### 使い方

```python
# 全RAWファイルを統一設定で現像
output_images = batch_process_raw(
    raw_dir="./raw_images",
    output_dir="./processed_images",
    white_balance="daylight",  # 統一ホワイトバランス
    exposure_correction=0.0,   # 露出補正なし
    denoise=True               # 軽いノイズ除去
)
```

---

# Part 5: COLMAP最適化

## 品質向上パラメータ

### 特徴点抽出

```bash
colmap feature_extractor \
    --database_path database.db \
    --image_path images/ \
    --ImageReader.single_camera 1 \
    --SiftExtraction.max_image_size 4096 \
    --SiftExtraction.max_num_features 16384 \
    --SiftExtraction.first_octave 0 \
    --SiftExtraction.num_octaves 4
```

| パラメータ | デフォルト | 推奨 | 効果 |
|-----------|----------|------|------|
| max_image_size | 3200 | 4096 | 高解像度対応 |
| max_num_features | 8192 | 16384 | 特徴点増加 |
| first_octave | -1 | 0 | 小さい特徴を無視 |

### マッチング

```bash
colmap exhaustive_matcher \
    --database_path database.db \
    --SiftMatching.guided_matching 1 \
    --SiftMatching.max_num_matches 32768
```

### バンドル調整

```bash
colmap mapper \
    --database_path database.db \
    --image_path images/ \
    --output_path sparse/ \
    --Mapper.ba_refine_focal_length 1 \
    --Mapper.ba_refine_principal_point 1 \
    --Mapper.ba_refine_extra_params 1
```

---

## MASt3R-SfM（2025年新手法）

スパースビューやノイジーなデータセットでCOLMAPより高精度。

### 特徴

- 意味的/幾何学的に関連するビューを自動選択
- カジュアルに撮影した画像セットでも動作
- 下流の3DGS/NeRF品質が向上

### 使い方

```bash
# インストール（要CUDA）
git clone https://github.com/naver/mast3r
cd mast3r
pip install -e .

# 実行
python demo.py --images your_images/
```

---

# Part 6: 統合パイプライン

## 完全な前処理フロー

```python
from pathlib import Path
import subprocess

class PreprocessingPipeline:
    """
    3DGS向け画像前処理パイプライン
    """

    def __init__(self, input_dir: str, output_dir: str):
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        raw_processing: bool = True,
        blur_filter: bool = True,
        blur_threshold: float = 100.0,
        colmap_quality: str = "high"
    ) -> Path:
        """
        パイプライン実行

        Returns:
            COLMAP出力ディレクトリ
        """
        # Step 1: RAW現像（該当する場合）
        if raw_processing:
            print("Step 1: RAW Processing...")
            images_dir = self.output_dir / "images"
            batch_process_raw(
                str(self.input_dir),
                str(images_dir),
                white_balance="daylight",
                denoise=True
            )
        else:
            images_dir = self.input_dir

        # Step 2: ブラーフィルタリング
        if blur_filter:
            print("Step 2: Blur Filtering...")
            sharp_images = filter_blurry_images(
                str(images_dir),
                threshold=blur_threshold
            )
            # シャープな画像だけを別ディレクトリにコピー
            filtered_dir = self.output_dir / "filtered_images"
            filtered_dir.mkdir(exist_ok=True)
            for img_path in sharp_images:
                import shutil
                shutil.copy(img_path, filtered_dir)
            images_dir = filtered_dir

        # Step 3: COLMAP実行
        print("Step 3: Running COLMAP...")
        sparse_dir = self.output_dir / "sparse"
        self._run_colmap(images_dir, sparse_dir, colmap_quality)

        print(f"Done! Output: {sparse_dir}")
        return sparse_dir

    def _run_colmap(
        self,
        images_dir: Path,
        output_dir: Path,
        quality: str
    ):
        """COLMAP実行"""
        db_path = self.output_dir / "database.db"

        # 特徴点抽出
        feature_cmd = [
            "colmap", "feature_extractor",
            "--database_path", str(db_path),
            "--image_path", str(images_dir),
            "--ImageReader.single_camera", "1",
        ]

        if quality == "high":
            feature_cmd.extend([
                "--SiftExtraction.max_image_size", "4096",
                "--SiftExtraction.max_num_features", "16384",
            ])

        subprocess.run(feature_cmd, check=True)

        # マッチング
        match_cmd = [
            "colmap", "exhaustive_matcher",
            "--database_path", str(db_path),
        ]
        subprocess.run(match_cmd, check=True)

        # マッピング
        output_dir.mkdir(parents=True, exist_ok=True)
        map_cmd = [
            "colmap", "mapper",
            "--database_path", str(db_path),
            "--image_path", str(images_dir),
            "--output_path", str(output_dir),
        ]
        subprocess.run(map_cmd, check=True)


# 使用例
if __name__ == "__main__":
    pipeline = PreprocessingPipeline(
        input_dir="./raw_captures",
        output_dir="./preprocessed"
    )

    sparse_dir = pipeline.run(
        raw_processing=True,
        blur_filter=True,
        blur_threshold=80.0,
        colmap_quality="high"
    )

    # 3DGS学習
    print(f"\n3DGS学習コマンド:")
    print(f"python train.py -s {sparse_dir.parent} --exposure_lr_init 0.001")
```

---

# Part 7: トラブルシューティング

## 症状別対処法

| 症状 | 原因 | 対処法 |
|------|------|--------|
| ぼやけたモデル | ブラー画像 | blur_threshold を上げる |
| 色ムラ | 露出変動 | exposure compensation 有効化 |
| 穴だらけ | 特徴点不足 | COLMAP max_num_features 増加 |
| 歪んだ形状 | ポーズ推定失敗 | 画像追加、MASt3R-SfM試行 |
| ノイズ多い | 高ISO撮影 | RAW現像時にdenoise |
| floater多い | 動体混入 | 撮影時間帯変更、マスク処理 |

---

# まとめ

## チェックリスト

- [ ] 撮影時: 露出固定、低ISO、高シャッター速度
- [ ] RAW現像: 統一ホワイトバランス、軽いノイズ除去
- [ ] ブラー除去: variance < 100 の画像を除外
- [ ] COLMAP: 高品質パラメータ設定
- [ ] 3DGS: exposure compensation 有効化

## 期待される改善

| 処理 | PSNR改善 |
|------|---------|
| ブラーフィルタリング | +1〜3 dB |
| 露出補正 | +0.5〜2 dB |
| RAW統一現像 | +0.5〜1 dB |
| COLMAP高品質設定 | +0.5〜1 dB |
| **合計** | **+2.5〜7 dB** |

**前処理で品質は大きく変わる。**

---

# 関連記事

## 3DGSシリーズ
- [NeRF vs 3DGS（無料版）](https://zenn.dev/amabito/articles/nerf-vs-3dgs-2026)
- [HyperRasterizer完全解説](https://zenn.dev/amabito/articles/hyper-rasterizer-zenn)
- [建設現場×3DGS](https://zenn.dev/amabito/articles/construction-3dgs)

## CUDA開発シリーズ
- [CUDA warp同期の罠](https://zenn.dev/amabito/articles/cuda-warp-sync-trap)
- [CUDAメモリ管理の罠](https://zenn.dev/amabito/articles/cuda-memory-management)
