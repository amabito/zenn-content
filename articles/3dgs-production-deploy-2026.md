---
title: "3DGS商用化が本格化した2026年：映画・不動産・ゲームの実例"
emoji: "🏭"
type: "tech"
topics: ["3DGS", "GaussianSplatting", "商用化", "WebGPU", "UnrealEngine"]
published: true
published_at: "2026-02-01 12:00"
---

# 結論から言う

**2026年は3D Gaussian Splattingが「研究」から「商用プロダクト」に完全移行した年。映画、不動産、ゲーム、VRの各分野で実例が出揃った。**

「3DGSは面白いけど、商用で使えるの？」

2024年まではこの疑問が妥当だった。2026年、答えは明確に「使える」に変わった。

**対象読者:**
- 3DGSの商用利用を検討している企業・エンジニア
- 3D/XR系のプロダクト開発に関わる人
- 3DGS技術の市場動向を把握したい人

**この記事で得られること:**
- 映画・不動産・ゲーム・VRでの3DGS商用事例
- 主要Webビューアの比較
- 残る技術課題とその対策
- 「どこから始めるか」の判断基準

---

# 映画: 大作映画に3DGSが採用された

## Superman（2026年公開）

初の大型映画でdynamic 3DGSが本格採用された。

```
Superman での3DGS活用:
├── VFXプリビズでの活用
│   ├── 撮影現場のリアルタイム3D化
│   ├── カメラアングルの事前検証
│   └── ライティングシミュレーション
├── dynamic 3DGSの適用
│   ├── 動的シーンの時系列3D再構成
│   ├── アクションシーンのリファレンス
│   └── ポストプロダクションでの素材活用
└── 成果: VFXプリビズ工程の大幅短縮
```

## OctaneRender 2026: Path-traced Gaussian Splatting

OTOYのOctaneRender 2026がpath-traced Gaussian Splattingに対応。

```
OctaneRender 2026:
├── 3DGSデータをそのままレンダリング可能
├── パストレーシングによるフォトリアル品質
├── GI（グローバルイルミネーション）対応
├── 既存ワークフローに統合可能
└── 映画品質のレンダリングが3DGSから直接可能
```

従来は3DGSからメッシュに変換する必要があったが、OctaneRenderにより3DGSデータを直接レンダリングパイプラインに組み込める。

---

# 不動産: スマホ撮影で物件の3D化が当たり前に

## Zillow: SkyTours

Zillowが導入したSkyToursは、航空写真から不動産の外観3Dモデルを自動生成するサービス。

```
SkyTours:
├── データソース: 航空写真 + 衛星画像
├── 処理: クラウドで自動3D再構成
├── 出力: インタラクティブな3Dビューア
├── 規模: 米国の不動産物件に順次適用
└── ユーザー体験: 物件の外観を360度確認可能
```

## Apartments.com: Matterport 3D Exteriors

Apartments.comはMatterportと連携し、3D Exteriorsを導入。

```
Matterport 3D Exteriors:
├── 撮影: スマートフォンで外観を撮影
├── 処理: Matterportのクラウドで3D化
├── 技術: 3DGS + NeRFハイブリッド
├── 出力: Webブラウザで閲覧可能な3Dモデル
└── 導入効果: 内覧前の問い合わせ品質向上
```

## スマホ撮影で対応可能

かつては専用機材（LiDARスキャナ等）が必要だった不動産の3D化が、スマートフォンの撮影だけで対応可能になった。

```
必要な機材の変遷:
├── 2020年: LiDARスキャナ（$50,000〜）
├── 2022年: iPhone LiDAR + 専用アプリ
├── 2024年: スマートフォン動画撮影 + クラウド処理
└── 2026年: スマートフォン撮影だけ（3DGSで自動処理）
```

---

# ゲーム: Unreal Engineでの3DGS統合

## XScene-UEPlugin

Unreal Engineに3DGSを組み込むプラグインが登場。

```
XScene-UEPlugin:
├── UE5.4/5.5対応
├── PLYファイルの直接インポート
├── リアルタイムレンダリング
├── Naniteとの共存
└── LOD（Level of Detail）サポート
```

## Fabマーケットプレイス

Epic Gamesのデジタルアセットマーケットプレイス「Fab」で、3DGSアセットが流通し始めた。

