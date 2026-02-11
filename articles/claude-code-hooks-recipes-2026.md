---
title: "Claude Code Hooks実践レシピ10選：自動レビュー・テスト・通知を仕組み化"
emoji: "🪝"
type: "tech"
topics: ["ClaudeCode", "自動化", "AI開発", "Hooks"]
published: true
---

## はじめに

Claude Code（やCursorなどのAI開発ツール）の生産性を最大化するには、**Hooksによる自動化**が不可欠です。

本記事では、実際に運用している10個のHooksレシピを紹介します。自動テスト、Codexレビュー、通知、コスト追跡など、開発フローを劇的に効率化する実践的な設定を解説します。

## Hooksとは

**Hooks**は、Claude Codeの特定のイベント（ファイル編集、コミット、ツール実行など）に反応して自動的にシェルコマンドを実行する仕組みです。

### 主要なHookタイプ

```bash
# ツール実行前
pre-tool

# ツール実行後
post-tool

# ファイル書き込み前
pre-write

# ファイル書き込み後
post-write

# Git操作関連
pre-commit
post-commit
```

### 設定場所

```
~/.claude/hooks/        # グローバル設定
.claude/hooks/          # プロジェクト固有設定
```

プロジェクト固有のhooksはグローバル設定より優先されます。

## Recipe 1: 自動テスト実行

### 目的
ファイル編集後、自動的にテストを実行して即座にフィードバック。

### 設定

```bash
# .claude/hooks/post-write
#!/bin/bash

FILE="$1"

# Pythonファイルが変更された場合のみ実行
if [[ "$FILE" == *.py ]]; then
    # テストファイル自体は除外
    if [[ "$FILE" != *test_* ]] && [[ "$FILE" != *_test.py ]]; then
        echo "Running tests after editing $FILE..."
        pytest tests/ -v --tb=short -x
    fi
fi
```

### 実行例

```
# Claude Codeがファイルを編集
$ edit src/models/user.py

# Hook自動実行
Running tests after editing src/models/user.py...
============= test session starts =============
tests/test_user.py::test_create_user PASSED
tests/test_user.py::test_validate_email PASSED
============= 2 passed in 0.5s =============
```

### 注意点
- `-x` オプションで最初のエラーで停止（高速フィードバック）
- テストファイル自体の編集では実行しない（無限ループ回避）

## Recipe 2: Codex自動レビュー

### 目的
Git commit時に自動的にCodexでコードレビューを実行。

### 設定

```bash
# .git/hooks/post-commit
#!/bin/bash

REVIEW_SCRIPT="$HOME/.codex/scripts/multi-phase-review.py"

if [ -f "$REVIEW_SCRIPT" ]; then
    echo "Running Codex review..."
    python "$REVIEW_SCRIPT"
fi
```

### multi-phase-review.py（簡略版）

```python
#!/usr/bin/env python3
import subprocess
import json
from pathlib import Path

def get_latest_commit_diff():
    """Get diff of the latest commit."""
    result = subprocess.run(
        ['git', 'show', 'HEAD'],
        capture_output=True,
        text=True
    )
    return result.stdout

def run_codex_review(diff: str) -> dict:
    """Run Codex review via CLI."""
    prompt = f"""
Review this code change:

{diff}

Provide:
1. Severity (LOW/MEDIUM/HIGH/CRITICAL)
2. Issues found
3. Concrete fix suggestions
4. Performance impact
"""

    result = subprocess.run(
        ['codex', 'exec', '--model', 'gpt-5.3-codex',
         '--sandbox', 'read-only', '--full-auto', '-'],
        input=prompt,
        capture_output=True,
        text=True
    )

    return {'output': result.stdout}

def main():
    diff = get_latest_commit_diff()

    # Classify risk level
    if 'CUDA' in diff or '__global__' in diff:
        print("CRITICAL risk detected (CUDA kernel)")
    elif len(diff.split('\n')) > 150:
        print("HIGH risk detected (large change)")
    else:
        print("MEDIUM risk - running basic review")

    review = run_codex_review(diff)

    # Save review
    review_dir = Path.home() / '.codex' / 'reviews'
    review_dir.mkdir(parents=True, exist_ok=True)

    review_file = review_dir / 'last_review.json'
    with open(review_file, 'w') as f:
        json.dump(review, f, indent=2)

    print(f"Review saved to {review_file}")

if __name__ == '__main__':
    main()
```

