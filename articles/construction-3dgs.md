---
title: "ドローン15分で現場が3D化：建設×3DGSの始め方"
emoji: "🏗️"
type: "tech"
topics: ["3DGS", "建設", "デジタルツイン", "ドローン", "測量"]
published: true
published_at: "2026-01-07 12:00"
---

# 結論から言う

**ドローン撮影15分、処理30分で現場が3Dモデルになる。**

「現場の3D化に1日かかる」「レーザースキャナは高すぎる」

こんな悩み、ありませんか？私は建設コンサルタントとして、この問題を3DGSで解決した。

**この記事で得られること:**
- 建設現場で3DGSを使う具体的な手順
- ドローン撮影のコツ
- 発注者に見せるための納品形式

---

# 建設現場の現状

## 従来の3Dスキャン

| 手法 | 時間 | コスト | 品質 |
|------|------|--------|------|
| 地上型レーザースキャナ | 1日/現場 | 高（機材数百万円） | 高 |
| 写真測量（SfM） | 数時間/現場 | 中 | 中 |
| ドローン測量 | 1-2時間/現場 | 中 | 中〜高 |

問題: 時間がかかる、コストが高い、リアルタイム性がない。

## 3DGSの可能性

```
ドローン撮影（15分）
    ↓
3DGS処理（30分）
    ↓
リアルタイム3Dビュー
```

**現場に戻る前に3Dモデルが完成する。**

---

# 3DGSとは（建設向け解説）

## 点群との違い

| 項目 | 点群（LiDAR） | 3DGS |
|------|--------------|------|
| データ形式 | 点の集合 | 楕円体（Gaussian）の集合 |
| レンダリング | 点を描画 | 滑らかに補間 |
| 見た目 | 粒状感がある | 写真のように自然 |
| ファイルサイズ | 大（数GB） | 中（数百MB） |

## 建設での活用シーン

1. **施工管理**: 出来形をリアルタイムで確認
2. **安全管理**: 危険箇所の可視化
3. **発注者への説明**: 写真より分かりやすい3Dモデル
4. **維持管理**: 構造物の経年変化を記録

---

# 実践: ドローン撮影から3DGSまで

## 1. ドローン撮影

```
機材: DJI Mavic 3 Pro
設定:
- 高度: 50m
- オーバーラップ: 80%
- サイドラップ: 60%
- 撮影間隔: 2秒
```

**ポイント**: 3DGSはテクスチャ情報を使うので、影の少ない曇りの日が最適。

## 2. 画像の整理

```bash
# 撮影枚数の確認
ls images/*.jpg | wc -l
# → 200-500枚程度が目安

# ブレている画像を除去
# （手動または自動スクリプト）
```

## 3. カメラ位置の推定

COLMAP（Structure from Motion）を使用。

```bash
colmap feature_extractor --database_path database.db --image_path images
colmap exhaustive_matcher --database_path database.db
colmap mapper --database_path database.db --image_path images --output_path sparse
```

## 4. 3DGS学習

```bash
python train.py -s ./data/construction_site -m ./output
```

30分〜1時間で3Dモデルが完成。

## 5. ビューアで確認

生成された`.ply`ファイルを3DGSビューアで開く。

- [SuperSplat](https://supersplat.io/)（Web）
- [PlayCanvas](https://playcanvas.com/)（Web）
- 自作ビューア（IGS Desktop）

---

# 課題と解決策

## 課題1: 動く物体

建設現場には重機や作業員がいる。動く物体は3DGSで「ゴースト」になる。

**解決策**:
- 早朝・休憩時間に撮影
- 後処理でfloater（浮遊物）を除去

## 課題2: 反射面

ガラス、水たまり、金属面は3DGSが苦手。

**解決策**:
- 反射面を避けて撮影
- 曇りの日に撮影（反射が減る）

## 課題3: スケール

3DGSは相対的なスケールしか分からない。

**解決策**:
- GCP（Ground Control Point）を設置
- 既知の寸法の物体を入れる（メジャー、コーンなど）

---

# 商用利用の注意

## ライセンス問題

オリジナルの3DGS実装は**商用利用不可**（Inria/Max-Planckライセンス）。

建設業務で使うなら、商用OKな実装が必要:
- gsplat（Apache 2.0）
- HyperRasterizer（Apache 2.0、自作）

## データの取り扱い

- 現場の位置情報が含まれる → 顧客の許可を得る
- 作業員の顔が映る → プライバシーに配慮

---

# まとめ

建設×3DGSの可能性:

1. **スピード**: 従来の1/10の時間で3D化
2. **コスト**: 高価な機材不要、ドローン1台でOK
3. **品質**: 写真のようにリアルな3Dモデル
4. **活用**: 施工管理、安全管理、発注者説明

**建設業界のDX、3DGSが加速させる。**

---

# 関連記事

## 3DGSシリーズ
- [HyperRasterizer完全解説](https://zenn.dev/amabito/articles/hyper-rasterizer-zenn) - 4169FPS達成の独自ラスタライザ
- [3DGS商用化ガイド](https://zenn.dev/amabito/articles/3dgs-commercial-guide) - ライセンス問題の整理
- **この記事** → 建設現場での活用事例

## CUDA開発シリーズ
- [RTX 5090 CUDA最適化](https://zenn.dev/amabito/articles/rtx5090-cuda-optimization) - Blackwell世代の最適化
- [CUDAメモリ管理の罠](https://zenn.dev/amabito/articles/cuda-memory-management) - メモリプール実装
- [PyTorch CUDA拡張](https://zenn.dev/amabito/articles/pytorch-cuda-extension) - Windowsビルドの罠

---

詳細なワークフローと品質向上テクニックは有料記事で解説しています。

https://zenn.dev/amabito/articles/construction-3dgs-paid
