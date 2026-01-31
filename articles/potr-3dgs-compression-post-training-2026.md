---
title: "POTR：Post-Training 3DGS圧縮で2-4倍軽量化【2026年最新】"
emoji: "🗜️"
type: "tech"
topics: ["3DGS", "圧縮", "最適化", "機械学習", "POTR"]
published: true
published_at: "2026-02-17 21:00"
---

# 結論から言う

**POTR（Post-Training 3DGS Compression）は、2026年1月21日にarXivで公開された、学習済み3D Gaussian Splattingモデルを後から圧縮する手法。** 再学習なしで2-4倍のスプラット削減、1.5-2倍の推論高速化を実現。ストレージとメモリの課題を解決する。

**対象読者:**
- 3DGSを本番環境にデプロイしている人
- モバイル・Web向けに3DGSを最適化したい人
- ストレージコストを削減したいサービス運営者

**この記事で得られること:**
- POTRが実現する圧縮率と速度向上の具体的数値
- Post-Training圧縮の仕組みと従来手法との違い
- 実装のポイントと適用シーン

---

## 3DGSの「重さ」問題

3D Gaussian Splattingは高速レンダリングを実現したが、**ストレージとメモリの消費量が大きい**。

### 典型的な3DGSモデルのサイズ

| シーン | スプラット数 | ファイルサイズ | メモリ使用量 |
|--------|------------|------------|------------|
| **小規模オブジェクト** | 50万〜100万 | 200MB〜500MB | 1GB〜2GB |
| **部屋・建物内部** | 200万〜500万 | 1GB〜2.5GB | 4GB〜8GB |
| **屋外大規模シーン** | 1000万〜 | 5GB〜20GB | 16GB〜64GB |

**問題の具体例:**

- Webブラウザで3DGSを表示 → 数GBのダウンロードは現実的でない
- モバイルアプリ → メモリ制限（iOS 3GB、Android端末で様々）
- クラウドストレージ → シーン数千個で数TB〜数十TB

---

## POTRのアプローチ：3段階圧縮

POTRは**Post-Training**、つまり学習済みモデルに対して適用する圧縮手法。

```
[学習済み3DGSモデル]
         ↓
   (1) Pruning（スプラット削除）
         ↓
   (2) SH係数の再計算
         ↓
   (3) オプション：ファインチューニング
         ↓
   [圧縮モデル]
```

### (1) 効率的Pruning

**従来手法の問題:**

Naive Pruning（不透明度しきい値ベース）は、視覚品質への影響を考慮せずにスプラットを削除する。

```python
# Naive Pruning（従来）
mask = gaussians.opacity < threshold  # 不透明度が低い → 削除
gaussians = gaussians[~mask]
```

結果：重要なスプラットまで削除され、品質劣化が大きい。

**POTRの解決策：重要度ベースPruning**

| ステップ | 処理 | 目的 |
|---------|------|------|
| 1. 影響度計算 | 各スプラットの削除がレンダリング品質に与える影響を計算 | 削除しても影響が小さいスプラットを特定 |
| 2. ランキング | 影響度でソート | 削除優先順位を決定 |
| 3. 削除 | 影響度が低いものから順に削除 | 品質を保ちながら削減 |

**技術的ポイント:**

修正ラスタライザで**全スプラットの影響度を並列計算**。従来の逐次的pruningと比べて大幅に高速化。

```python
# POTR Pruning
importance_scores = modified_rasterizer.compute_importance(gaussians, views)
# 全スプラットの影響度を並列計算（CUDA）

ranked_indices = torch.argsort(importance_scores)
keep_ratio = 0.3  # 70%削除
keep_indices = ranked_indices[-int(len(gaussians) * keep_ratio):]
gaussians = gaussians[keep_indices]
```

---

### (2) SH係数の再計算によるエントロピー削減

3D Gaussian Splattingは、色を**球面調和関数（Spherical Harmonics, SH）**で表現する。

**問題:**

学習時のSH係数は、圧縮観点では非効率な値になっている。

- AC係数（高次成分）のスパース性が低い（約70%がゼロでない）
- エントロピーが高い → 圧縮効率が悪い

**POTRの解決策:**

Pruning後、SH係数を**再計算**してエントロピーを削減。

| 指標 | 学習済みモデル | POTR後 |
|------|--------------|--------|
| **AC係数スパース性** | 70% | 97% |
| **エントロピー** | 高 | 低 |
| **圧縮率** | 通常 | **1.5-2.5倍向上** |

技術的詳細:

```python
# SH係数の再計算
def recompute_sh_coefficients(gaussians, views):
    """
    Pruning後のGaussiansに対してSH係数を再計算
    - 各視点でレンダリング
    - 誤差を最小化するSH係数を最適化（閉じた形式の解）
    """
    for view in views:
        rendered = rasterizer(gaussians, view)
        gt = view.image

        # SH係数のみを最適化（位置・スケール・回転は固定）
        sh_new = solve_least_squares_sh(
            rendered, gt, gaussians.means, view.camera
        )
        gaussians.sh_coefficients = sh_new

    return gaussians
```

---

### (3) オプション：ファインチューニング

Pruning + SH再計算だけでも十分な品質だが、さらに品質を上げたい場合はファインチューニング。

```python
# 短時間のファインチューニング（数分〜数十分）
optimizer = torch.optim.Adam(gaussians.parameters(), lr=1e-4)

for iteration in range(1000):  # 短時間
    loss = reconstruction_loss(gaussians, views)
    loss.backward()
    optimizer.step()
```

**効果:**

- PSNR: +0.3〜0.8 dB
- 学習時間: 元の学習の5-10%程度

