---
title: "NeRF vs 3DGS：2026年、どちらを選ぶべきか"
emoji: "⚔️"
type: "tech"
topics: ["nerf", "3dgs", "機械学習", "コンピュータグラフィックス", "3d"]
published: true
---

# 結論から言う

**2026年、実用的なプロジェクトには3DGSを選べ。研究や特殊用途ならNeRFも検討。**

3DGS（3D Gaussian Splatting）が登場して3年。NeRF（Neural Radiance Fields）は終わったのか？答えは「No」だが、使い分けが必要だ。

---

# 2026年の状況

## 論文数で見るトレンド

| 技術 | 2024年arxiv論文数 | 2025年arxiv論文数 |
|------|-----------------|-----------------|
| 3DGS | 約800本 | **1,692本** |
| NeRF | - | 減少傾向 |

3DGS関連の論文は**倍増**。業界の関心は明らかに3DGSに移っている。

> "I am now 100% convinced that radiance field representations like gaussian splatting are a fundamental imaging medium and that in 2026 we will see an accelerated shift of imaging into 3D."
> — Radiance Fields Newsletter

---

# NeRFとは（おさらい）

2020年にMildenhallらが発表。複数視点の画像からニューラルネットワークで3Dシーンを表現する技術。

```
入力: 複数視点の画像
    ↓
処理: MLPで空間座標→色・密度を学習
    ↓
出力: 任意視点の画像をレンダリング
```

**特徴:**
- **暗黙的表現**: シーンはニューラルネットワークの重みとして表現
- **レイトレーシング**: 各ピクセルごとにレイを飛ばして計算
- **高品質**: 透明物体、反射、影の表現が得意

---

# 3DGSとは（おさらい）

2023年にKerblらがSIGGRAPHで発表。点群を3Dガウス分布として表現し、ラスタライズでレンダリング。

```
入力: 複数視点の画像
    ↓
処理: SfMで点群生成 → 各点をガウス分布に変換
    ↓
出力: ラスタライズで高速レンダリング
```

**特徴:**
- **明示的表現**: シーンは数百万のガウス分布の集合
- **ラスタライズ**: GPUの並列処理を活用
- **高速**: リアルタイムレンダリング（数百〜数千FPS）

---

# 性能比較（2026年時点）

## レンダリング速度

| 技術 | 典型的なFPS | 備考 |
|------|-----------|------|
| NeRF（初期） | 0.1 | 実用不可 |
| Instant-NGP | 30〜60 | ハッシュグリッドで高速化 |
| 3DGS | **100〜1000** | ラスタライズ |
| RadSplat（ハイブリッド） | **900** | NeRF+3DGS |

**3DGSはNeRFより1桁以上速い。**

## 学習時間

| 技術 | 典型的な学習時間 |
|------|---------------|
| NeRF（初期） | 数時間〜1日 |
| Instant-NGP | 数分〜数十分 |
| 3DGS | **数分〜数十分** |

Instant-NGPの登場でNeRFも高速化したが、3DGSと同等レベル。

## メモリ使用量

| 技術 | メモリ特性 |
|------|----------|
| NeRF | 小（ネットワーク重みのみ） |
| 3DGS | **大**（数百万のガウス分布） |

NeRFのメモリ使用量は3DGSの**1/10**程度。これはNeRFの大きな利点。

## 品質

| 項目 | NeRF | 3DGS |
|------|------|------|
| 一般的なシーン | ◎ | ◎ |
| 透明物体 | ◎ | △ |
| 反射・光沢 | ◎ | △ |
| 動的シーン | △ | ○ |
| 大規模屋外 | △ | △ |

**NeRFは透明物体と反射の表現で優位。**

---

# なぜ3DGSが主流になったか

## 1. 実用速度

NeRFの致命的な弱点は速度だった。研究には使えても、製品には組み込めない。

3DGSはこれを解決した。**リアルタイムレンダリング**ができる。

## 2. 理解しやすい

NeRFは「ニューラルネットワークが何を学んだか」を解釈しにくい。

3DGSは「ここにこういう形のガウスがある」と可視化できる。**デバッグしやすい。**

## 3. 編集可能

NeRFのシーンを編集するのは難しい。ネットワーク全体を再学習する必要がある。

3DGSはガウス分布を直接操作できる。**削除、移動、追加が容易。**

---

# NeRFが今も必要な場面

## 1. メモリ制約がある環境

モバイルデバイスやエッジデバイスでは、数百MBのガウスデータは重すぎる。

NeRFのネットワーク（数十MB）なら搭載できる場合がある。

## 2. 透明物体・反射の表現

ガラス、水、鏡などはNeRFの方が得意。

3DGSで同等の表現をするには追加の工夫が必要。

## 3. 研究用途

NeRFは5年近い研究蓄積がある。派生手法も多い。

- Mip-NeRF: アンチエイリアシング
- NeRF-W: 野外シーン対応
- D-NeRF: 動的シーン
- NeRF++: 大規模シーン

特定の課題に対しては、既存のNeRF派生が最適解の場合もある。

