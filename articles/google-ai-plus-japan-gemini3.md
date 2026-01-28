---
title: "Google AI Plus日本上陸：月額1,200円で何ができるか"
emoji: "🌏"
type: "tech"
topics: ["Google", "Gemini", "AI", "サブスク", "日本"]
published: false
---

# 結論から言う

**月額1,200円でGemini 3 Pro・200GBストレージ・動画生成が使える。ただしProプランの1/3以下の利用回数制限がある。**

2026年1月27日、GoogleはAIサブスクリプション「Google AI Plus」を日本を含む35か国で提供開始した。従来のGoogle AI Pro（月額約2,900円相当）の半額以下で、最新のGemini 3 Proにアクセスできる。

**この記事で得られること:**
- Google AI Plusの機能と制限の正確な理解
- 既存プラン（Pro/Ultra）との比較
- 開発者視点：Gemini 3のAgentic VisionとCUDA/3DGS開発での活用可能性

---

# Google AI Plusの全容

## 料金と特典

| 項目 | 内容 |
|------|------|
| 月額 | 1,200円 |
| 初回特典 | 最初の2か月間50%OFF（月額600円） |
| ストレージ | 200GB（Google One統合） |
| AI機能 | Gemini 3 Pro、Nano Banana Pro |
| 動画生成 | Flowでの動画制作（月200回） |
| NotebookLM | リサーチ・ライティング支援 |
| 家族共有 | 最大5人 |
| 展開地域 | 日本含む35か国 |

## 何が含まれて、何が含まれないか

**含まれるもの:**
- Gemini 3 ProへのアクセスとThinkingモード
- Flowでの動画制作ツール（月200クレジット）
- NotebookLMの上位機能
- 200GBクラウドストレージ
- 最大5人の家族共有

**含まれないもの:**
- AIクレジットのチャージ（使い切ったら翌月まで待つ）
- Google検索のDeep Search
- Google Home Premium
- Google Cloudクレジット

## 最大の注意点：利用回数制限

**Google AI Plusの利用回数は、Proプランの1/3以下。**

これは見落としがちだが極めて重要な制限だ。

| プラン | Gemini 3 Pro利用 | Thinkingモード |
|--------|------------------|---------------|
| AI Plus（1,200円） | 制限あり（Proの1/3以下） | 制限あり |
| AI Pro（約2,900円相当） | フル利用 | フル利用 |
| AI Ultra | 最大利用 | 最大利用 |

日常的にGeminiをヘビーに使う人には制限が厳しい。ライトユーザー向けの位置づけだ。

---

# 既存プランとの比較

## Google AI サブスクリプション体系

| プラン | 月額 | Gemini 3 Pro | ストレージ | Deep Search | Cloudクレジット |
|--------|------|-------------|-----------|------------|----------------|
| **AI Plus** | **1,200円** | **制限付き** | **200GB** | **なし** | **なし** |
| AI Pro | ~2,900円 | フル | 2TB | あり | あり |
| AI Ultra | 上位 | 最大 | 大容量 | あり | あり |

## Google One Premium（2TB）ユーザーへの影響

既存のGoogle One Premium 2TB（月額2,900円）加入者には、数日以内にAI Plus特典が自動付与される。追加料金なしでGemini 3 Proが使えるようになる。

---

# Gemini 3とAgentic Vision

## Gemini 3 Flashの新機能：Agentic Vision

AI Plusとは別のトピックだが、同日発表されたGemini 3 FlashのAgentic Visionは開発者として注目すべき機能だ。

### Agentic Visionとは

画像理解を「静的な認識」から「能動的な調査プロセス」に変える機能。

```
従来: 画像 → LLMが一発で回答
Agentic Vision: 画像 → Think → Act（コード実行） → Observe → 繰り返し
```

### 具体的にできること

1. **ズーム＆クロップ**: Pythonコードを生成して画像の特定領域を切り出し、拡大して分析
2. **画像アノテーション**: バウンディングボックスやラベルを描画して視覚的に推論を根拠づけ
3. **テーブル解析＆可視化**: 高密度な表を解析し、Pythonでグラフ化

### ベンチマーク改善

- コード実行有効化で**ビジョン系ベンチマーク全体に5-10%の品質向上**
- SWE-bench Verifiedで78%（Gemini 3 Proすら上回る）
- GPQA Diamondで90.4%

### 開発者向けパラメータ

