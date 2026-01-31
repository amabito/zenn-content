---
title: "3DGS学習フレームワークを10回作り直した：HyperSplat開発記録"
emoji: "📓"
type: "tech"
topics: ["3DGS", "PyTorch", "機械学習", "CUDA", "開発記録"]
published: true
published_at: "2026-01-14 07:00"
---

# 結論から言う

**3D Gaussian Splatting（3DGS）の学習フレームワークを、v2からv22まで10回以上作り直した。**

途中でスクリプトが消失し、Gaussianが爆発し、PSNRが10dB劣化した。しかし最終的に、**商用利用可能な独自フレームワーク**を完成させた。

この記事では、各バージョンで何を試し、何が失敗し、何を学んだかを記録する。

**この記事で得られること:**
- 3DGS学習でよくある失敗パターン
- 品質向上のためのアプローチ
- スクリプト喪失からの教訓

---

# HyperSplatとは

HyperSplatは、3D Gaussian Splattingの学習フレームワーク。

```
HyperRasterizerファミリー:
├── HyperRasterizer  → CUDAラスタライザ（4169 FPS）
├── HyperSplat       → 学習フレームワーク ← これ
└── HyperViewer      → WebGPUビューア
```

**全て商用利用可能（Apache 2.0 / 独自実装）。**

---

# バージョン進化の記録

## 全体タイムライン

| Version | 状態 | 主な試み |
|---------|------|----------|
| v2 | 完了 | 基本実装、Densification動作確認 |
| v4 | 中止 | Gaussian爆発（1.5M超過） |
| v6 | スキップ | v7へ方針変更 |
| v7 | 完了 | EDGS-style（密度化なし） |
| v8 | 完了 | 新技術導入 |
| v9 | 完了 | High-Speed Optimization |
| v10 | 喪失 | **スクリプト消失** |
| v11 | 喪失 | スクリプト消失、異常出力 |
| v12 | 完了 | 5品質技術 + 4高速化技術 |
| v14-v20 | 開発 | PSNR劣化問題との戦い |
| v22 | 完了 | **最終版、77 it/s** |

---

# 失敗1: Gaussian爆発（v4）

## 症状

```
Iteration 0:    50K Gaussians
Iteration 3000: 200K Gaussians
Iteration 5000: 800K Gaussians
Iteration 7000: 1,500K Gaussians ← メモリ不足で停止
```

Densification（密度化）が制御不能になり、Gaussian数が爆発的に増加。

## 原因

```
密度化の条件が緩すぎた:
├── 勾配閾値: 0.0001（低すぎ）
├── 密度化間隔: 50イテレーションごと（頻繁すぎ）
└── 最大Gaussian制限: なし
```

## 学び

- **密度化は両刃の剣**: 品質向上にも、破壊にもなる
- 最大Gaussian数のハードリミットは必須
- 勾配閾値は控えめに設定（0.0002以上を推奨）

---

# 失敗2: スクリプト消失事件（v10-v11）

## 何が起きたか

PC再構築時に、Claude Codeのメモリ上で直接実行していたスクリプトが失われた。

```
消失したもの:
├── train_hypersplat_v10.py（ファイル未保存）
├── train_hypersplat_v11.py（ファイル未保存）
└── 各種設定値（記録なし）
```

## v11の出力だけが残っていた

```
v11:       408KB → 明らかに小さい（異常）
v11_fix:   10MB  → サイズは正常だが品質不明
v11_quality: 49MB → ノイズ・色が濃い
```

スクリプトがないため、同じ結果を再現する手段がなかった。

## 対策

それ以降のルール:

```
絶対に守ること:
├── 必ずローカルファイルとして保存してから実行
├── 設定はconfig.jsonとして出力ディレクトリに保存
└── CLAUDE.MDに進捗を記録
```

**教訓: コードは必ずファイルに保存する。メモリ上の実行だけでは再現性がない。**

---

# 品質改善: v12の独自技術群

v12では、v11の品質問題を解決するために複数の独自技術を導入した。

## アプローチの方向性

大きく分けて2つの方向で改善を行った。

### 品質向上

3DGS学習で発生する典型的な品質問題に対して、それぞれ独自の正則化・フィルタリング手法を開発した。

```
対処した問題:
├── 空間に浮遊するノイズGaussian
├── 色の不自然さ
├── 複数視点での不整合
├── アーティファクト
└── 幾何的な位置ずれ
```

いずれも損失関数への正則化項の追加、または学習中の動的なGaussian制御で解決している。

### 高速化

学習の後半で不要な計算を削減する仕組みを導入した。

```
基本的な考え方:
├── すでに収束したGaussianの計算を省略
├── 寄与の小さいGaussianの更新を間引く
└── 各Gaussianに適した学習率を適用
```