### 実行例

```bash
$ git commit -m "feat: implement stream compaction"
[main abc1234] feat: implement stream compaction
 3 files changed, 150 insertions(+)

Running Codex review...
CRITICAL risk detected (CUDA kernel)
Analyzing...
Review saved to ~/.codex/reviews/last_review.json
```

### 注意点
- CUDA/GPUコードは自動的にCRITICALレベルでレビュー
- レビュー結果は次回のClaude Codeセッションで参照可能

## Recipe 3: Lint自動チェック

### 目的
ファイル書き込み前にLintエラーをチェックし、自動修正。

### 設定

```bash
# .claude/hooks/pre-write
#!/bin/bash

FILE="$1"

if [[ "$FILE" == *.py ]]; then
    echo "Linting $FILE..."

    # ruffで自動修正
    ruff check "$FILE" --fix
    ruff format "$FILE"

    if [ $? -ne 0 ]; then
        echo "Lint failed for $FILE"
        exit 1
    fi
fi
```

### 実行例

```
# Claude Codeがファイルを書き込もうとする
Writing to src/main.py...

# Hook自動実行
Linting src/main.py...
Fixed 3 errors
Formatted successfully

# 修正されたファイルが書き込まれる
```

### 注意点
- `pre-write` は書き込み前に実行されるため、修正内容が反映される
- Lint失敗時は `exit 1` でファイル書き込みを中止

## Recipe 4: 自動フォーマット

### 目的
ファイル保存時に自動的にフォーマットを適用。

### 設定

```bash
# .claude/hooks/post-write
#!/bin/bash

FILE="$1"

case "$FILE" in
    *.py)
        ruff format "$FILE"
        ;;
    *.ts|*.tsx|*.js|*.jsx)
        prettier --write "$FILE"
        ;;
    *.rs)
        rustfmt "$FILE"
        ;;
    *.go)
        gofmt -w "$FILE"
        ;;
esac
```

### 実行例

```
# ファイル書き込み後
Post-write hook: formatting src/main.py
Formatted successfully
```

## Recipe 5: セキュリティスキャン

### 目的
依存関係変更時に自動的に脆弱性スキャンを実行。

### 設定

```bash
# .claude/hooks/post-write
#!/bin/bash

FILE="$1"

# 依存関係ファイルが変更された場合
if [[ "$FILE" == "pyproject.toml" ]] || [[ "$FILE" == "requirements.txt" ]]; then
    echo "Running security scan..."

    # pip-audit for Python
    pip-audit

    if [ $? -ne 0 ]; then
        echo "⚠️ Security vulnerabilities found!"
        echo "Run 'pip-audit' for details."
    fi
fi

if [[ "$FILE" == "package.json" ]]; then
    echo "Running npm audit..."
    npm audit
fi
```

### 実行例

```
$ edit pyproject.toml
# ... add dependency ...

Running security scan...
Found 2 vulnerabilities:
- requests: CVE-2023-XXXX (HIGH)
- urllib3: CVE-2023-YYYY (MEDIUM)

⚠️ Security vulnerabilities found!
```

## Recipe 6: CUDA Build検証

### 目的
CUDAファイル変更後、自動的にビルドを実行して検証。

### 設定

```bash
# .claude/hooks/post-write
#!/bin/bash

FILE="$1"

if [[ "$FILE" == *.cu ]] || [[ "$FILE" == *.cuh ]]; then
    echo "CUDA file changed. Verifying build..."

    cd "$(git rev-parse --show-toplevel)"

    # WSL2でビルド（より安定）
    wsl -d Ubuntu-24.04 -- bash -c "
        cd /mnt/d/work/Projects/$(basename $(pwd))/src/hyper_rasterizer && \
        python3 setup.py build_ext --inplace
    "

    if [ $? -eq 0 ]; then
        echo "✓ Build successful"
    else
        echo "✗ Build failed - check CUDA code"
        exit 1
    fi
fi
```

### 実行例

```
# CUDAファイル編集後
CUDA file changed. Verifying build...
Building extension...
✓ Build successful
```

## Recipe 7: 長時間タスク完了通知

### 目的
長時間実行されるタスク（ビルド、テストなど）が完了したら通知。

### 設定