---

## パフォーマンス比較

### 圧縮率

| 手法 | スプラット削減率 | ファイルサイズ削減 | PSNR低下 |
|------|-----------------|------------------|----------|
| **Naive Pruning** | 50% | 30-40% | -2.5 dB |
| **LightGaussian** | 60% | 45-55% | -1.2 dB |
| **Compact3DGS** | 70% | 55-65% | -0.8 dB |
| **POTR（本手法）** | **75-80%** | **65-75%** | **-0.3 dB** |

### 推論速度

| 手法 | FPS（RTX 4090） | メモリ使用量 | ロード時間 |
|------|----------------|------------|-----------|
| **オリジナル** | 100 FPS | 4GB | 5秒 |
| **Naive Pruning** | 130 FPS | 2.5GB | 3秒 |
| **Compact3DGS** | 150 FPS | 2GB | 2.5秒 |
| **POTR** | **180-200 FPS** | **1.2GB** | **1.5秒** |

**なぜ速い？**

1. スプラット数が少ない → タイルへの割り当てが高速
2. メモリフットプリントが小さい → キャッシュヒット率向上
3. SH係数のスパース性が高い → 計算量削減

---

## 実装のポイント

### 重要度の計算方法

```python
def compute_splat_importance(gaussians, views):
    """
    各スプラットの削除がPSNRに与える影響を計算
    """
    importance = torch.zeros(len(gaussians))

    for view in views:
        # 通常レンダリング
        img_full = rasterizer(gaussians, view)

        # 各スプラットを削除してレンダリング（並列計算）
        imgs_ablated = rasterizer.render_with_ablation(
            gaussians, view, compute_per_splat=True
        )

        # PSNR差を重要度とする
        for i in range(len(gaussians)):
            psnr_drop = compute_psnr(img_full, imgs_ablated[i])
            importance[i] += psnr_drop

    return importance / len(views)
```

### 修正ラスタライザのキーアイデア

通常のラスタライザ:

```
各ピクセル = Σ (各スプラットの寄与)
```

修正ラスタライザ:

```
各ピクセル = Σ (各スプラットの寄与)
             ↓
各スプラットの削除時の影響 = そのスプラットなしでレンダリング
             ↓
全スプラット分を**並列**に計算（CUDA最適化）
```

---

## 誰に影響があるか

| ユースケース | 影響度 | 理由 |
|------------|--------|------|
| **Webブラウザ3DGS** | 最高 | ファイルサイズ削減 → ダウンロード時間短縮 |
| **モバイルアプリ** | 最高 | メモリ削減 → 低スペック端末でも動作 |
| **クラウドストレージ** | 高 | ストレージコスト削減（数百〜数千シーン） |
| **リアルタイムAR/VR** | 高 | 推論高速化 → フレームレート向上 |
| **デスクトップアプリ** | 中 | ロード時間短縮 |

---

## 従来手法との違い

### LightGaussianとの比較

| 観点 | LightGaussian | POTR |
|------|--------------|------|
| **アプローチ** | 学習中にpruning | Post-Training |
| **既存モデル対応** | 不可（再学習必要） | 可能 |
| **圧縮率** | 中 | 高 |
| **品質** | 良い | より良い |

### Compact3DGSとの比較

| 観点 | Compact3DGS | POTR |
|------|-------------|------|
| **SH削減** | 高次SH削除のみ | SH再計算でエントロピー削減 |
| **推論速度** | 改善あり | より高速 |
| **適用コスト** | 再学習必要 | 数分〜数十分 |

---

## 技術的課題

1. **動的シーンへの対応** — 4DGS（時間軸あり）への拡張は未検証
2. **ビュー依存の最適化** — 特定視点に偏ったpruningの回避方法
3. **量子化との組み合わせ** — FP16/INT8量子化と組み合わせた場合の効果

---

## まとめ

| 項目 | 詳細 |
|------|------|
| **何が新しいか** | Post-Training圧縮、重要度ベースPruning、SH再計算 |
| **何が嬉しいか** | 既存モデルを2-4倍軽量化、1.5-2倍高速化 |
| **誰が使うべきか** | Web・モバイルで3DGSをデプロイする全ての人 |
| **公開日** | 2026年1月21日（arXiv） |
| **コード公開** | 未確認 |

3DGSの「重さ」が本番環境での最大の障壁だった。POTRはそれを解決する実用的なアプローチを提示した。今後、Web・モバイルでの3DGS普及が加速する。

---

## 関連記事

- [無料] [3DGS圧縮手法比較](https://zenn.dev/amabito/articles/3dgs-compression-comparison) - 各種圧縮手法の比較
- [無料] [3DGSストリーミング配信](https://zenn.dev/amabito/articles/3dgs-streaming) - Web配信の実践
- [無料] [WebGPU×3DGS実装ガイド](https://zenn.dev/amabito/articles/hyper-viewer-webgpu) - ブラウザ実装
- [無料] [3DGS本番デプロイ2026](https://zenn.dev/amabito/articles/3dgs-production-deploy-2026) - 本番環境構築

---

## 参考

- [POTR論文](https://arxiv.org/abs/2601.14821v1) - arXiv 2026/01/21
- [LightGaussian](https://arxiv.org/abs/2311.17245) - 学習中pruning（先行手法）
- [Compact3DGS](https://arxiv.org/abs/2311.13681) - SH削減（先行手法）
- [3D Gaussian Splatting原論文](https://arxiv.org/abs/2308.04079) - SIGGRAPH 2023

---

ご質問・ご相談はコメント欄へ。
