---
title: "NVIDIAが公開したPPISP：3DGSの色ズレを物理ベースで解決する新手法"
emoji: "📷"
type: "tech"
topics: ["3DGS", "CUDA", "NVIDIA", "ComputerVision", "画像処理"]
published: true
---

# 結論から言う

**NVIDIAが2026年1月にリリースしたPPISP（Physically-Plausible ISP）は、3D Gaussian Splattingの「色ズレ問題」を物理ベースで解決するプラグインモジュール。** Apache 2.0、CUDAカーネル実装、gsplat/3DGRUT統合予定。マルチカメラ構成で3DGSを使うなら必須の技術になる。

**対象読者:**
- 3D Gaussian Splattingで実世界シーンを再構成している人
- マルチカメラ撮影で色ずれ・floater問題に悩んでいる人
- gsplat/nerfstudioを使っている人

**この記事で得られること:**
- PPISPが解決する問題と4つの物理モジュールの仕組み
- 従来手法（Bilateral Grid、GLO等）との違い
- 実装の組み込み方法とコード例

---

## マルチカメラ3DGSの「色ズレ問題」とは

3D Gaussian Splattingで実世界のシーンを再構成する際、マルチカメラ構成では避けられない問題がある。

**各カメラのISP（Image Signal Processor）が独立動作する。**

つまり、同じシーンを撮影しても：

- カメラAは暖色寄り、カメラBは寒色寄り
- カメラAは明るめ、カメラBは暗め
- レンズ周辺部が暗くなる度合いがカメラごとに異なる

これらの不一致が3DGS学習に与える影響は深刻だ。

| 症状 | 原因 |
|------|------|
| **floater（浮遊アーティファクト）** | 色の不一致を表面の違いとして学習 |
| **色むら** | カメラ間のホワイトバランス差 |
| **ボケた再構成** | 露出差で同一点の輝度が矛盾 |
| **新規視点でのブレ** | 学習時のper-frame補正が推論時に使えない |

---

## PPISPのアプローチ：物理ベース分解

従来手法はデータ駆動で「なんとなく色を合わせる」方向だった。PPISPは発想が異なる。

**カメラのISPパイプラインを物理的に分解し、各コンポーネントを個別にモデル化する。**

### 4つの物理モジュール

| モジュール | 粒度 | モデル化する現象 |
|-----------|------|---------------|
| **Exposure Compensation** | per-frame | オート露出・照明変動による明るさの変動 |
| **Vignetting** | per-camera | レンズの光学特性による周辺光量落ち |
| **Color Correction** | per-frame | ホワイトバランスドリフト・色かぶり |
| **Camera Response Function** | per-camera | ISPの非線形トーンマッピング（gamma等） |

ポイントは**per-camera**と**per-frame**の分離。

- ビネッティングとCRFはレンズ・ISP固有 → カメラが変わらない限り不変
- 露出と色補正はフレームごとに変動 → シーンの照明条件に依存

この分離により、各パラメータに**物理的な意味**が生まれる。

---

## 2段階学習 + コントローラ蒸留

PPISPの学習は2段階で行われる。

```
[Stage 1: 0-80%]
  シーン表現（Gaussians） + PPISP 4モジュール → 共同最適化

[Stage 2: 80-100%]
  シーン表現 + PPISPパラメータ → FREEZE
  コントローラネットワーク → 学習
```

### コントローラの役割

Stage 2で学習するコントローラは、通常カメラの**オート露出・オートホワイトバランス**に相当する。

レンダリングされたラディアンス画像を入力として、per-frameの露出・色補正パラメータを予測する。

**これの何が嬉しいか：**

推論時（新規視点レンダリング時）にper-frameパラメータが不要になる。コントローラが自動で適切な補正を予測してくれる。

---

## 従来手法との比較

### Bilateral Grid（SIGGRAPH 2024）との違い

Bilateral Guided Radiance Field Processing（SIGGRAPH/TOG 2024）は、ISPの効果をlocally-affineなbilateral gridで近似する手法。

| 観点 | Bilateral Grid | PPISP |
|------|---------------|-------|
| **モデリング** | データ駆動のlocally-affine変換 | 物理ベースのISPコンポーネント分解 |
| **解釈可能性** | グリッド値に物理的意味なし | 各パラメータ＝ISPの物理量 |
| **推論時パラメータ** | per-viewグリッドが必要 | コントローラが自動予測 |
| **用途** | 静的シーン再構成 + ユーザー編集 | マルチカメラ動画の物理的補正 |
| **バックボーン** | ZipNeRF依存 | **任意のradiance fieldにプラグイン可能** |

### GLO（Global Latent Optimization）との違い

per-imageの潜在ベクトルで色を合わせるGLOは：

- 物理的解釈がない
- 新規視点への汎化が弱い
- 学習するパラメータがimage数に比例して増える

PPISPはカメラ数に比例するパラメータ＋コントローラで、スケーラブル。

