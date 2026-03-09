---
title: "Claude Code Hook活用：AIの動作を自在にカスタマイズ"
emoji: "🪝"
type: "tech"
topics: ["ClaudeCode", "自動化", "AI", "CLI", "開発効率"]
published: false
---

# 結論から言う

**Hookを使うと、Claude Codeの動作をカスタマイズできる。**

- コマンド実行前に確認を挟む
- ファイル編集時に自動フォーマット
- コミット時にリンターを実行
- 自分好みのワークフローを構築

この記事では、Hookの設定方法と実践的な活用例を解説する。

---

# Hookとは

## 概念

```
Hook:
├── Claude Codeの特定タイミングで実行されるスクリプト
├── Gitのpre-commit hookに近い概念
├── シェルコマンドを自由に指定可能
└── 成功/失敗でClaude Codeの動作を制御
```

## Hookのタイミング

| Hook名 | タイミング | 用途 |
|--------|-----------|------|
| PreToolUse | ツール実行前 | 確認、前処理 |
| PostToolUse | ツール実行後 | 後処理、通知 |
| Notification | 通知発生時 | 外部連携 |

---

# 設定方法

## 設定ファイル

`~/.claude/settings.local.json` に記述:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "command": "echo 'Bashコマンド実行前'"
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit",
        "command": "prettier --write \"$FILE_PATH\""
      }
    ]
  }
}
```

## 環境変数

Hook内で使用可能な環境変数:

| 変数 | 内容 |
|------|------|
| `$TOOL_NAME` | 実行されたツール名 |
| `$FILE_PATH` | 対象ファイルパス |
| `$TOOL_INPUT` | ツールへの入力（JSON） |
| `$TOOL_OUTPUT` | ツールの出力 |

---

# 実践例

## 1. ファイル編集時に自動フォーマット

**課題**: Claude Codeが編集したコードのフォーマットが崩れる

**解決**:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit",
        "command": "prettier --write \"$FILE_PATH\" 2>/dev/null || true"
      },
      {
        "matcher": "Write",
        "command": "prettier --write \"$FILE_PATH\" 2>/dev/null || true"
      }
    ]
  }
}
```

**効果**: 編集後に自動でPrettierが実行される

## 2. 危険なコマンドをブロック

**課題**: `rm -rf` など危険なコマンドを誤って実行したくない

**解決**:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "command": "bash -c 'echo \"$TOOL_INPUT\" | grep -qE \"rm\\s+-rf|drop\\s+database\" && exit 1 || exit 0'"
      }
    ]
  }
}
```

**効果**: 危険なパターンを検出したらコマンドをブロック

## 3. コミット前にリンター実行

**課題**: コミット前にコード品質をチェックしたい

**解決**:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash(git commit*)",
        "command": "npm run lint || (echo 'Lint failed' && exit 1)"
      }
    ]
  }
}
```

**効果**: lint失敗時はコミットを中止

## 4. Slack通知

**課題**: 長時間タスクの完了を知りたい

**解決**:

```json
{
  "hooks": {
    "Notification": [
      {
        "matcher": "*",
        "command": "curl -X POST $SLACK_WEBHOOK -d '{\"text\":\"Claude Code: 入力待ちです\"}'"
      }
    ]
  }
}
```

**効果**: 入力待ち状態になったらSlackに通知

## 5. ログ記録

**課題**: Claude Codeの操作履歴を残したい

**解決**:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "*",
        "command": "echo \"$(date): $TOOL_NAME\" >> ~/.claude/tool_history.log"
      }
    ]
  }
}
```

**効果**: 全ツール実行がログファイルに記録される

---

# 高度な活用

## マッチャーの書き方

```
マッチャーパターン:
├── "Bash"          → Bash全般
├── "Bash(git *)"   → gitコマンドのみ
├── "Edit"          → ファイル編集
├── "Write"         → ファイル作成
├── "Read"          → ファイル読み取り
├── "*"             → 全ツール
└── "Bash(npm *)"   → npmコマンドのみ
```

## 複数Hookの組み合わせ

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit(*.py)",
        "command": "black \"$FILE_PATH\""
      },
      {
        "matcher": "Edit(*.ts)",
        "command": "prettier --write \"$FILE_PATH\""
      },
      {
        "matcher": "Edit(*.rs)",
        "command": "rustfmt \"$FILE_PATH\""
      }
    ]
  }
}
```

**効果**: 言語別に適切なフォーマッターが実行される

## 条件分岐

```bash
# check_dangerous.sh
#!/bin/bash
INPUT=$(cat)
if echo "$INPUT" | grep -qE "rm -rf|DROP TABLE|format C:"; then
    echo "危険なコマンドを検出しました" >&2
    exit 1
fi
exit 0
```

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "command": "echo \"$TOOL_INPUT\" | ~/.claude/check_dangerous.sh"
      }
    ]
  }
}
```

---

# トラブルシューティング

## Hookが動作しない

```
確認ポイント:
├── JSONの構文エラーがないか
├── コマンドのパスは正しいか
├── 実行権限はあるか
└── マッチャーのパターンは正しいか
```

## Hookでブロックされすぎる

```
対策:
├── マッチャーを限定的に
├── exit 0 でフォールバック
└── || true で失敗を無視
```

## デバッグ方法

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "*",
        "command": "echo \"DEBUG: $TOOL_NAME $TOOL_INPUT\" >> /tmp/claude_debug.log"
      }
    ]
  }
}
```

---

# まとめ

| 項目 | 内容 |
|------|------|
| Hookとは | Claude Codeの動作をカスタマイズするスクリプト |
| タイミング | PreToolUse, PostToolUse, Notification |
| 用途 | フォーマット、セキュリティ、通知、ログ |
| 設定場所 | `~/.claude/settings.local.json` |

**Hookで、自分だけのClaude Code環境を構築。**

---

# 関連記事

## Claude Codeシリーズ
- [Claude Code MCP入門](https://zenn.dev/amabito/articles/claude-code-mcp-intro) - 外部ツール連携
- [Discord×Claude Code](https://zenn.dev/amabito/articles/discord-claude-code-bot) - チーム連携

## 技術シリーズ
- [3DGSとは？](https://zenn.dev/amabito/articles/3dgs-business-guide) - 経営者向け解説

---

:::message
Hook設定は強力ですが、誤設定するとClaude Codeが動作しなくなる場合があります。
バックアップを取ってから設定変更することをお勧めします。
:::
