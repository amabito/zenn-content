---
title: "Claude Codeで開発ワークフローを自動化した全記録【2026年版】"
emoji: "🤖"
type: "tech"
topics: ["ClaudeCode", "自動化", "開発効率", "AI", "プログラミング"]
published: false
---

# 結論から言う

**Claude CodeのSkill・Hook・MCP・Discord Botを組み合わせて、コーディング・テスト・デプロイ・記事執筆まで自動化した。**

この記事では、個人開発者が実際に構築した自動化環境の全体像を公開する。

**対象読者:**
- Claude Codeを使い始めた・使いこなしたい開発者
- 開発ワークフローの効率化に興味がある人
- AIコーディングツールの実践的な活用法を知りたい人

**この記事で得られること:**
- Skill・Hook・MCP・Discord Botの役割と連携
- 実際の自動化構成の全体像
- 導入による具体的な効果

---

## 自動化の全体像

```
┌─────────────────────────────────────────────┐
│              開発ワークフロー                   │
├──────────┬──────────┬───────────┬────────────┤
│  Skill   │  Hook    │   MCP     │ Discord Bot│
│ 専門知識  │ 自動実行  │ 外部連携   │ リモート操作 │
├──────────┴──────────┴───────────┴────────────┤
│              Claude Code CLI                  │
└─────────────────────────────────────────────┘
```

4つの仕組みがあり、役割は明確に分かれている。

---

## 1. Skill：専門知識のカプセル化

特定タスクに必要な知識・手順・ルールをMarkdownにまとめ、Claude Codeに読み込ませる仕組み。

### 実際に作ったSkill

| Skill | 用途 | 効果 |
|-------|------|------|
| blogger | 技術ブログ記事の作成・管理 | 記事構成・SEO・価格設定の自動判断 |
| code-review | コードレビュー | 品質基準の統一 |
| debugging | バグ調査 | 体系的デバッグプロセス |
| git-workflow | Git操作 | コミット規約の自動適用 |

### Skillの構造

```markdown
---
name: blogger
description: 技術ブログの記事作成・管理・収益化
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash(git:*)
  - Bash(npx:*)
---

# Blogger Skill

## マーケティング戦略
[具体的ルール・判断基準]

## 記事テンプレート
[テンプレート定義]

## 禁止事項
[やってはいけないこと]
```

**ポイント:**
- **`allowed-tools`でセキュリティ制御**
  - 必要最小限のツールのみ許可（例: 記事作成SkillにBash(rm *)は不要）
  - ワイルドカードに注意（`Bash(git:*)`は全git操作を許可）
  - 機密リスクのある操作は明示的に除外
- **ルールは具体的に**
  - ❌ 「良い記事を書く」
  - ✅ 「タイトルは20-36文字」「h2見出しは5-7個」
- **Skill同士は独立**
  - 1つが壊れても他に影響しない
  - 共通ロジックは別ファイルに分離

---

## 2. Hook：イベント駆動の自動処理

Claude Codeの特定イベントに対してシェルコマンドを自動実行する仕組み。

### 活用例

| トリガー | 処理 | 効果 |
|---------|------|------|
| コミット前 | lint + テスト | 品質担保の自動化 |
| ファイル変更後 | ビルド確認 | 壊れたコードの即時検出 |
| ツール使用後 | ログ記録 | 操作の追跡 |

### 実装例（コミット前フック）

`~/.claude/hooks/pre-commit.sh`:
```bash
#!/bin/bash
# Pythonファイルが変更されていればlintを実行
if git diff --cached --name-only | grep '\.py$'; then
    echo "Running pylint..."
    pylint $(git diff --cached --name-only | grep '\.py$')
    if [ $? -ne 0 ]; then
        echo "❌ Lint failed. Fix errors before committing."
        exit 1  # コミットをブロック
    fi
fi
```

設定ファイル（`~/.claude/config.json`）:
```json
{
  "hooks": {
    "pre-commit": "~/.claude/hooks/pre-commit.sh"
  }
}
```

**ポイント:**
- 「忘れがちだが毎回やるべきこと」に使う
- 重い処理を入れると体験が悪くなる。軽量に保つ（上記例: 3秒以内）
- 失敗時の挙動を決めておく（`exit 1`でブロック、`exit 0`で警告のみ）

---

## 3. MCP：外部サービス連携

Model Context Protocol。Claude Codeが外部ツール・サービスと通信するプロトコル。

### 連携例

| 連携先 | 用途 |
|--------|------|
| ファイルシステム | プロジェクトファイルの読み書き |
| Git | リポジトリ操作 |
| Web API | 外部サービスとの通信 |
| データベース | データの読み書き |

### 実装例（カスタムMCPサーバー）

Node.jsでGitHub API連携サーバーを作成:

```javascript
// mcp-github-server.js
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { Octokit } from "@octokit/rest";

const server = new Server({
  name: "github-mcp",
  version: "1.0.0",
});

const octokit = new Octokit({ auth: process.env.GITHUB_TOKEN });

server.setRequestHandler("tools/call", async (request) => {
  if (request.params.name === "create_issue") {
    const { owner, repo, title, body } = request.params.arguments;
    const result = await octokit.issues.create({ owner, repo, title, body });
    return { content: [{ type: "text", text: JSON.stringify(result.data) }] };
  }
});

server.connect();
```

