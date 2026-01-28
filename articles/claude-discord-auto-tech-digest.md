---
title: "Claude Code+Discordで毎朝AIニュースを自動配信する仕組み"
emoji: "📡"
type: "tech"
topics: ["ClaudeCode", "Discord", "Python", "自動化", "AI"]
published: false
---

# 結論から言う

**6つの情報源からAI/3DGS/CUDA関連ニュースを自動収集し、Claude CLIで日本語翻訳して、毎朝Discord Webhookで配信するシステムを構築した。** Pythonスクリプト約830行。Windows環境のタスクスケジューラで完全自動実行。

手動で技術ニュースを巡回する時間がゼロになった。

**この記事で得られること:**
- 6ソースからの情報収集アーキテクチャ
- Claude CLI活用による英日翻訳の実装方法
- Discord Webhookの活用とEmbed設計
- Windows環境特有の罠と回避策

---

# アーキテクチャ概要

## 全体フロー

```
[6つの情報源]
    │
    ▼
[Python収集スクリプト]
    │  RSS / API / スクレイピング
    ▼
[Claude CLI 翻訳]
    │  英語タイトル → 日本語
    ▼
[Discord Webhook 投稿]
    │  Embedで整形通知
    ▼
[Discordチャンネル]
    毎朝自動で最新ニュースが届く
```

**設計思想:**
- 各ソースのフェッチャーは独立モジュール
- 1ソースが失敗しても他は継続（フォールトトレラント）
- 翻訳はバッチ処理でAPI呼び出しを最小化
- 重複排除は過去24時間のURLハッシュで実現

---

# 情報源の選定と設計判断

## 6つの情報源

| # | ソース | 種別 | 取得方法 | 主な対象 |
|---|--------|------|----------|----------|
| 1 | Gigazine | RSS | feedparser | AI・テック全般（日本語） |
| 2 | ITmedia AI+ | RSS | feedparser | 企業AI活用（日本語） |
| 3 | Publickey | RSS | feedparser | インフラ・開発ツール（日本語） |
| 4 | Hugging Face Daily Papers | API | requests | 最新AI論文 |
| 5 | Reddit (r/MachineLearning, r/LocalLLaMA) | API | PRAW | コミュニティ話題 |
| 6 | GitHub Releases | API | requests | CUDA/PyTorch/nerfstudioリリース |

## 選定基準

**日本語ソース（3つ）を入れた理由:**
- 翻訳コスト不要、即座に読める
- 日本市場特有の情報（法規制、導入事例）
- Gigazineは速報性が高く、ITmediaは企業視点が強い

**英語ソース（3つ）の選定理由:**
- HF Daily Papers: arXiv論文の中から質の高いものが自動キュレーション
- Reddit: 実務者の生の声、ベンチマーク結果、ツール評価
- GitHub Releases: 依存ライブラリの更新を見逃さない

**除外したソース:**
- Twitter/X: API費用が高い、ノイズ多い
- arXiv直接: 量が多すぎて翻訳コスト過大
- Hacker News: ML特化でなくノイズ多い

---

# 情報収集モジュールの設計

## 共通インターフェース

各ソースのフェッチャーは統一されたデータ構造を返す。

```
NewsItem:
├── title: str          # 記事タイトル
├── url: str            # 記事URL
├── source: str         # ソース名
├── published: datetime # 公開日時
├── summary: str        # 要約（あれば）
├── language: str       # "ja" or "en"
└── category: str       # "paper", "release", "news", "discussion"
```

## フィルタリングロジック

全ソース共通のキーワードフィルタを適用する。

```
INCLUDE_KEYWORDS:
├── AI/ML系: "LLM", "transformer", "diffusion", "agent"
├── 3D系: "3DGS", "gaussian splatting", "NeRF", "3D reconstruction"
├── GPU系: "CUDA", "GPU", "NVIDIA", "RTX"
└── ツール系: "PyTorch", "Claude", "nerfstudio"

EXCLUDE_KEYWORDS:
├── "crypto", "blockchain", "NFT"  # ノイズ除外
└── "stock", "investment"           # 金融系除外
```

**24時間ウィンドウ:** 前回実行以降の記事のみ取得。初回は過去24時間。

## RSS取得（日本語3ソース）

feedparserでRSSを取得し、キーワードフィルタを適用する。

