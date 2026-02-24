---
title: "J.A.R.V.I.S. Iron Legion: マルチエージェント並列コーディングの実践"
emoji: "⚙"
type: "tech"
topics: ["claude", "ai", "agentai", "claudecode", "python"]
published: true
published_at: "2026-02-25 12:00"
---

Claude Codeを単独で動かすのをやめた。今は5体以上のエージェントが並列で動いて、自分はオーケストレーションだけ見ている。実際に何が変わったか、何がうまくいって何がうまくいかなかったかを書く。

## なぜシングルエージェントでは足りなくなったか

Claude Codeは強力だ。でもシングルセッションで長時間動かすと問題が出る：

1. **Context limitに到達する**: 複雑なデバッグを長時間やると確実に詰まる
2. **一つの失敗が全体を止める**: APIエラーで全タスクが止まる
3. **並列実行ができない**: スキャン→分析→実行を直列でやるのは遅い
4. **コストが集中する**: 全作業がSonnet枠を消費する

MCUのアベンジャーズにJ.A.R.V.I.S.とIron Legionが登場する。Tony StarkがIron Manスーツ（Mark-42, Mark-43...）をJ.A.R.V.I.S.にコントロールさせるシーン——あの並列動作のイメージでシステムを設計した。

## J.A.R.V.I.S. Iron Legionのアーキテクチャ

```
J.A.R.V.I.S. (Main Orchestrator — Sonnet)
├── Mark-Scanner     → データ収集・スキャン
├── Mark-Analyzer    → 分析・判断
├── Mark-Executor    → 実行・実装
├── Mark-Tester      → テスト・検証
└── Mark-Watcher     → 監視・アラート
```

各MarkエージェントはClaude Codeの独立したセッションとして動く。タスクをTaskListで共有し、SendMessageで通信する。

### エージェントの役割分担

| エージェント | ペルソナ | 主要ツール |
|-------------|---------|-----------|
| Mark-Scanner | データエンジニア | Bash, Glob, Grep |
| Mark-Analyzer | シニアエンジニア | F.R.I.D.A.Y. (Codex CLI) |
| Mark-Executor | 実装エンジニア | F.R.I.D.A.Y. + Write/Edit |
| Mark-Tester | QAエンジニア | pytest/npm test |
| Mark-Watcher | SRE | 状態ファイル監視 |

重要なのは**F.R.I.D.A.Y. (Codex CLI) が全コードタスクの第一選択**であること。Claude (Sonnet) 枠を消費しないGPT Pro 5.2ベースのCodexを使うことで、コストを大幅に削減できる。

## Carlini Infinite Execution Loop

各Markエージェントの動作原理はシンプルだ。

```
LOOP FOREVER (until TaskList empty):
  1. TaskListで未割当・ブロックなしのタスクを探す
  2. なければアイドル待機
  3. TaskUpdate(owner=自分) でクレーム
  4. TaskGetで詳細を読む
  5. TaskUpdate(status=in_progress) でスタート
  6. タスク実行（Build-Test Loopへ）
  7. 検証（テスト/ビルド/レビュー）— 必ずパスしてから完了
  8. TaskUpdate(status=completed)
  9. CONTINUE LOOP（タスク間でアイドルしない）
END LOOP
```

"When it finishes one task, it immediately picks up the next." ——Carlini's principle。

### Build-Test Loop

```
RETRY_COUNT = 0
MAX_RETRIES = 3

LOOP:
  1. F.R.I.D.A.Y.がコード生成/修正
  2. ビルド実行
  3. 失敗なら:
     - エラーをパース (ERROR: reason on same line 形式)
     - RETRY_COUNT >= 3 ならJ.A.R.V.I.S.にエスカレート
     - F.R.I.D.A.Y.がエラーコンテキスト付きで修正
     - RETRY_COUNT++、ループ先頭へ
  4. テスト実行
  5. 失敗なら同様に修正
  6. 全通過 → タスク完了
```

