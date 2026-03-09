---
title: "claude-mem-lite: Claudeのセッション間メモリをSQLite+FTS5で実現した話"
emoji: "🧠"
type: "tech"
topics: ["ClaudeCode", "sqlite", "python", "ai", "開発効率"]
published: false
published_at: "2026-03-01 18:00"
---

## 問題：Claudeは昨日の会話を覚えていない

Claude Codeで開発していると、こういうことが起きる。

昨日の続きで作業しようとすると、「前回はどこまで進んでいたか」を一から説明しなければいけない。

「Phase 11まで終わったんだけど、Phase 12を続けて」

「Phase 11とは何ですか？」

毎回この繰り返し。

---

## 2種類のメモリを使い分ける

セッション間でコンテキストを保持する方法として、自分は2種類のメモリを使い分けている。

### MEMORY.md（手動・永続パターン）

`~/.claude/projects/<project>/memory/MEMORY.md`

安定したパターン、アーキテクチャ決定、繰り返す問題への解決策などを手動で書いておく。セッション開始時に常に読み込まれる。

```markdown
# MEMORY.md

## CUDA Index semantics mismatch (2026-01-30)
- tile-local vs global index でforward/backwardが食い違う
- 鉄則: Forward/Backward共有変数は座標系を1つに統一
...

## thread_local + PyTorch autograd (2026-02-06)
- Forward/Backwardは異なるスレッドで実行される
- 鉄則: NEVER use thread_local for cross-thread state
...
```

**特徴:**
- 内容を自分で管理（重要なパターンだけ書く）
- 200行制限（それ以上はトランケート）
- 一度書いたら何度でも参照される

### claude-mem-lite（自動・最近のアクティビティ）

`~/.claude/claude_mem_lite/`

直近のセッションで何をやったかを自動記録。「さっき何したっけ」の検索用。

---

## claude-mem-liteの設計

### アーキテクチャ

```
~/.claude/claude_mem_lite/
├── cli.py          # コマンドラインインターフェース
├── memory.db       # SQLite DB（本体）
└── hooks/
    └── startup.sh  # セッション開始時フック
```

技術スタック：
- **SQLite + FTS5** — フルテキスト検索が速い、単一ファイルで管理簡単
- **Python** — 標準ライブラリのみ、依存関係なし
- **startup hook** — Claude Code起動時に直近の活動を自動インジェクト

### FTS5を使う理由

SQLiteのFTS5（Full-Text Search version 5）は日本語を含むテキストの全文検索が効く。

```sql
-- インデックス作成
CREATE VIRTUAL TABLE memories_fts USING fts5(
    content,
    tags,
    content='memories',
    content_rowid='id'
);

-- 検索
SELECT m.*, rank
FROM memories_fts
JOIN memories m ON memories_fts.rowid = m.id
WHERE memories_fts MATCH 'Phase 11'
ORDER BY rank;
```

`bm25`スコアリングで関連度順に結果が出る。

---

## 使い方

### CLI

```bash
# 直近20件を表示
python cli.py recent 20

# キーワード検索
python cli.py search "Phase 11"
python cli.py search "CUDA gradient"

# 特定IDの詳細
python cli.py get 42

# 手動でメモリを追加
python cli.py add "3DGS学習でのLPIPS設定: conv3_3_onlyがベスト" --tags "3dgs,lpips"
```

### startup hook

Claude Code起動時に自動実行される。直近7日間のアクティビティをコンテキストに注入する。

```bash
# ~/.claude/claude_mem_lite/hooks/startup.sh
#!/bin/bash

echo "=== Recent Activity (claude-mem-lite) ==="
python ~/.claude/claude_mem_lite/cli.py recent 10 --format brief
echo "=========================================="
```

これで「前回何をしていたか」がセッション開始時に自動で見える。

---

## MEMORY.md との使い分け

| 用途 | MEMORY.md | claude-mem-lite |
|------|-----------|-----------------|
| 管理方法 | 手動 | 自動 |
| 内容 | 安定したパターン・教訓 | 直近の作業内容 |
| 参照方法 | 常時ロード | 必要時に検索 |
| 寿命 | 永続 | 90日程度 |
| 適用範囲 | プロジェクト横断 | セッション内容 |