| パラメータ | 機能 | 用途 |
|-----------|------|------|
| `thinking_level` | 推論量の制御（minimal/low/medium/high） | レスポンス品質 vs コスト・レイテンシのバランス |
| `media_resolution` | 画像処理解像度（low〜ultra high） | トークン消費 vs 精度のバランス |
| マルチモーダル関数応答 | 画像・PDFを関数レスポンスに含む | ツール連携の高度化 |
| ストリーミング関数呼び出し | 部分的な引数をストリーム | UX改善 |

---

# 開発者視点：3DGS/CUDA開発でのGemini活用

## 現在の筆者の環境

- **メイン開発**: Claude Code + Claude Opus 4.5
- **補助**: GitHub Copilot
- **3DGSプロジェクト**: HyperRasterizer（CUDAラスタライザ）、HyperSplat（学習フレームワーク）

## Gemini 3が使えそうな場面

### Agentic Visionの3DGS応用

3DGS開発では画像品質の評価が頻繁に発生する。

- **レンダリング結果の自動評価**: Agentic Visionでレンダリング画像の問題箇所を自動検出
- **GT比較の自動化**: Ground Truth画像とのピクセル単位比較をAIが能動的に実行
- **アーティファクト検出**: フローター、ぼやけ、色ずれの自動検出と領域特定

### Gemini 3 Proの推論能力

- GPQA Diamond 90.4%の推論力は、数学的な最適化問題の検討に使える
- 3DGSの密度化戦略やプルーニング閾値の理論的検討

### 実際に使うかどうか

| 用途 | 推奨モデル | 理由 |
|------|-----------|------|
| CUDAカーネル実装 | Claude Opus 4.5 | 実績と安定性 |
| 画像品質の自動評価 | **Gemini 3 Flash** | **Agentic Visionが最適** |
| 数理的検討 | Claude Opus 4.5 or Gemini 3 Pro | どちらも強い |
| ドキュメント・記事作成 | Gemini 3 Pro | コスト効率 |

---

# 月額1,200円は「買い」か

## おすすめな人

- Googleエコシステム（Gmail、Drive、Photos）をメインで使っている人
- AI機能を「たまに」使いたいライトユーザー
- 200GBストレージが欲しい人（AI機能はおまけ）
- 家族でシェアしたい人（5人で割れば1人240円）

## おすすめしない人

- Geminiをヘビーに使う開発者（利用回数制限がすぐ来る）
- Deep Searchを日常的に使いたい人
- Claude CodeやCopilotで十分な開発者
- API経由で大量に使いたい人（別途API契約が必要）

## コスト比較（AIサブスクリプション）

| サービス | 月額 | 主な用途 |
|---------|------|---------|
| Google AI Plus | 1,200円 | Gemini 3 Pro（制限付き）＋200GB |
| ChatGPT Plus | ~$20 | GPT-5.2 |
| Claude Pro | ~$20 | Claude Opus 4.5 |
| GitHub Copilot | ~$10 | コーディング補完 |

---

# まとめ

| 観点 | 評価 |
|------|------|
| コスパ | 200GBストレージ込みで1,200円は割安。AI機能は制限付き |
| AI機能 | Gemini 3 Proにアクセス可能。ただしProプランの1/3以下の回数 |
| Agentic Vision | 開発者として最も注目すべき機能。画像解析が能動的に |
| 3DGS開発への適用 | Agentic Visionによるレンダリング品質評価は有望 |
| 総合判断 | ライトユーザーなら買い。ヘビーユーザーはProプランを検討 |

**Google AI Plusは「AIの民主化」の一歩だが、ヘビーユーザーは利用回数制限に注意。** 開発者にとっての本命は、Agentic Visionの能動的画像解析能力だ。

---

# 関連記事

- [Claude Code vs GitHub Copilot 2026：AI開発ツール実践比較](https://zenn.dev/amabito/articles/claude-code-vs-copilot-2026)
- [Claude Codeで開発効率3倍にした具体的な使い方【2026年版】](https://zenn.dev/amabito/articles/claude-code-productivity)
- [Kimi K2.5の実力：Opus比1/10コストでGPT-5.2級の衝撃](https://zenn.dev/amabito/articles/kimi-k25-benchmark-cost-analysis)
- [RTX 5090 CUDA最適化：知らないと損する5つの新常識](https://zenn.dev/amabito/articles/rtx5090-cuda-optimization)
