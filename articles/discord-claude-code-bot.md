---
title: "スマホからClaude Codeを操作する：Discord Bot構築ガイド"
emoji: "📱"
type: "tech"
topics: ["Discord", "ClaudeCode", "Python", "DiscordBot", "自動化"]
published: true
---

# 結論から言う

**スマホのDiscordアプリから、PCで動くClaude Codeを操作できるようにした。**

電車の中でも、カフェでも、ベッドの上でも開発ができる。

この記事では、Discord BotとClaude Code CLIを連携させて、スマホからリアルタイムで開発指示を出せるシステムの構築方法を解説する。

**この記事で得られること:**
- Discord Bot × Claude Code連携の仕組み
- 実装のアーキテクチャ設計
- セキュリティ考慮事項
- 基本的な構築手順

---

# なぜDiscord連携が必要か

## 課題：PCの前にいないと開発できない

```
従来のワークフロー:
├── PCの前に座る
├── ターミナルを開く
├── claude コマンドを実行
└── 結果を確認

→ PCがないと何もできない
```

## 解決：どこからでもClaude Codeを操作

```
新しいワークフロー:
├── スマホでDiscordを開く
├── /cc ファイル一覧を見せて
├── Claude Codeが実行
└── 結果がDiscordに返ってくる

→ 電車でも、カフェでも開発可能
```

---

# システムアーキテクチャ

## 全体構成

```
[スマホ Discord App]
        │
        ▼ WebSocket (Discord API)
[Discord Server]
        │
        ▼
[WSL2: Discord Bot (Python)]
        │
        ├─► セッション管理（会話継続）
        │
        ▼
[Claude Code CLI]
        │
        ▼
[結果を Discord に返信]
```

## 技術選定

| コンポーネント | 技術 | 理由 |
|---------------|------|------|
| Bot | Python + discord.py | 非同期処理が優秀 |
| 実行環境 | WSL2 Ubuntu | Claude CLIがLinux向け |
| 通信 | WebSocket | リアルタイム双方向 |
| セッション | メモリ + JSON永続化 | 会話継続のため |

---

# セキュリティ設計

**これが最も重要。** 雑に作ると誰でもあなたのPCを操作できてしまう。

## 多層認証

```
Layer 1: Discord Server
  └─► プライベートサーバーのみ

Layer 2: Channel ID
  └─► 指定チャンネルのみBot反応

Layer 3: User ID
  └─► ホワイトリスト登録ユーザーのみ

Layer 4: Command Prefix
  └─► /cc コマンドのみ処理
```

## 権限最小化

```python
# 許可するClaude Codeツールを明示的に制限
ALLOWED_TOOLS = [
    "View",  # ファイル読み取りのみ
    "Bash(git status,git log,git diff,ls,cat,head,tail)"
]
# ファイル書き込みは禁止（必要時のみ個別許可）
```

## Bot権限

```
必要最小限のみ:
✓ View Channels
✓ Send Messages
✓ Send Messages in Threads
✓ Create Public Threads
✓ Read Message History

明示的に除外:
✗ Administrator
✗ Manage Server
✗ Mention Everyone
```

---

# 基本的なコマンド体系

## 実装するコマンド

| コマンド | 説明 |
|---------|------|
| `/cc <指示>` | Claude Codeに指示を送信 |
| `/cc continue <指示>` | 前回の会話を継続 |
| `/cc reset` | セッションをリセット |
| `/cc cancel` | 実行中タスクをキャンセル |
| `/cc status` | Bot状態確認 |
| `/cc help` | ヘルプ表示 |

## 使用例

```
# ファイル一覧を確認
/cc このプロジェクトの構造を教えて

# 続けて質問
/cc continue その中のmain.pyの内容を見せて

# 新しいトピック
/cc reset
/cc テストを実行して結果を教えて
```

---

# 実装の要点

## 1. スレッドによる会話分離

```python
# 新しい指示 → 新しいスレッドを作成
if not isinstance(message.channel, discord.Thread):
    thread = await message.create_thread(
        name=f"Claude: {prompt[:40]}...",
        auto_archive_duration=1440  # 24時間
    )
```

**メリット:**
- 複数の作業を並行して進められる
- 過去の会話を簡単に参照できる
- チャンネルが散らからない

## 2. セッション管理

```python
@dataclass
class Session:
    session_id: str
    thread_id: int
    message_count: int = 0

    def touch(self):
        self.last_activity = datetime.now()
        self.message_count += 1
```

