---
title: "Claude Codeのcontext limit対策: ファイルベース通信パターン"
emoji: "📁"
type: "tech"
topics: ["ClaudeCode", "ai", "マルチエージェント", "開発効率"]
published: true
published_at: "2026-02-28 18:00"
---

## 問題：長時間セッションで突然死

J.A.R.V.I.S.チームモード（マルチエージェントでの長時間開発セッション）を運用していると、数時間後に突然これが出る。

```
Context limit reached. Use /compact to continue.
```

しかも `/compact` も失敗する。会話履歴が長すぎてcompactできない状態。

エージェントが20個のタスクを一つずつ報告していると、メッセージだけで数万トークン消費する。

---

## 根本原因

マルチエージェントで複数のMarkユニットが動いていると、各エージェントがSendMessageで進捗を報告してくる。

```python
# NGパターン（実際にやっていた）
SendMessage(
    type="message",
    recipient="main",
    content="""
    Task #10完了しました。

    根本原因の分析:
    - portfolio_manager.pyの291行目で、active ordersのみをチェックしていた
    - filled positionsのチェックが漏れていた
    - signal_idの重複チェックが実装されていなかった

    修正内容:
    - active.jsonとの照合ロジックを追加
    - signal_id重複ブロックを実装
    - 幽霊ポジションのクリーンアップ処理を追加

    テスト結果:
    - test_risk_manager.py: 5/5 PASSED
    - 本番環境での動作確認: 重複エントリーなし

    変更ファイル:
    - src/polymarket_bot/core/portfolio_manager.py
    - tests/test_risk_manager.py
    """,
    summary="Task #10完了"
)
```

10個のタスクが全部こんな報告をすると、それだけで数千トークン。

---

## Carliniの教え

Nicholas Carlini（Anthropicの研究者）が言っていることで印象に残っているのが：

> "Use file-based state instead of message history. Agents read from files, not from chat history."

コンテキストウィンドウを「作業メモリ」として使うな。ファイルシステムを使え。

長い分析結果はファイルに保存して、メッセージには「ファイルのパス」だけを送る。

---

## 解決策：ファイルベース通信パターン

### パターン1: 大量データはファイルに書く

```python
# OKパターン
import json

# 詳細はファイルに保存
detailed_result = {
    "root_cause": "...",
    "fix_applied": "...",
    "test_results": {...}
}
with open(".jarvis/task10_result.json", "w") as f:
    json.dump(detailed_result, f, ensure_ascii=False, indent=2)

# メッセージには最小限だけ
SendMessage(
    type="message",
    recipient="main",
    content="Task #10完了。詳細: .jarvis/task10_result.json",
    summary="Task #10完了"
)
```

### パターン2: 進捗チェックポイント

10タスクごとに`.jarvis/progress.md`に状態を保存する。

```markdown
# .jarvis/progress.md

## Completed (Task #1-10)
- [x] Task #1: ETH建玉検出修正 → trading_limits.py:47
- [x] Task #2: signal_id重複チェック → portfolio_manager.py:291
- [x] Task #3: margin ratio監視 → risk_manager.py:88
...

## In Progress
- [ ] Task #11: Dashboard統合

## Next Action
Resume from Task #11.

## Files Modified
- src/polymarket_bot/core/trading_limits.py
- src/polymarket_bot/core/portfolio_manager.py
```

コンテキストがリセットされても、このファイルを読めば状態が復元できる。

### パターン3: メッセージは100行以内ルール

SendMessageの内容を100行以内に収める。

```python
MAX_MESSAGE_LINES = 100

def send_task_complete(task_id: int, summary: str, files: list[str]) -> None:
    """タスク完了報告（コンパクト版）"""
    file_list = "\n".join(f"  - {f}" for f in files[:5])  # 最大5ファイル

    content = f"""[COMPLETE] Task #{task_id}: {summary}
Files:
{file_list}
"""
    SendMessage(
        type="message",
        recipient="main",
        content=content,
        summary=f"Task #{task_id}完了"
    )
```

---

## 緊急対処法

すでにcontext limitに到達してしまった場合。

### Step 1: 最後に見えているメッセージから状態を手動で記録

```bash
# 今のタスク状況をファイルに手動保存
cat > .jarvis/rescue.md << 'EOF'
# Rescue State

## Last Known State
- Completed: Task #1-10
- In Progress: Task #11 (Dashboard統合)
- Failed: /compact

## Next Action
Resume from Task #11.
EOF
```

### Step 2: セッションを閉じる

コンテキスト超過したセッションはもう使えない。新しいセッションを開く。

### Step 3: 新規セッションで再開

```
User: "J.A.R.V.I.S.、.jarvis/rescue.mdから作業を引き継いで再開。Task #11から続けて。"
```

`.jarvis/`以下にファイルが残っていれば、完全に状態を復元できる。

---

## 予防のためのチェックリスト

セッション開始時：

```
[ ] タスク数が15以上の場合、事前にチェックポイント計画を立てる
[ ] .jarvis/ディレクトリを作成しておく
[ ] progress.mdテンプレートを用意
```

エージェント（Markユニット）の義務：

```
[ ] 長い分析結果は必ず.jarvis/にファイル保存
[ ] SendMessageは100行以内
[ ] 完了報告は「完了 + ファイルパス」のみ
[ ] タスク10個ごとにprogress.md更新
```

---

## 実際にやってみた構成

```
.jarvis/
├── progress.md          # 全タスクの状態（チェックポイント）
├── task01_result.json   # Task #1の詳細結果
├── task02_result.json   # Task #2の詳細結果
├── ...
└── rescue.md            # 緊急時の状態保存
```

この構成にしてから、長時間セッションのcontext limitに当たる頻度が大幅に減った。

仮に当たっても、rescue.mdがあれば5分で復元できる。

---

## なぜこれで効くか

コンテキストウィンドウはRAMのようなもの。有限で揮発性。

ファイルシステムはディスクのようなもの。大容量で永続的。

AIエージェントの設計でよくある失敗は「RAMに全部詰め込もうとすること」。重要な状態はディスク（ファイル）に書いておき、コンテキストには「何がどこにあるか」だけを持つ。これが正しい設計。

---

## まとめ

- マルチエージェント長時間セッションでcontext limitは避けられない問題
- 対策は「ファイルベース通信」一択
- 詳細な分析結果は`.jarvis/`以下のファイルに保存
- メッセージには「ファイルパス」だけを送る
- 10タスクごとにprogress.mdへチェックポイント保存
- 緊急時はrescue.mdに状態保存 → 新規セッション → 再開

Carliniの言葉通り：チャット履歴ではなくファイルシステムを状態管理に使う。

---

## 関連記事

- [J.A.R.V.I.S. Iron Legion: マルチエージェント並列コーディング実践](#)
- [claude-mem-lite: Claudeのセッション間メモリをSQLite+FTS5で実現した話](#)