---

## 実装：コード例

PPISPはpipでインストールでき、既存パイプラインに組み込める。

### インストール

```bash
pip install ppisp @ git+https://github.com/nv-tlabs/ppisp.git@v1.0.0 --no-build-isolation
```

`--no-build-isolation`はCUDAカーネルをローカルのPyTorchバージョンに合わせてビルドするため。

### 基本的な使い方

```python
from ppisp import PPISP

# 初期化（カメラ3台、500フレーム）
ppisp = PPISP(num_cameras=3, num_frames=500)
optimizers = ppisp.create_optimizers()
schedulers = ppisp.create_schedulers(optimizers, max_iters)

# Training loop
for iteration in range(max_iters):
    # 1. Gaussian Splattingでレンダリング
    rgb_raw = rasterizer.render(gaussians, camera)

    # 2. PPISPでフォトメトリック補正
    rgb_out = ppisp(
        rgb_raw, pixel_coords,
        resolution=(W, H),
        camera_idx=camera.id,
        frame_idx=frame.id
    )

    # 3. Loss計算（補正後の画像とGTを比較）
    loss = reconstruction_loss(rgb_out, gt_image)
    loss += ppisp.get_regularization_loss()

    # 4. 逆伝播
    loss.backward()
```

### 新規視点レンダリング

```python
# frame_idx=-1 でコントローラを使用
rgb_novel = ppisp(
    rgb_raw, pixel_coords,
    resolution=(W, H),
    camera_idx=camera.id,
    frame_idx=-1  # コントローラが自動予測
)
```

---

## 技術的ポイント

### なぜ「物理ベース」が重要か

従来のアフィン変換（`corrected = A @ rgb + b`）でも色補正はできる。しかし：

1. **ビネッティングは空間依存** — 画像中心と周辺で異なる補正が必要。アフィン変換はピクセル位置に依存しない
2. **CRFは非線形** — gamma曲線のような非線形変換はアフィン変換では近似できない
3. **パラメータの分離** — 物理分解により、カメラ固有（交換しても変わらない）とフレーム固有（照明で変わる）を明確に分離できる

### CUDAカーネル実装

PPISPの補正処理は微分可能なCUDAカーネルとして実装されている。Pythonで同等の処理を書く場合と比べて：

- 学習ループへのオーバーヘッドが最小
- GPU上で全ピクセルを並列処理
- 逆伝播もCUDAで実装（torch.autograd.Functionベース）

---

## 誰に影響があるか

| ユースケース | 影響度 | 理由 |
|------------|--------|------|
| **マルチカメラリグ**（自動運転、スタジオ等） | 高 | カメラ間差が最大の問題 |
| **動画からの3DGS** | 高 | フレーム間の露出変動を補正 |
| **ドローン撮影** | 中 | 照明変動が激しい |
| **スマホ1台で撮影** | 低 | カメラ1台なのでカメラ間差なし（ただし露出変動はある） |

---

## まとめ

| 項目 | 詳細 |
|------|------|
| **何が新しいか** | ISPパイプラインの物理分解による色補正 |
| **何が嬉しいか** | floater減少、色一貫性向上、推論時パラメータ不要 |
| **誰が使うべきか** | マルチカメラで3DGSを使う人全員 |
| **ライセンス** | Apache 2.0（商用利用可能） |
| **導入コスト** | `pip install` + 学習ループに数行追加 |

NVIDIAがgsplatと3DGRUTへの公式統合を予定しているため、近い将来nerfstudio経由でも使えるようになるはず。マルチカメラ3DGSの品質を一段上げたいなら、今すぐ試す価値がある。

---

## 関連記事

- [無料] [3DGSラスタライザ比較2026](https://zenn.dev/amabito/articles/3dgs-rasterizer-comparison) - ラスタライザ選定ガイド
- [無料] [CUDA最適化入門](https://zenn.dev/amabito/articles/cuda-optimization-basics) - CUDA開発の基礎
- [無料] [RTX 5090 CUDA最適化ガイド](https://zenn.dev/amabito/articles/rtx5090-cuda-optimization) - Blackwell世代の最適化
- [無料] [NeRF vs 3DGS 2026](https://zenn.dev/amabito/articles/nerf-vs-3dgs-2026) - 最新の比較

---

## 参考

- [PPISP GitHub](https://github.com/nv-tlabs/ppisp) - ソースコード（Apache 2.0）
- [PPISP論文](https://arxiv.org/abs/2601.18336) - arXiv
- [NVIDIA SIL プロジェクトページ](https://research.nvidia.com/labs/sil/projects/ppisp/) - デモ動画あり
- [Bilateral Guided Radiance Field Processing](https://arxiv.org/abs/2406.00448) - 先行手法（SIGGRAPH 2024）
- [3D Gaussian Splatting原論文](https://arxiv.org/abs/2308.04079) - SIGGRAPH 2023

---

ご質問・ご相談はコメント欄へ。
