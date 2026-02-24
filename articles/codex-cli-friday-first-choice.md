---
title: "Codex CLI (F.R.I.D.A.Y.) を全コードタスクの第一選択にした理由"
emoji: "🔧"
type: "tech"
topics: ["claude", "openai", "ai", "claudecode", "codex"]
published: true
published_at: "2026-02-25 21:00"
---

Claude Codeのコストが月30万円を超えたとき、設計を見直した。全コードタスクをCodex CLI（GPT Pro 5.2）に委譲するようにしたら、Claudeの利用コストが65%下がった。何をどう変えたかを書く。

## 問題: 全作業がClaude枠を消費していた

Claude Codeを使い始めた頃は、全部Claudeに頼んでいた。コード生成、バグ修正、リファクタリング、ドキュメント生成——全部Sonnetかそれ以上のモデルが動いていた。

月末のAPI請求を見て青ざめた。

問題を分析すると：
- コード生成は高頻度で繰り返す作業
- コード修正はプロジェクトコンテキストが必要だが、それもAPI料金
- リトライが発生するとさらに倍増

解決策は「コードタスクを別のモデルに委譲する」こと。

## F.R.I.D.A.Y.とは何か

MCUでF.R.I.D.A.Y.はTony StarkのAIアシスタントだ（Female Replacement Intelligent Digital Assistant Youth）。J.A.R.V.I.S.の後継として登場し、より実践的でアイルランド訛りのキャラクターがある。

自分のシステムでは**Codex CLI（GPT Pro 5.2ベース）**をF.R.I.D.A.Y.と呼んでいる。ChatGPT Pro（$200/月）の契約内で使えるため、Claude枠を消費しない。

```
MCU AI System:
J.A.R.V.I.S. (Claude Sonnet) — オーケストレーション
F.R.I.D.A.Y. (Codex CLI)    — 全コードタスク [Claude枠外]
Karen (Gemini CLI)            — 全リサーチタスク [Claude枠外]
VERONICA (Llama 3.2:3b)      — 高頻度監視 [完全無料]
E.D.I.T.H. (Claude Opus)    — 最終手段 [制限中]
```

## 3つの実行モード

### Mode 1: コードレビュー・分析（read-only）

```bash
codex exec --sandbox read-only --full-auto "Review this code for security issues" 2>/dev/null
```

read-onlyはファイルを変更しない。設計レビュー、コードの問題点指摘、アーキテクチャ分析に使う。

### Mode 2: 新規コード生成（workspace-write）

```bash
codex exec --sandbox workspace-write --full-auto "Implement a BTC price scanner using bitbank API" 2>/dev/null
```

workspace-writeはファイルを作成・編集できる。スクラッチから新しいコードを書くとき。

### Mode 3: 既存コード修正（workspace-write + コンテキスト）

```bash
codex exec --sandbox workspace-write --include-directories . --full-auto "Fix the margin calculation bug in risk_manager.py line 291" 2>/dev/null
```

`--include-directories .`でカレントディレクトリ全体をF.R.I.D.A.Y.のコンテキストに含める。既存コードの修正・拡張はこれ。

### CUDAや複雑なアルゴリズム（o3モデル）

```bash
codex -p complex exec --sandbox workspace-write --include-directories . --full-auto "Implement CUDA kernel for tile-based Gaussian rasterization with shared memory optimization" 2>/dev/null
```

`-p complex`でo3モデルを指定する。CUDA kernelの実装や、数学的に複雑なアルゴリズムはo3が得意だ。

## 実際の委譲パターン

### パターン1: ビルドループ

```python
# J.A.R.V.I.S.がF.R.I.D.A.Y.に委譲
RETRY_COUNT = 0
MAX_RETRIES = 3

while RETRY_COUNT < MAX_RETRIES:
    # F.R.I.D.A.Y.にコード修正を依頼
    result = subprocess.run([
        "codex", "exec",
        "--sandbox", "workspace-write",
        "--include-directories", ".",
        "--full-auto",
        f"Fix the build error: {error_message}"
    ], capture_output=True, text=True)

    # ビルドを試みる
    build_result = subprocess.run(
        ["python", "setup.py", "build_ext", "--inplace"],
        capture_output=True, text=True
    )

    if build_result.returncode == 0:
        break  # 成功

    error_message = build_result.stderr
    RETRY_COUNT += 1

if RETRY_COUNT >= MAX_RETRIES:
    # J.A.R.V.I.S.にエスカレート
    notify_user(f"ERROR: Build failed after {MAX_RETRIES} retries")
```

### パターン2: コードレビュー反復

F.R.I.D.A.Y.のレビューは1回では全問題を発見できないことがある。APPROVEDが出るまで繰り返す：

```bash
# 第1回レビュー → NEEDS_FIX (5 issues)
codex exec --sandbox read-only --full-auto "Review src/risk_manager.py for production readiness"

# 修正後、第2回レビュー → NEEDS_MORE_FIX (2 issues)
codex exec --sandbox read-only --full-auto "Re-review src/risk_manager.py, previous issues were fixed. Check again."

# 再修正後、第3回レビュー → APPROVED
codex exec --sandbox read-only --full-auto "Final review of src/risk_manager.py"
```

3回の反復でAPPROVEDになったことが多い。1回で完璧を求めず、反復を前提にする方が結果がいい。

### パターン3: 長いプロンプトはstdinで渡す