```bash
# .claude/hooks/post-tool
#!/bin/bash

TOOL="$1"
DURATION="$2"  # seconds

# 30秒以上かかったタスクのみ通知
if [ "$DURATION" -gt 30 ]; then
    # Windows通知（PowerShell経由）
    powershell.exe -Command "
        \$notify = New-Object -ComObject Wscript.Shell
        \$notify.Popup('Task completed: $TOOL', 5, 'Claude Code', 64)
    "

    # または、Discord Webhookで通知
    # curl -X POST "$DISCORD_WEBHOOK" \
    #   -H "Content-Type: application/json" \
    #   -d "{\"content\": \"Task completed: $TOOL ($DURATION sec)\"}"
fi
```

### 実行例

```
# 長時間タスク実行中...
Running tests...
(45 seconds later)

# Windows通知が表示される
"Task completed: pytest (45 sec)"
```

## Recipe 8: 破壊的操作前のバックアップ

### 目的
大規模なリファクタリングやファイル削除前に自動バックアップ。

### 設定

```bash
# .claude/hooks/pre-tool
#!/bin/bash

TOOL="$1"

# 破壊的操作を検出
if [[ "$TOOL" == *"rm"* ]] || [[ "$TOOL" == *"delete"* ]] || [[ "$TOOL" == *"refactor"* ]]; then
    BACKUP_DIR="$HOME/.claude/backups/$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$BACKUP_DIR"

    # プロジェクト全体をバックアップ
    rsync -a --exclude='.git' --exclude='node_modules' --exclude='__pycache__' \
          . "$BACKUP_DIR/"

    echo "Backup created: $BACKUP_DIR"
fi
```

### 実行例

```
User: "Refactor the entire codebase to use new architecture"

Pre-tool hook executing...
Backup created: /home/user/.claude/backups/20260207_143022

Proceeding with refactoring...
```

## Recipe 9: API コスト追跡

### 目的
Claude Code APIの使用量を追跡し、コスト超過を防止。

### 設定

```bash
# .claude/hooks/post-tool
#!/bin/bash

TOOL="$1"
TOKENS_USED="$2"  # Assuming this is passed by Claude Code

# コストログに追記
LOG_FILE="$HOME/.claude/cost_log.csv"

if [ ! -f "$LOG_FILE" ]; then
    echo "timestamp,tool,tokens,model,cost_usd" > "$LOG_FILE"
fi

# モデルに応じたコスト計算（例）
MODEL="sonnet"  # or "opus"
if [ "$MODEL" == "opus" ]; then
    COST=$(echo "scale=6; $TOKENS_USED * 0.000015" | bc)  # $15/M tokens
else
    COST=$(echo "scale=6; $TOKENS_USED * 0.000003" | bc)  # $3/M tokens
fi

echo "$(date -Iseconds),$TOOL,$TOKENS_USED,$MODEL,$COST" >> "$LOG_FILE"

# 日次コスト集計
TODAY=$(date +%Y-%m-%d)
TODAY_COST=$(grep "^$TODAY" "$LOG_FILE" | cut -d',' -f5 | paste -sd+ | bc)

echo "Today's cost: \$$TODAY_COST"

# 閾値チェック（例: $10/day）
if (( $(echo "$TODAY_COST > 10" | bc -l) )); then
    echo "⚠️ Daily cost limit exceeded!"
fi
```

### 実行例

```
Task completed
Tokens used: 15000
Today's cost: $0.045

# 次のタスク
Tokens used: 25000
Today's cost: $0.12

# 閾値超過
Tokens used: 350000
Today's cost: $11.25
⚠️ Daily cost limit exceeded!
```

## Recipe 10: セッションコンテキスト保存

### 目的
重要な会話内容を自動的にメモリに保存（claude-mem-lite連携）。

### 設定

```bash
# .claude/hooks/post-tool
#!/bin/bash

TOOL="$1"
OUTPUT="$2"

# 特定のキーワードを含む出力を自動保存
if echo "$OUTPUT" | grep -qE "(CRITICAL|BUG|IMPORTANT|TODO)"; then
    # claude-mem-liteに保存
    python "$HOME/.claude/claude_mem_lite/cli.py" add \
        --content "$OUTPUT" \
        --source "auto-hook" \
        --tags "auto,$(date +%Y-%m-%d)"

    echo "Context saved to claude-mem"
fi
```