**効果: 品質を維持しつつ、学習後半の計算量を大幅に削減。**

具体的な手法の詳細は非公開。

---

# 失敗3: PSNR 10dB劣化（v14-v20）

## 症状

```
v12: PSNR 28.5 dB（良好）
v14: PSNR 18.2 dB（-10 dB！）
v16: PSNR 19.1 dB
v18: PSNR 17.8 dB
v20: PSNR 20.3 dB
```

v12からv14以降で、画質が大幅に劣化。何を試しても改善しない。

## 調査過程

```
試したこと:
├── 学習率の調整 → 改善なし
├── 損失関数の変更 → 改善なし
├── Densification設定の変更 → 改善なし
├── SH degreeの変更 → 改善なし
├── Backward passのデバッグ → 正常
└── ???
```

## 原因: max_screen_size

```python
# v14で追加した一見無害な設定
max_screen_size = 20  # スクリーン上20ピクセル以上のGaussianを制限

# 実はこれが原因:
# 近景のGaussianが制限され、ディテールが失われる
# → PSNR 10dB劣化
```

**たった1つのパラメータ変更が、10dBの品質差を生んだ。**

## 解決

```python
# ❌ 問題のある設定
max_screen_size = 20

# ✅ 修正: 制限を緩和
max_screen_size = 0  # 制限なし
```

## 教訓

- **パラメータ変更は1つずつ**: 複数の変更を同時に行うと原因特定が困難
- **品質メトリクスの自動記録**: 毎回PSNRを記録し、劣化を即座に検出
- **「無害そうな」設定こそ危険**: max_screen_sizeは性能最適化のために追加したが、品質に壊滅的影響

---

# 最終版: v22

## スペック

| 項目 | 値 |
|------|-----|
| 学習速度 | 77 it/s |
| PSNR | 28+ dB |
| ラスタライザ | HyperRasterizer |
| ライセンス | 商用利用可能 |

## v22で到達した構成

```
HyperSplat v22:
├── ラスタライザ: HyperRasterizer (Apache 2.0)
├── 品質: 独自の正則化・フィルタリング技術群
├── 高速化: 収束検出ベースの計算削減
├── 損失: L1 + SSIM + LPIPS(間引き)
├── Densification: 適応的閾値 + ハードリミット
└── max_screen_size: 0（制限なし）
```

---

# 全バージョンの教訓まとめ

| 失敗 | 原因 | 対策 |
|------|------|------|
| Gaussian爆発 | 密度化条件が緩すぎ | ハードリミット + 閾値調整 |
| スクリプト消失 | ファイル未保存 | **必ずファイル保存** |
| PSNR劣化 | max_screen_size=20 | パラメータは1つずつ変更 |
| 色が濃い | 正則化なし | 独自正則化導入 |
| ノイズ | 浮遊Gaussian | 独自フィルタリング導入 |
| 勾配爆発 | clip_grad_normなし | grad clipping追加 |
| LPIPS低下 | 毎回VGG実行 | 100回ごとに制限 |

---

# 3DGS学習のベストプラクティス

## 絶対に守ること

1. **スクリプトをファイルに保存**してから実行
2. **設定をJSON出力**して再現性を確保
3. **PSNRを毎回記録**して品質を追跡
4. **パラメータは1つずつ変更**
5. **Densificationにハードリミット**を設ける

## やらない方がいいこと

1. メモリ上でスクリプトを直接実行
2. 複数パラメータの同時変更
3. max_screen_sizeの過度な制限
4. 毎イテレーションでLPIPS計算
5. Densificationの閾値を低くしすぎる

---

# 関連記事

## HyperRasterizerシリーズ
- [HyperRasterizer完全解説](https://zenn.dev/amabito/articles/hyper-rasterizer-zenn) - 4169FPS達成
- [HyperRasterizerでトレーニング](https://zenn.dev/amabito/articles/hyper-rasterizer-training) - ラスタライザ統合
- [ブラウザで3DGS表示](https://zenn.dev/amabito/articles/hyper-viewer-webgpu) - WebGPUビューア

## 3DGSシリーズ
- [3DGSを商用利用したい人へ](https://zenn.dev/amabito/articles/3dgs-commercial-guide) - ライセンス問題
- [3DGS圧縮技術比較](https://zenn.dev/amabito/articles/3dgs-compression-comparison) - 圧縮手法

## CUDA開発シリーズ
- [CUDAメモリ管理の罠](https://zenn.dev/amabito/articles/cuda-memory-management) - メモリ管理
- [CUDA warp同期の罠](https://zenn.dev/amabito/articles/cuda-warp-sync-trap) - デッドロック回避