```bash
codex exec --sandbox workspace-write --include-directories . --full-auto - 2>/dev/null <<'EOF'
Implement a complete trading risk manager with the following specifications:

1. Position sizing: Half Kelly 6.7% of portfolio
2. Stop-loss: 1% from entry price
3. Take-profit: 5% from entry price
4. Trailing stop: activate at +0.5%, update every +0.2%
5. Max leverage: 1.5x
6. Margin floor: 60% maintenance ratio

Requirements:
- Python type hints on all functions
- Unit tests in tests/test_risk_manager.py
- Error handling for API failures
- Logging via Python logging module

File: src/core/risk_manager.py
EOF
```

ヒアドキュメントで長い仕様をstdinとして渡せる。これでプロンプトの長さを気にしなくてよくなる。

## 判断フロー: F.R.I.D.A.Y. vs J.A.R.V.I.S. vs E.D.I.T.H.

```
コードタスク?
  → Yes → F.R.I.D.A.Y.（Codex CLI）が第一選択

    CUDA/複雑アルゴリズム?
      → F.R.I.D.A.Y. (o3モデル)
      → 失敗 → o3で再試行（タスク分割）
      → 2回失敗 → ユーザーに確認「E.D.I.T.H.に切り替えますか？」

    標準的なコード生成/修正?
      → F.R.I.D.A.Y. (gpt-5.2-codexモデル)
      → 失敗 → プロンプト改善して再試行
      → 2回失敗 → o3を試す → ユーザーに確認

    ドキュメント生成?
      → F.R.I.D.A.Y. (gpt-5.2モデル)

  → No → J.A.R.V.I.S.（Sonnet）またはKaren（Gemini CLI）
```

E.D.I.T.H.（Opus）は原則禁止。F.R.I.D.A.Y.が2回失敗してユーザーが明示的に承認した場合のみ使う。「難しそう」「複雑そう」という理由だけでは切り替えない。

## F.R.I.D.A.Y.の言語プロトコル

F.R.I.D.A.Y.へのプロンプトは**英語**で書く。

理由：
1. Codexは英語でトレーニングされており、英語の指示の方が精度が高い
2. コードのコメント・変数名・関数名は英語が自然
3. 日本語で書いてもCodexが英語で解釈するケースがある

```bash
# NG: 日本語プロンプト
codex exec --full-auto "bitbank APIを使ってBTCの価格スキャナーを実装してください"

# OK: 英語プロンプト
codex exec --full-auto "Implement a BTC price scanner using bitbank API with the following requirements:
- Fetch current price every 30 seconds
- Save to data/state/price_data.json
- Handle API rate limits with exponential backoff
- Type hints on all functions"
```

## 実際のコスト削減効果

導入前後の比較（月次）：

| モデル | 導入前 | 導入後 | 削減率 |
|-------|-------|-------|-------|
| Sonnet (J.A.R.V.I.S.) | 100% | 35% | -65% |
| Opus (E.D.I.T.H.) | 87% | 10% | -77% |
| Codex CLI (F.R.I.D.A.Y.) | 0% | 追加コストなし | - |
| Gemini CLI (Karen) | 0% | 追加コストなし | - |

コスト目標: 月¥257,720 → ¥57,720（-78%、年間240万円削減）。

F.R.I.D.A.Y.はChatGPT Proの$200/月に含まれているため追加コストがない。すでにPro契約しているなら、Codex CLIの利用は実質無料だ。

## 制限と注意点

F.R.I.D.A.Y.が得意でないこと：

**1. プロジェクト固有のアーキテクチャ知識**
`--include-directories .`でコンテキストを渡しても、大きなプロジェクトでは全体を把握しきれないことがある。重要な設計制約はプロンプトに明示的に書く必要がある。

**2. セキュリティ要件**
「APIキーをハードコードしない」「SQLインジェクション対策」等、セキュリティ要件はプロンプトに含めないと実装されないことがある。

**3. テストの自動生成**
テスト生成を明示的に依頼しないと書いてくれないことが多い。「Unit tests in tests/test_*.py」と仕様に含める。

**4. ビルドエラーの複雑なデバッグ**
MSVC + CUDA + PyTorchのような複雑なビルド環境の問題は、o3でも解決できないことがある。その場合はJ.A.R.V.I.S.（Sonnet）の出番だ。

## E.D.I.T.H.への切り替えタイミング

F.R.I.D.A.Y.で2回失敗したら、ユーザーに確認する：

```
[WARNING] F.R.I.D.A.Y. retry 2/2 failed
Task: CUDA kernel shared memory optimization
Error: ptxas error: uses too much shared data (0xcc20 bytes, 0xc000 max)

E.D.I.T.H.（Opus）に切り替えますか？
現在のOpusクォータ使用率: 12%
残クォータ: 88%

[y/n] >
```

自動でOpusに切り替えない。コスト意識を保つために人間の判断を挟む。

## まとめ

F.R.I.D.A.Y.（Codex CLI）を全コードタスクの第一選択にすることで得られるもの：

1. **コスト削減**: Claude枠を65%削減
2. **速度**: 並列で複数タスクを処理できる
3. **自律性**: Build-Test Loopで3回まで自己修復
4. **分業**: オーケストレーション（J.A.R.V.I.S.）とコード実装（F.R.I.D.A.Y.）を分離

設定は少し複雑だが、一度固めてしまえば日々の作業でClaude枠を意識しなくてよくなる。

ChatGPT Pro契約があれば今日から試せる。`codex --help`で始めてみてほしい。