```
処理フロー:
1. feedparser.parse(url)
2. 各エントリからtitle, link, published抽出
3. キーワードフィルタ適用
4. 24時間以内のもののみ返却
```

**注意点:** Gigazineは `published_parsed` のタイムゾーンがJSTだが、他はUTC。タイムゾーン正規化が必要。

## Hugging Face Daily Papers

```
API: https://huggingface.co/api/daily_papers
認証: 不要（公開API）
レスポンス: JSON配列（title, paper.id, publishedAt）
```

上位10件を取得。論文タイトルは英語なので翻訳対象。

## Reddit

```
ライブラリ: PRAW (Python Reddit API Wrapper)
認証: OAuth2（Client ID + Secret）
取得: hot/top posts from past 24h
サブレディット: MachineLearning + LocalLLaMA
```

**Reddit APIの制約:**
- レート制限: 60リクエスト/分
- OAuth2トークン取得が必要（事前設定）
- NSFW投稿は自動フィルタ

## GitHub Releases

監視対象リポジトリ:

```
WATCH_REPOS:
├── pytorch/pytorch
├── NVIDIA/cuda-toolkit
├── nerfstudio-project/nerfstudio
├── nerfstudio-project/gsplat
├── anthropics/claude-code
└── graphdeco-inria/gaussian-splatting
```

GitHub REST APIでlatestリリースを取得。前回チェック以降の新規リリースのみ通知。

---

# 英語→日本語翻訳の実装

## Claude CLIによるバッチ翻訳

英語ソースのタイトルをまとめてClaude CLIに渡し、一括翻訳する。

```
翻訳フロー:
1. 英語タイトルをリスト化（最大30件）
2. Claude CLIにプロンプトとして渡す
3. 翻訳結果をパース
4. 元データにマージ
```

**バッチ化の理由:**
- 1件ずつ翻訳するとAPI呼び出しが多すぎる
- 30件まとめれば1回のCLI呼び出しで完了
- コスト・速度の両面で有利

## Windows改行問題の回避

**問題:** WindowsのコマンドラインでClaude CLIにマルチライン文字列を渡すと、改行コードの扱いで壊れることがある。

**発生条件:**
- `subprocess.run()` でstdinにパイプ入力
- 日本語文字列にCR+LFが混在
- PowerShellとcmd.exeで挙動が異なる

**回避策:**

```
対策1: 一時ファイル経由
  → 翻訳対象を一時ファイルに書き出し
  → Claude CLIに --input オプションで渡す
  → 改行コード問題を完全に回避

対策2: Base64エンコード
  → 改行を含まない形式でデータを渡す
  → CLIの出力もBase64で受け取る
  → デバッグが困難になるため非推奨
```

結論として**一時ファイル経由が最も安定**する。

## エンコーディングの罠

```
Windows環境の落とし穴:
├── デフォルトエンコーディング: cp932（Shift-JIS系）
├── Claude CLIの出力: UTF-8
├── Python 3のデフォルト: ロケール依存
└── 解決: PYTHONUTF8=1 環境変数を設定
```

`subprocess.run()` に `encoding='utf-8'` を明示指定するだけでは不十分。タスクスケジューラ経由だと環境変数が異なるため、バッチファイル内で `set PYTHONUTF8=1` を設定する。

---

# Discord Embedの設計

## Embed構造

1つのソースカテゴリごとに1つのEmbedを作成する。

```
Embed設計:
├── title: "AI/ML最新ニュース [2026-01-28]"
├── color: ソースごとに色分け
│   ├── 日本語ニュース: 0x00B0F0 (水色)
│   ├── AI論文: 0xFF6B35 (オレンジ)
│   ├── Reddit話題: 0xFF4500 (Reddit色)
│   └── GitHubリリース: 0x238636 (GitHub色)
├── fields:
│   ├── field: "[タイトル](URL)" × N件
│   └── field: "翻訳: 日本語タイトル" (英語ソースのみ)
├── footer: "取得時刻: 07:00 JST"
└── timestamp: ISO 8601
```

## Webhook投稿

```
投稿方法: requests.post(webhook_url, json=payload)
レート制限: 30メッセージ/分/Webhook
対策: Embed数が多い場合は1秒間隔で投稿
```