Claude Code設定（`~/.claude/config.json`）:
```json
{
  "mcpServers": {
    "github": {
      "command": "node",
      "args": ["mcp-github-server.js"],
      "env": { "GITHUB_TOKEN": "ghp_xxxxx" }
    }
  }
}
```

**ポイント:**
- MCPサーバーは「Claude Codeの手足を増やす」仕組み
- セキュリティ上、信頼できるサーバーのみ使用する（トークン管理に注意）
- 公式サーバーとコミュニティサーバーがある

---

## 4. Discord Bot：スマホから開発指示

### なぜDiscordか

- スマホアプリが安定
- Bot作成が簡単
- チャンネルで会話履歴が残る
- 無料

### アーキテクチャ

```
スマホ(Discord) → Discord Bot (Python) → Claude Code CLI → 実行結果 → Discord返信
```

### できること

- コード修正指示
- テスト実行
- Git操作（コミット、プッシュ）
- 記事の作成・公開
- プロジェクト状態確認

電車の中、カフェ、就寝前。PCなしで開発指示が出せる。

### 実装例（最小構成）

```python
# discord_bot.py
import discord
import subprocess

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content.startswith("!claude "):
        prompt = message.content[8:]  # "!claude "を除去

        # Claude Code CLIを実行
        result = subprocess.run(
            ["claude", "code", prompt],
            capture_output=True,
            text=True,
            timeout=300
        )

        # 結果をDiscordに返信（2000文字制限）
        response = result.stdout[:1900] if result.stdout else "実行完了"
        await message.channel.send(f"```\n{response}\n```")

client.run("YOUR_DISCORD_BOT_TOKEN")
```

**セキュリティ上の注意:**
- **機密情報を送信しない:** Discord APIキー、データベースパスワード、秘密鍵などは絶対に送らない
- **チャンネルを限定:** プライベートチャンネルのみで使用（パブリックチャンネルでの使用禁止）
- **トークンは環境変数:** `os.getenv("DISCORD_TOKEN")`で管理
- **ログが残る:** Discordサーバーに会話履歴が残ることを認識する

---

## 組み合わせの実例

### 記事作成ワークフロー

```
1. Discord:「3DGSの入門記事を書いて」
2. Claude Code: bloggerスキル読み込み
3. 記事テンプレートに従い記事作成
4. Hook: 保存時にmarkdownlint実行
5. git commit & push
6. Zenn: GitHub連携で自動デプロイ
7. Discord:「記事を公開しました」
```

### CUDA開発ワークフロー

```
1. Discord:「CUDAカーネルのベンチマーク取って」
2. Claude Code: プロジェクト読み込み
3. ベンチマークスクリプト実行
4. Hook: 結果をログに記録
5. Discord: 結果をフォーマットして返信
```

---

## 導入の効果

| 項目 | Before | After |
|------|--------|-------|
| 記事作成 | 手動で構成→執筆→確認 | Skill+テンプレートで構成自動化 |
| コード品質 | レビュー忘れあり | Hookで自動チェック |
| リモート作業 | PC必須 | スマホから指示可能 |
| 外部連携 | 手動コピペ | MCPで自動連携 |

---

## 導入のコツ

### やるべきこと

1. **Skillから始める** — 最も効果が高い。よく使うタスク1つをSkill化
2. **段階的に拡張** — 一度に全部入れない。1つずつ追加
3. **ルールは具体的に** — 曖昧な指示は曖昧な結果になる

### やってはいけないこと

1. **Hookを重くしない** — レスポンス悪化で使わなくなる
2. **MCPサーバーを増やしすぎない** — 管理コスト増加
3. **Discord Botに機密を流さない** — ログが残る

---

## まとめ

| 仕組み | 役割 | 一言 |
|--------|------|------|
| **Skill** | 専門知識の定義 | 何を知っているか |
| **Hook** | 自動トリガー | いつ実行するか |
| **MCP** | 外部連携 | 何と繋がるか |
| **Discord Bot** | リモート操作 | どこから操作するか |

4つを組み合わせることで「知識を持ち、自動で動き、外部と繋がり、どこからでも操作できる」開発環境が作れる。

---

## 関連記事

- [無料] [Claude Code MCP入門](https://zenn.dev/amabito/articles/claude-code-mcp-intro) - MCPの基礎
- [無料] [Claude Code Hook活用ガイド](https://zenn.dev/amabito/articles/claude-code-hooks-automation) - Hookの詳細
- [有料] [Claude Code生産性ガイド](https://zenn.dev/amabito/articles/claude-code-productivity-paid) - 生産性最大化の設定
- [無料] [Discord×Claude Code Bot](https://zenn.dev/amabito/articles/discord-claude-code-bot) - Bot構築の詳細

---

ご質問・ご相談はコメント欄へ。