```
Fabでの3DGSアセット:
├── スキャンベースの環境アセット
│   ├── 実在の建物・街並み
│   ├── 自然環境（岩、木、地形）
│   └── 室内環境
├── 価格帯: $5〜$50
├── フォーマット: PLY, Splat
└── 用途: ゲーム背景、建築ビジュアライゼーション
```

従来の3Dモデリングでは数日〜数週間かかる環境アセットの制作が、撮影+3DGS処理で数時間に短縮された。

---

# VR/XR: 没入体験との融合

## VRChat 3DGSサポート

VRChatが3DGSデータの表示をサポート。

```
VRChat + 3DGS:
├── ワールド内に3DGSオブジェクトを配置可能
├── リアルタイムレンダリング
├── ユーザーアップロード対応
└── 課題: パフォーマンス最適化が必要
```

## Meta Quest統合

Meta Questプラットフォームで3DGSの表示がサポートされ始めた。

```
Meta Quest + 3DGS:
├── Quest 3S / Quest 3での表示対応
├── Passthrough（MR）との組み合わせ
├── 制約: モバイルGPUのため小規模シーンに限定
└── 可能性: 現実空間に3DGSオブジェクトを配置するMR体験
```

## Apple Vision Pro + Safari WebGPU + WebXR

Apple Vision ProのSafariでWebGPUが有効になったことで、Webベースの3DGS + XR体験が可能に。

```
Vision Pro + WebGPU + WebXR:
├── Safari: WebGPUデフォルト有効
├── WebXR: Immersive Web対応
├── 3DGS: WebGPUでリアルタイムレンダリング
├── 組み合わせ: ブラウザだけで空間3DGS体験
└── メリット: アプリインストール不要
```

---

# Webビューア: オープンソースエコシステムの成熟

## 主要ビューアの比較

| ビューア | ライセンス | レンダラー | 特徴 |
|---------|-----------|-----------|------|
| PlayCanvas SuperSplat | MIT | WebGPU | エディタ+ビューア |
| Three.js + Spark | MIT | WebGPU | World Labsが開発、Three.jsエコシステム |
| Babylon.js 8.0 | Apache 2.0 | WebGPU | ビルトイン3DGSサポート |

## PlayCanvas SuperSplat

```
SuperSplat:
├── ライセンス: MIT（商用利用自由）
├── 機能
│   ├── PLY / Splat読み込み
│   ├── 編集（不要部分の削除）
│   ├── 圧縮・エクスポート
│   └── シーンの合成
├── レンダリング: WebGPU
└── URL: https://playcanvas.com/supersplat/editor
```

## Three.js + Spark（World Labs）

World Labsが開発したSparkは、Three.jsベースの3DGSレンダラー。

```
Spark:
├── ライセンス: MIT
├── Three.jsエコシステムとの統合
├── WebGPUレンダリング
├── 高品質なソーティング
└── npm installで導入可能
```

## Babylon.js 8.0

```
Babylon.js 8.0:
├── ライセンス: Apache 2.0
├── 3DGSレンダリングがビルトイン
├── WebGPUエンジンが安定
├── シーングラフとの統合
└── PlaygroundでプロトタイピングOK
```

---

# スマホ問題: モバイルGPUの壁

## 現状のパフォーマンス

3DGSのモバイル表示は依然として課題が大きい。

| デバイス | GPU | 100万ポイント | 評価 |
|---------|-----|-------------|------|
| iPhone 16 Pro | A18 Pro | 25-30fps | かろうじて実用 |
| Samsung S25 Ultra | Snapdragon 8 Elite | 15-20fps | 厳しい |
| Pixel 9 Pro | Tensor G4 | 8-12fps | 実用困難 |
| ミッドレンジ | Mali-G720 | 2-9fps | 表示不可 |

VR/XRでは90fps以上が必要であり、モバイルGPUでの3DGSは大幅な最適化が不可欠。

## 対策

```
モバイル対応の戦略:
├── ポイント数の削減（pruning）
│   ├── 100万→20万ポイントに間引き
│   ├── 品質低下は許容範囲内
│   └── モバイルで30fps達成可能
├── LOD（Level of Detail）
│   ├── 距離に応じてポイント数を調整
│   ├── 近景: フル解像度
│   └── 遠景: 大幅に間引き
├── 圧縮
│   ├── fp32→fp16/int8量子化
│   ├── ファイルサイズ1/4〜1/10
│   └── 読み込み時間の短縮
└── サーバーサイドレンダリング
    ├── GPUサーバーでレンダリング
    ├── 映像をストリーミング配信
    └── モバイルはビューアのみ
```