### 実行例

```
Claude: "CRITICAL: Found memory leak in CUDA kernel..."

Post-tool hook executing...
Context saved to claude-mem

# 後で検索可能
$ python ~/.claude/claude_mem_lite/cli.py search "memory leak"
Found 1 result:
[2026-02-07] CRITICAL: Found memory leak in CUDA kernel...
```

## Hooksの組み合わせ例

### パターン1: 安全なCUDA開発フロー

```bash
# 1. CUDA編集前: バックアップ (pre-write)
# 2. CUDA編集後: ビルド検証 (post-write)
# 3. コミット時: Codexレビュー (post-commit)
# 4. レビュー結果: claude-memに保存 (post-tool)
```

### パターン2: CI/CDスタイルの自動チェック

```bash
# 1. ファイル編集前: Lint (pre-write)
# 2. ファイル編集後: フォーマット (post-write)
# 3. ファイル編集後: テスト実行 (post-write)
# 4. テスト失敗: 通知 (post-tool)
```

### パターン3: コスト最適化フロー

```bash
# 1. タスク実行前: 今日のコスト確認 (pre-tool)
# 2. タスク実行後: トークン使用量記録 (post-tool)
# 3. 閾値超過: Sonnetに切り替え推奨 (post-tool)
```

## トラブルシューティング

### 問題1: Hookが実行されない

**チェック項目:**
```bash
# 実行権限があるか確認
ls -la .claude/hooks/
# -rwxr-xr-x が正しい

# 権限がない場合
chmod +x .claude/hooks/*

# Shebang（#!/bin/bash）があるか確認
head -1 .claude/hooks/post-write
```

### 問題2: Hookでエラーが発生する

**デバッグ方法:**
```bash
# Hookを直接実行してエラーを確認
bash -x .claude/hooks/post-write test.py

# ログファイルに出力を追加
#!/bin/bash
exec 2>> /tmp/claude-hook-error.log
set -x  # デバッグモード
```

### 問題3: Hookが重すぎて遅い

**最適化:**
```bash
# バックグラウンド実行
(long_running_task &)

# 条件を厳しくする
if [[ "$FILE" == "src/"* ]]; then  # src/配下のみ
    run_tests
fi

# キャッシュを活用
if [ -f ".test_cache" ] && [ "$FILE" -ot ".test_cache" ]; then
    echo "Tests already passed (cached)"
    exit 0
fi
```

## Hooksのベストプラクティス

### 1. Fail-safe設計

```bash
# エラーが起きてもClaude Codeを止めない
set +e  # エラーでスクリプトを終了しない

command_that_might_fail || echo "Warning: command failed"
```

### 2. 冪等性を保つ

```bash
# 何度実行しても同じ結果
mkdir -p "$DIR"  # -pで既存ディレクトリでもエラーにしない
```

### 3. プロジェクト固有とグローバルを使い分け

```
~/.claude/hooks/          # 全プロジェクト共通（Lint, Format）
.claude/hooks/            # プロジェクト固有（CUDA build, 特殊テスト）
```

### 4. 環境変数で制御

```bash
# デバッグ時だけ詳細ログ
if [ "$CLAUDE_DEBUG" = "1" ]; then
    set -x
fi

# 特定のHookを無効化
if [ "$SKIP_AUTO_TEST" = "1" ]; then
    exit 0
fi
```

## まとめ

Claude Code Hooksを活用することで、以下を自動化できます：

1. **品質保証**: 自動テスト、Lint、Codexレビュー
2. **安全性**: バックアップ、セキュリティスキャン
3. **生産性**: 自動フォーマット、ビルド検証
4. **可視性**: コスト追跡、通知、コンテキスト保存

**推奨Hooks（優先順位順）:**
1. 自動テスト実行（即時フィードバック）
2. Codex自動レビュー（品質向上）
3. Lint/Format（コード品質）
4. コスト追跡（予算管理）
5. 破壊的操作前のバックアップ（安全性）

Hooksを適切に設定することで、Claude Codeがより強力な開発パートナーになります。ぜひ、プロジェクトに合わせてカスタマイズしてみてください。

## 参考資料

- Claude Code公式ドキュメント
- Git Hooks ガイド: https://git-scm.com/docs/githooks
- codex CLI ドキュメント
- ruff ドキュメント: https://docs.astral.sh/ruff/