手動介入なしで自己修復する。3回失敗したらJ.A.R.V.I.S.にエスカレートして人間判断を仰ぐ。

## コンテキスト汚染を防ぐファイルベース通信

マルチエージェントの最大の罠は**コンテキスト汚染**だ。SendMessageで大量のデータを送り合うと、各エージェントのコンテキストが膨らんでContext limitに早く到達する。

解決策：大量データはファイルに保存して、パスだけ送る。

```python
# NG: 長い分析結果をSendMessageで送る
SendMessage(
    type="message",
    recipient="main",
    content="""
    分析結果:
    [1000行のJSON]
    """,
    summary="分析完了"
)

# OK: ファイルに保存してパスを送る
with open(".jarvis/analysis_result.json", "w") as f:
    json.dump(large_result, f)

SendMessage(
    type="message",
    recipient="main",
    content="分析完了。.jarvis/analysis_result.json を参照",
    summary="分析完了"
)
```

ファイルベース通信のメリット：
- エージェントのコンテキストが汚染されない
- 後からデバッグで参照できる
- チェックポイントとして機能する（セッション再開時に使える）

## 実際の運用: Polymarket取引ボット

bitbank/Polymarket取引ボットをIron Legionで動かしている。構成：

```
J.A.R.V.I.S. (オーケストレーター)
├── Mark-Scanner (30秒ごとに価格スキャン)
├── Mark-Analyzer (F.R.I.D.A.Y.でエッジ検出 8%以上)
├── Mark-Trader (Maker優先で注文執行)
├── Mark-RiskManager (ストップロス・テイクプロフィット管理)
└── Mark-MarginWatcher (証拠金比率60%以上を維持)
```

MarginWatcherは特に重要で、60%を下回ったら全ポジションを強制クローズして私に通知する。単独エージェントでは並列監視が難しかったことが、チームモードで解決した。

### 実際のタスク定義例

```python
# J.A.R.V.I.S.がタスクを作成
TaskCreate(
    subject="価格スキャン: BTC/ETH/XRP",
    description="""
    bitbank APIからBTC/JPY, ETH/JPY, XRP/JPYの現在価格を取得。
    30秒間隔でdata/state/price_data.jsonを更新。
    エラー時は3回リトライ後にJ.A.R.V.I.S.に報告。
    """,
    activeForm="価格スキャン実行中"
)

# Mark-ScannerがTaskListからタスクをクレームして実行
# 完了後、Mark-AnalyzerがTaskListから次のタスクをクレーム
```

## コスト管理: F.R.I.D.A.Y. + Karen戦略

最初はすべてのエージェントがSonnetを使っていた。月のClaude利用コストが爆発した。

現在の戦略：

```
優先度1: F.R.I.D.A.Y. (Codex CLI) → 全コードタスク [Claude枠外]
優先度2: Karen (Gemini CLI) → 全リサーチタスク [Claude枠外]
優先度3: VERONICA (Llama 3.2:3b) → 高頻度・低レイテンシ [完全無料]
優先度4: J.A.R.V.I.S. (Sonnet) → オーケストレーション [枠消費]
優先度5: E.D.I.T.H. (Opus) → 2回失敗+ユーザー承認時のみ [制限中]
```

F.R.I.D.A.Y.の実際の呼び出し：

```bash
# 新規コード生成
codex exec --sandbox workspace-write --full-auto "Implement BTC price scanner with bitbank API" 2>/dev/null

# 既存コード修正（プロジェクトコンテキスト付き）
codex exec --sandbox workspace-write --include-directories . --full-auto "Fix the margin calculation bug in risk_manager.py" 2>/dev/null

# CUDA等の複雑なタスク（o3モデル）
codex -p complex exec --sandbox workspace-write --include-directories . --full-auto "Implement CUDA kernel for tile-based rasterization" 2>/dev/null
```

