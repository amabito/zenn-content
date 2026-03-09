---
title: "Claude Code MCP入門：外部ツールを自在に操る"
emoji: "🔌"
type: "tech"
topics: ["ClaudeCode", "MCP", "AI", "CLI", "自動化"]
published: false
---

# 結論から言う

**MCPを使うと、Claude Codeが外部サービスと連携できる。**

- GitHub、Slack、データベース、カスタムAPIとシームレスに統合
- 自然言語で「GitHubのIssue一覧を取得して」と言えば実行される
- 自分のツールもMCPサーバーとして公開可能

この記事では、MCPの概念と実践的な使い方を解説する。

---

# MCPとは

## Model Context Protocol

```
MCP (Model Context Protocol):
├── AIモデルと外部ツールの標準プロトコル
├── Anthropicが策定
├── オープン仕様（誰でも実装可能）
└── Claude Code標準サポート
```

## なぜMCPが必要か

```
従来:
├── AIにファイル読み込み → 手動でコピペ
├── AIにAPI実行 → 結果を手動で伝える
├── AIに外部サービス連携 → 複雑なプロンプト設計
└── 手間がかかる

MCP:
├── AIが直接ファイル読み込み
├── AIが直接API実行
├── AIが直接外部サービス連携
└── 自然言語で指示するだけ
```

---

# MCPの仕組み

## アーキテクチャ

```
┌─────────────────────────────────────────────────┐
│                Claude Code CLI                   │
│  (MCP Host)                                     │
└─────────────────┬───────────────────────────────┘
                  │ JSON-RPC over stdio
    ┌─────────────┼─────────────┐
    ▼             ▼             ▼
┌────────┐  ┌────────┐  ┌────────┐
│ GitHub │  │ Slack  │  │ Custom │
│ Server │  │ Server │  │ Server │
└────────┘  └────────┘  └────────┘
```

## 3つの機能

| 機能 | 説明 | 例 |
|------|------|-----|
| Tools | AIが呼び出せる関数 | `create_issue`, `send_message` |
| Resources | AIが読み取れるデータ | ファイル、DB、API |
| Prompts | 定型プロンプトテンプレート | コードレビュー手順 |

---

# セットアップ

## 設定ファイル

Claude Codeの設定ファイル（`~/.claude/settings.json`）にMCPサーバーを追加:

```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_xxxx"
      }
    },
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/allowed/dir"]
    }
  }
}
```

## 公式MCPサーバー

| サーバー | 用途 |
|---------|------|
| server-github | GitHub操作 |
| server-filesystem | ファイル操作 |
| server-memory | 記憶保持 |
| server-brave-search | Web検索 |
| server-puppeteer | ブラウザ操作 |

---

# 実践例

## GitHub連携

```
ユーザー: 「このリポジトリの未解決Issueを一覧して」

Claude Code:
1. MCPでGitHubサーバーに接続
2. list_issues(state="open") を呼び出し
3. 結果を整形して表示

結果:
#42: バグ修正: ログイン画面のエラー
#38: 機能追加: ダークモード対応
#35: ドキュメント更新
```

## Slack連携

```
ユーザー: 「#dev-channelに進捗を投稿して」

Claude Code:
1. MCPでSlackサーバーに接続
2. send_message(channel="#dev-channel", text="...") を呼び出し
3. 投稿完了

結果:
✅ Slackに投稿しました
```

## データベース連携

```
ユーザー: 「ユーザーテーブルから今月登録した人数を教えて」

Claude Code:
1. MCPでPostgreSQLサーバーに接続
2. execute_query("SELECT COUNT(*) FROM users WHERE ...") を呼び出し
3. 結果を解釈して回答

結果:
今月の新規登録者数は 247人 です。
```

---

# カスタムMCPサーバーを作る

## 最小構成（Python）

```python
# my_server.py
from mcp.server import Server
from mcp.types import Tool, TextContent

server = Server("my-server")

@server.tool()
async def greet(name: str) -> list[TextContent]:
    """名前を受け取って挨拶を返す"""
    return [TextContent(type="text", text=f"こんにちは、{name}さん！")]

if __name__ == "__main__":
    import asyncio
    asyncio.run(server.run())
```

## 設定追加

```json
{
  "mcpServers": {
    "my-server": {
      "command": "python",
      "args": ["my_server.py"]
    }
  }
}
```

## 使い方

```
ユーザー: 「田中さんに挨拶して」

Claude Code: MCPのgreetツールを呼び出します
結果: こんにちは、田中さん！
```

---

# ユースケース

## 1. 開発ワークフロー自動化

```
「PRをレビューして、問題があればIssueを作成、
問題なければマージしてSlackに通知」

MCPが連携:
├── GitHub: PR取得、Issue作成、マージ
├── コードレビュー: Claude Code本体
└── Slack: 通知送信
```

## 2. データ分析

```
「売上データベースから今月の傾向を分析して、
レポートをConfluenceに投稿」

MCPが連携:
├── PostgreSQL: データ取得
├── 分析: Claude Code本体
└── Confluence: レポート投稿
```

## 3. 監視・アラート

```
「サーバーログを監視して、エラーが増えたらSlackに通知」

MCPが連携:
├── Filesystem: ログ読み取り
├── 分析: Claude Code本体
└── Slack: アラート送信
```

---

# セキュリティ考慮

## 権限管理

```
注意点:
├── MCPサーバーは強力な権限を持つ
├── 環境変数でトークンを管理
├── 許可するディレクトリを限定
└── 本番環境では慎重に
```

## 推奨設定

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "/home/user/projects"  // 限定したパスのみ
      ]
    }
  }
}
```

---

# まとめ

| 項目 | 内容 |
|------|------|
| MCPとは | AIと外部ツールの標準プロトコル |
| メリット | 自然言語で外部サービス連携 |
| 公式サーバー | GitHub, Slack, DB, ファイル等 |
| カスタム | Pythonで簡単に作成可能 |

**MCPで、Claude Codeの可能性は無限大。**

---

# 関連記事

## Claude Codeシリーズ
- [Claude Code Hook活用](https://zenn.dev/amabito/articles/claude-code-hooks-automation) - 自動化テクニック
- [Discord×Claude Code](https://zenn.dev/amabito/articles/discord-claude-code-bot) - チーム連携

## 技術シリーズ
- [3DGSとは？](https://zenn.dev/amabito/articles/3dgs-business-guide) - 経営者向け解説

---

:::message
MCPは急速に進化しています。最新情報は[公式ドキュメント](https://modelcontextprotocol.io/)を確認してください。
:::