---

# ハイブリッドアプローチ

2026年のトレンドは「NeRFと3DGSの融合」だ。

## RadSplat（Google）

NeRFで学習した情報を3DGSに変換。

- NeRFの品質 + 3DGSの速度
- **900 FPS**を達成
- NeRF/3DGSハイブリッドの先駆け

## NeRF Is a Valuable Assistant for 3DGS（ICCV 2025）

NeRFを「補助」として使い、3DGSの初期化や密度化を改善。

**両者は競合ではなく補完関係。**

---

# 2026年の最新研究動向

## NeRF側の進化

| 技術 | 概要 |
|------|------|
| HR-NeRF | ハイライト・反射の改善（PSNR 3-5dB向上） |
| DT-NeRF | Diffusion + Transformer統合 |
| Instant-NGP派生 | さらなる高速化 |

## 3DGS側の進化

| 技術 | 概要 |
|------|------|
| Compact3D | 40-50倍圧縮、2-3倍高速化 |
| Deblur-GS | モーションブラー対応 |
| BARD-GS | 動的シーン対応（CVPR 2025） |
| E-3DGS | イベントカメラ統合 |

## 共通の課題

- 大規模屋外シーン
- 動的シーンのリアルタイム処理
- 計算リソースの効率化

---

# 選択フローチャート

```
リアルタイム性が必要？
├─ Yes → 3DGS
└─ No
    ├─ メモリ制約がある？
    │   ├─ Yes → NeRF
    │   └─ No
    │       ├─ 透明/反射物体が多い？
    │       │   ├─ Yes → NeRF or ハイブリッド
    │       │   └─ No → 3DGS
    │       └─
    └─
```

## 具体的なユースケース

| ユースケース | 推奨 | 理由 |
|------------|------|------|
| Webビューア | 3DGS | 速度が命 |
| VR/AR | 3DGS | 90FPS必須 |
| 映画VFX | NeRF or ハイブリッド | 品質重視 |
| モバイルアプリ | NeRF（圧縮版） | メモリ制約 |
| 建設・測量 | 3DGS | 実用速度と編集性 |
| 文化財デジタル化 | 3DGS | 速度と品質のバランス |
| 製品カタログ | 3DGS | 編集・更新のしやすさ |

---

# 今後の予測

## 短期（2026-2027）

- 3DGSが実用分野を席巻
- NeRFは研究・特殊用途に特化
- ハイブリッド手法が増加

## 中期（2028-2029）

- 両者の良いとこ取りした統合技術が登場
- デバイス側での処理（エッジAI）が進化
- スマートフォンでのリアルタイム3DGS

## 長期（2030〜）

- 「NeRF vs 3DGS」という議論自体が古くなる
- 新しい表現形式が登場する可能性
- 3Dキャプチャがカメラの標準機能に

---

# まとめ

| 観点 | NeRF | 3DGS |
|------|------|------|
| 速度 | △ 遅い | ◎ 高速 |
| メモリ | ◎ 軽量 | △ 重い |
| 品質（一般） | ◎ | ◎ |
| 品質（透明/反射） | ◎ | △ |
| 編集性 | △ | ◎ |
| 2026年の主流 | 研究用途 | **実用分野** |

**迷ったら3DGS。特別な理由があればNeRF。**

---

# 関連記事

## 3DGSシリーズ
- [HyperRasterizer完全解説](https://zenn.dev/amabito/articles/hyper-rasterizer-zenn) - 商用利用可能な高速ラスタライザ
- [3DGS商用化ガイド](https://zenn.dev/amabito/articles/3dgs-commercial-guide) - ライセンス問題の整理
- [建設現場×3DGS](https://zenn.dev/amabito/articles/construction-3dgs) - 実用事例

## CUDA開発シリーズ
- [RTX 5090 CUDA最適化](https://zenn.dev/amabito/articles/rtx5090-cuda-optimization) - GPU世代別最適化
- [CUDA warp同期の罠](https://zenn.dev/amabito/articles/cuda-warp-sync-trap) - デッドロック回避

---

画像前処理テクニック、ブラー除去、品質向上の詳細は有料記事で解説しています。

https://zenn.dev/amabito/articles/3dgs-image-preprocessing-paid

---

# 参考

- [A Survey of 3D Reconstruction: NeRF to 3DGS](https://pmc.ncbi.nlm.nih.gov/articles/PMC12473764/)
- [NVIDIA GTC 2025: From NeRF to 3DGS](https://www.nvidia.com/en-us/on-demand/session/gtc25-dlit71553/)
- [Radiance Fields Newsletter](https://radiancefields.substack.com/)
- [NeRF Is a Valuable Assistant for 3DGS (ICCV 2025)](https://openaccess.thecvf.com/content/ICCV2025/papers/Fang_NeRF_Is_a_Valuable_Assistant_for_3D_Gaussian_Splatting_ICCV_2025_paper.pdf)
- [SpectacularAI 3DGS Deblur](https://spectacularai.github.io/3dgs-deblur/)