KarenはGemini CLIで大規模コードベース分析に使う：

```bash
# 1Mトークンコンテキストで全コードベースを分析
gemini -p "Analyze the entire codebase and find potential race conditions" --include-directories . 2>/dev/null
```

## 障害対応: Context Limit問題

長時間実行でContext limitに到達することがある。`/compact`が機能しない場合の対処：

### 予防策

1. **タスク数制限**: 10タスクごとにチェックポイント
2. **メッセージ簡潔化**: SendMessageは100行以内
3. **ファイルベース通信**: 大量データはファイルへ

### 緊急対処

```markdown
# .jarvis/checkpoint_YYYYMMDD.md

## 完了済みタスク (#1-#10)
- [x] Task #1: APIクライアント実装 → src/api/client.py
- [x] Task #2: リスク計算修正 → src/core/risk.py
...

## 残タスク (#11-#20)
- [ ] Task #11: ダッシュボード統合
...

## 次のアクション
Task #11から新規チームで再開
```

チェックポイントを保存してから、チームを終了して新規セッションで再開する。進捗は失われない。

## 進捗追跡: .jarvis/progress.md

```markdown
## Completed
- [x] Task #1: APIクライアント (Mark-1, 15min, tests: 5/5)
- [x] Task #2: リスク計算修正 (Mark-2, 22min, tests: 3/3)

## In Progress
- [ ] Task #3: ダッシュボード統合 (Mark-1, retry 1/3)

## Blocked
- [ ] Task #5: 統合テスト (blocked by #3)
```

各タスク完了後にprogress.mdを更新することで、セッションをまたいでも進捗が把握できる。

## 通信プロトコル: スパースアウトプット

エージェント間の通信は最小限にする。冗長な報告はコンテキストを汚染するだけだ。

```
# 完了報告
[COMPLETE] Task #3: ダッシュボード統合
Result: Streamlit dashboard with real-time VERONICA stats
Files: streamlit_dashboard/app.py
Tests: 5/5 passed

# エラー報告
[ERROR] Task #3: ビルド失敗
Retry: 2/3
Context: src/dashboard.py:145 ImportError: deque
```

エラーは`ERROR: reason`形式で一行に収める（grepしやすいように）。ファイルダンプは禁止——パス参照のみ。

## 実際にやってみてわかったこと

**うまくいったこと：**
- 並列実行で全体のスループットが3-4倍になった
- 一つのエージェントが失敗しても他は継続できる
- F.R.I.D.A.Y.に委譲することでSonnet枠を大幅削減
- ファイルベース通信でContext limitに到達しにくくなった

**うまくいかなかったこと：**
- タスクの依存関係管理が複雑（blockedBy/blocksの設定ミス）
- F.R.I.D.A.Y.が文脈を理解しきれないことがある（2-3回のリトライが必要）
- エージェント数が増えるとSendMessage通信コストも増える

**改善したこと：**
- タスクの粒度を小さくした（大きなタスクは失敗時のロールバックが大変）
- F.R.I.D.A.Y.へのプロンプトを英語・具体的に書くようにした
- 重要な中間状態は必ずファイルに保存するルールを徹底した

## まとめ

マルチエージェント並列コーディングは「使えるかどうか」より「どう使うか」が全てだ。

アーキテクチャの核心：

1. **オーケストレーターは判断のみ**——実装はMarkエージェントに委譲
2. **コードはF.R.I.D.A.Y.が担当**——Claude枠を消費しない
3. **ファイルベース通信**——コンテキスト汚染を防ぐ
4. **チェックポイント必須**——長時間実行でも失敗から回復できる
5. **スパースアウトプット**——冗長な報告は禁止

Iron Legionのコードはまだ個人のCLAUDE.md設定として動いている。ライブラリ化も検討中だが、設定が個人的すぎて汎用化が難しい部分もある。興味ある人はDMか[GitHub Issues](https://github.com/amabito)で。