---

# 残る技術課題

## 4Dストリーミング

動的な3DGS（4DGS）のリアルタイムストリーミングはまだ発展途上。

```
4Dストリーミングの課題:
├── データ量: 1フレーム分の3DGS × 30fps = 膨大
├── 帯域幅: 圧縮なしで数百Mbps必要
├── レイテンシ: リアルタイム性の確保
└── 現状: 事前レンダリング or 短いクリップに限定
```

## 圧縮技術

```
圧縮の現状:
├── Compact3D: CVPR 2024、85%削減
├── LightGaussian: ICML 2024、pruning+蒸留
├── HAC: 属性ハッシュで50倍圧縮
└── 課題: 標準フォーマットが未確定
```

## LOD（Level of Detail）

```
LODの現状:
├── Octree-GS: CVPR 2024、階層LOD
├── Hierarchical 3DGS: SIGGRAPH 2024
├── 課題: LOD切り替え時のポッピング
└── 研究段階から実用段階へ移行中
```

---

# どこから始めるか

## ユースケース別の導入難易度

| ユースケース | 難易度 | 初期コスト | 推奨開始方法 |
|------------|--------|-----------|------------|
| Webビューア | 低 | 無料〜 | SuperSplatで試す |
| 不動産内覧 | 低 | $0〜 | スマホ撮影+クラウド処理 |
| ゲーム背景 | 中 | UEライセンス | XScene-UEPluginで導入 |
| 映画VFX | 高 | OctaneRender | プリビズから試行 |
| VR/XR | 高 | デバイス費用 | Quest 3で小規模テスト |

## 最小構成で試す

```
最小構成（コスト$0）:
├── 1. スマートフォンで対象物を撮影（50-100枚）
├── 2. COLMAP or Polycam で点群生成
├── 3. nerfstudio splatfacto で学習
├── 4. SuperSplat で表示・編集
└── 所要時間: 半日（学習含む）
```

---

# まとめ

| 分野 | 主な事例 | 成熟度 |
|------|---------|--------|
| 映画 | Superman（dynamic 3DGS）、OctaneRender | 実用段階 |
| 不動産 | Zillow SkyTours、Matterport | 普及段階 |
| ゲーム | UE5 XScene、Fabマーケットプレイス | 導入段階 |
| VR/XR | VRChat、Quest、Vision Pro | 初期段階 |
| Web | SuperSplat、Three.js、Babylon.js | 実用段階 |
| モバイル | スマホ直接表示 | 課題あり |

**2026年は3DGSが「使える技術」になった年。始めるなら今。まずはSuperSplatで触ってみよう。**

---

# 関連記事

- [3DGSは商用利用できない？ライセンスと解決策](https://zenn.dev/amabito/articles/3dgs-commercial-guide) - ライセンス問題の整理
- [3DGSとは？ビジネス活用ガイド](https://zenn.dev/amabito/articles/3dgs-business-guide) - 経営者向け解説
- [写真からWebで見れる3Dモデルを作る](https://zenn.dev/amabito/articles/3dgs-pipeline-photos-to-web) - パイプライン完全ガイド
- [3DGSストリーミング](https://zenn.dev/amabito/articles/3dgs-streaming) - 大規模シーンの配信手法
- [3DGS圧縮技術比較](https://zenn.dev/amabito/articles/3dgs-compression-comparison) - サイズ削減手法

---

# 参考

- [3D Gaussian Splatting for Real-Time Radiance Field Rendering](https://repo-sam.inria.fr/fungraph/3d-gaussian-splatting/)
- [PlayCanvas SuperSplat - GitHub](https://github.com/playcanvas/super-splat)
- [Babylon.js 8.0](https://doc.babylonjs.com/)
- [OctaneRender 2026 - OTOY](https://home.otoy.com/render/octane-render/)
- [Unreal Engine Gaussian Splatting](https://dev.epicgames.com/documentation/en-us/unreal-engine/)
- [Matterport 3D Exteriors](https://matterport.com/)
- [Zillow SkyTours](https://www.zillow.com/)

---

ご質問・ご相談はコメント欄へ。