**複数Embed一括送信:** Discord Webhookは1リクエストで最大10個のEmbedを送信可能。6ソースなら1回のリクエストで完了する。

---

# タスクスケジューラで毎朝自動実行

## セットアップ

```
実行バッチファイル（run_digest.bat）の内容:

  1. PYTHONUTF8=1 を設定
  2. 仮想環境をactivate
  3. python tech_digest.py を実行
  4. ログファイルに出力
```

## タスクスケジューラ設定

| 項目 | 設定値 |
|------|--------|
| トリガー | 毎日 07:00 |
| 操作 | run_digest.bat 実行 |
| 条件 | AC電源接続時のみ（ノートPC考慮） |
| 設定 | 最長実行時間: 10分 |
| 設定 | 失敗時の再試行: 5分後に1回 |

**ログイン不要実行:** 「ユーザーがログオンしているかどうかにかかわらず実行する」を有効化。ただしパスワード保存が必要。

## 実行時の注意点

```
よくあるトラブル:
├── "指定されたファイルが見つかりません"
│   → バッチファイルのパスを絶対パスに
├── Python仮想環境が見つからない
│   → activate.batの絶対パスを指定
├── 文字化け
│   → PYTHONUTF8=1を設定
└── ネットワーク未接続
    → PC起動直後はWi-Fi未接続の場合あり
    → トリガーを起動後5分遅延に設定
```

---

# 実際の運用結果

## 定量データ（2週間運用）

| 指標 | 結果 |
|------|------|
| 1日あたりの記事数 | 15-30件 |
| うち英語→日本語翻訳 | 8-15件 |
| Claude CLI翻訳コスト | 約$0.02/日 |
| 実行時間 | 平均45秒 |
| 失敗率 | 4.2%（Reddit API一時障害） |

## 定性的な効果

**導入前:**
- 毎朝30分かけてRSS・Twitter・Redditを巡回
- 英語論文タイトルを読み飛ばしがち
- 重要リリースに気づくのが数日遅れ

**導入後:**
- 朝のDiscord通知を2分で確認
- 日本語翻訳により英語論文も自然に目に入る
- GitHub Releaseの通知で依存ライブラリの更新に即対応

**月間の時間削減効果:** 30分/日 x 30日 = **約15時間/月**

## 改善アイデア

```
今後の拡張候補:
├── Anthropic公式ブログの追加
├── YouTube（AI系チャンネル）の新着通知
├── 論文の1行要約をClaude CLIで生成
├── 重要度スコアリング（高/中/低のタグ付け）
└── 週次サマリーの自動生成
```

---

# まとめ

| 項目 | 詳細 |
|------|------|
| **構成** | Python 830行 + バッチファイル |
| **情報源** | 日本語RSS 3 + HF Papers + Reddit + GitHub |
| **翻訳** | Claude CLIバッチ処理 |
| **配信** | Discord Webhook + Embed |
| **自動化** | Windowsタスクスケジューラ |
| **コスト** | 月$0.60程度（Claude API） |
| **時間削減** | 約15時間/月 |

**技術ニュースの収集を自動化することで、情報のインプットではなく、アウトプット（開発・執筆）に時間を使えるようになった。**

Windows環境特有の罠（改行コード、エンコーディング、タスクスケジューラの挙動）さえ乗り越えれば、Claude CLIは自動化パイプラインの強力な構成要素になる。

---

# 関連記事

## Claude Code活用シリーズ
- [Claude Codeで開発効率3倍にした具体的な使い方](https://zenn.dev/amabito/articles/claude-code-productivity) - 基本の活用法
- [Claude Code Hook活用：AIの動作を自在にカスタマイズ](https://zenn.dev/amabito/articles/claude-code-hooks-automation) - Hookによる自動化
- [Claude Codeで開発ワークフローを自動化した全記録](https://zenn.dev/amabito/articles/claude-code-automation-workflow) - 自動化の全体像
- [Claude Agent SDK活用：カスタムツールで専門AIを構築](https://zenn.dev/amabito/articles/claude-agent-sdk-custom-tools) - Agent SDK

## Discord連携シリーズ
- [スマホからClaude Codeを操作する：Discord Bot構築ガイド](https://zenn.dev/amabito/articles/discord-claude-code-bot) - Bot構築の基礎

---

ご質問・ご相談はコメント欄へ。