**ポイント:**
- スレッドごとにセッションを管理
- `--continue` フラグでClaude Codeの会話を継続
- JSON永続化でBot再起動後も復元

## 3. 長文の分割送信

Discordは2000文字制限がある。

```python
async def send_long_message(channel, content, max_length=1900):
    chunks = []
    # コードブロックを考慮した分割
    # ``` の途中で切れないように
    for chunk in smart_split(content, max_length):
        await channel.send(chunk)
        await asyncio.sleep(0.5)  # レート制限対策
```

## 4. タイムアウト処理

```python
try:
    stdout, stderr = await asyncio.wait_for(
        process.communicate(),
        timeout=600  # 10分
    )
except asyncio.TimeoutError:
    return "⏰ タイムアウト（10分）"
```

---

# 構築手順（概要）

## 1. Discord Developer Portalで Bot作成

```
1. https://discord.com/developers/applications
2. New Application → "Claude Code Bot"
3. Bot タブ → Add Bot
4. MESSAGE CONTENT INTENT: ON（重要）
5. Token をコピー（1度しか表示されない）
```

## 2. WSL2環境の準備

```bash
# 作業ディレクトリ
mkdir -p ~/claude-discord-bot
cd ~/claude-discord-bot

# Python環境
python3 -m venv venv
source venv/bin/activate

# 依存パッケージ
pip install discord.py python-dotenv pyyaml
```

## 3. 設定ファイル

```bash
# .env（認証情報）
DISCORD_TOKEN=your_bot_token
DISCORD_ALLOWED_USERS=your_user_id
DISCORD_ALLOWED_CHANNELS=your_channel_id
CLAUDE_PATH=/home/username/.local/bin/claude
WORKSPACE=/home/username/projects
```

## 4. 起動

```bash
./start_discord_bot.sh
```

---

# 私の使い方

## 通勤中

```
📱 電車の中で:
/cc 昨日のコミット内容を見せて

🤖 Bot:
feat: Add user authentication
- JWT token implementation
- Password hashing with bcrypt
...

📱 続けて:
/cc continue テストは通ってる？

🤖 Bot:
All 42 tests passed.
```

## 昼休み

```
📱 カフェで:
/cc TODO一覧を見せて

🤖 Bot:
- [ ] API rate limiting
- [ ] Error handling improvement
- [x] User authentication
...

📱 思いついたことをメモ:
/cc CLAUDE.mdに「キャッシュ機能を検討」と追記して
```

## 帰宅後

PCを開いたら、すでに作業の続きが記録されている。

---

# 注意事項

## できないこと

| 項目 | 理由 |
|------|------|
| インタラクティブ操作 | vim、対話型プログラムは不可 |
| 大量のファイル生成 | レスポンスが長すぎる |
| 長時間タスク | 10分タイムアウト |
| 機密情報操作 | セキュリティリスク |

## やってはいけないこと

```
❌ Bot Tokenをコードにハードコード
❌ 誰でも参加できるサーバーで使用
❌ ファイル書き込みを無制限に許可
❌ 実行結果を確認せずにコミット
```

---

# まとめ

| 項目 | 内容 |
|------|------|
| 何ができる | スマホからClaude Code操作 |
| 技術スタック | Python + discord.py + WSL2 |
| セキュリティ | 4層認証 + 権限最小化 |
| 使用場面 | 通勤中、外出先、ベッド |

**「PCがないと開発できない」という制約から解放される。**

---

# 関連記事

## Claude Codeシリーズ
- [Claude Codeで開発効率3倍](https://zenn.dev/amabito/articles/claude-code-productivity) - 基本的な使い方
- [【有料】Claude Code完全活用ガイド](https://zenn.dev/amabito/articles/claude-code-productivity-paid) - プロンプト集と自動化

## 技術シリーズ
- [3DGSを商用利用したい人へ](https://zenn.dev/amabito/articles/hyper-rasterizer-zenn) - HyperRasterizer解説
- [GPUプログラミング入門](https://zenn.dev/amabito/articles/gpu-programming-intro) - CUDA基礎

---

:::message
**完全な実装コード**（Python Bot全文 + 設定ファイル + 起動スクリプト）は有料記事で公開しています。
→ [【有料】Discord × Claude Code Bot 完全実装ガイド](https://zenn.dev/amabito/articles/discord-claude-code-bot-paid)
:::