**MEMORY.md**: 「このプロジェクトで繰り返す問題の解決策」を書く。一度遭遇したバグの教訓、アーキテクチャの決断理由など。

**claude-mem-lite**: 「先週何をしていたか」を自動記録。作業ログに近い。

---

## 実際の活用例

### セッション再開時

```bash
$ python cli.py recent 20
[2026-02-13] Task #10: Polymarketボット重複ポジション修正
  - portfolio_manager.py:291 signal_id重複チェック追加
  - active.jsonとの照合ロジック実装

[2026-02-12] VERONICA (Llama 3.2:3b) ベンチマーク
  - 26.93 req/s、キャッシュ込み1347 req/s
  - 98%キャッシュヒット率確認

[2026-02-11] LPIPS GT Feature Caching実装
  - 43.7%高速化（72.44ms → 40.80ms/iter）
  - pinned_cpu + fp16 + conv3_3_only構成で確定
...
```

これを見れば「前回どこまで進んだか」が即座にわかる。

### 忘れた設定値の検索

```bash
$ python cli.py search "LPIPS"
1. [2026-02-11] LPIPS GT Feature Caching
   pinned_cpu + fp16 + conv3_3_only
   +3.8GB VRAM、43.7%高速化

2. [2026-02-10] LPIPS頻度設定
   LPIPS@50 (every 50 iter) がベスト
   psnr: 29.07 dB
```

「あの設定何だったっけ」が検索一発でわかる。

---

## セッション回復パターン

`session-recovery.md`（ルールファイル）と組み合わせて使う。

```
ユーザー: "ビルドが途中で止まった"

J.A.R.V.I.S.:
1. git log --oneline -20  # 実際の進捗確認
2. python cli.py recent 10  # 直近のコンテキスト確認
3. python cli.py search "<キーワード>"  # 関連情報検索
```

git logが「真実」、claude-mem-liteが「文脈」を提供する。

---

## 実装のポイント

### SQLiteを選んだ理由

- サーバー不要、単一ファイルで管理
- Python標準ライブラリに含まれる（`import sqlite3`）
- FTS5で全文検索が高速
- バックアップがファイルコピーだけで済む

```python
import sqlite3
from pathlib import Path

DB_PATH = Path.home() / ".claude" / "claude_mem_lite" / "memory.db"

def search(query: str, limit: int = 10) -> list[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT m.id, m.content, m.tags, m.created_at,
                   rank
            FROM memories_fts
            JOIN memories m ON memories_fts.rowid = m.id
            WHERE memories_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (query, limit)).fetchall()
    return [dict(r) for r in rows]
```

---

## MEMORY.mdの200行制限への対処

MEMORY.mdには200行制限がある（それ以上はトランケート）。

対処法：

```
MEMORY.md（200行以内）
├── セクション1: 重要パターンへのリンク
│   - "CUDA Index semantics → cuda-index-bugs.md"
│   - "HR-DGR Gap → hr-dgr-investigation.md"
└── セクション2: 最新の教訓（直近5件程度）

詳細ファイル:
~/.claude/projects/<project>/memory/
├── cuda-index-bugs.md     # CUDAバグの詳細
├── hr-dgr-investigation.md # DGR超え調査記録
└── ...
```

MEMORY.mdはインデックスとして使い、詳細は別ファイルに分離する。

---

## まとめ

Claude Codeのセッション間メモリを2層構造で管理している：

1. **MEMORY.md**: 手動管理・永続パターン・常時ロード
2. **claude-mem-lite**: 自動記録・最近のアクティビティ・検索可能

どちらも「コンテキストをコンテキストウィンドウに詰め込まない」という設計思想は同じ。状態はファイルに書いて、必要な時に読む。

セッション間の継続性が上がると、「前回の説明をまたやり直す」というムダが減る。AIが「何を知っているか」を管理するのも、開発者の仕事の一部になってきている。
