---
title: "Claude Code月$800超え問題：Opus・Sonnet・Codexの最適な使い分け"
emoji: "💰"
type: "tech"
topics: ["ClaudeCode", "AI", "コスト最適化", "開発効率"]
published: false
---

## はじめに：月$800の衝撃

Claude ProMAX（週$200）を契約している。それでも週のトークンリミットを超えてしまう。単純計算で月$800以上のコスト。

原因を分析したところ、**Claude Opusを全てのタスクに使っていた**ことが判明した。トークン消費量の80%以上がOpus。これでは予算が持たない。

しかし、闇雲にSonnetに切り替えても品質が落ちる。特に複雑なCUDAカーネル実装やマルチファイル修正では、Opusの推論能力が必要だ。

この記事では、**Claude Opus、Claude Sonnet、OpenAI Codex、Google Geminiを適材適所で使い分け、コストを80%削減しながら品質を維持する方法**を解説する。

## 問題：なぜOpusを使いすぎるのか

### Claude Codeのモデルコスト構造

Claude Codeでは、セッション起動時とTask agentでモデルを選択できる：

```bash
# セッション起動時
claude --model opus    # 高コスト
claude --model sonnet  # 低コスト

# Task agent（コード内）
Task(model="opus", prompt="CUDA実装...")
Task(model="sonnet", prompt="テスト実行...")
```

### トークン単価の差

公開されている価格（2026年2月時点）：

| モデル | 入力 (MTok) | 出力 (MTok) | 相対コスト |
|--------|------------|------------|----------|
| Claude Opus 4.6 | $15 | $75 | **5x** |
| Claude Sonnet 4.5 | $3 | $15 | 1x |
| OpenAI Codex (GPT-5.3) | $2.5 | $10 | **0.67x** |

**Opusは Sonnet の5倍、Codexの7.5倍のコスト。**

### なぜOpusに依存してしまうのか

Claude Codeを使い始めたとき、こう考えた：

> 「複雑な実装は失敗すると手戻りが大きい。最初から最強モデルを使おう」

結果：

- セッション本体をOpusで起動
- 全てのTask agentをOpusで実行
- 軽微なファイル操作もOpusが処理
- ドキュメント執筆もOpus

**Opusが全てをやっていた。** これがコスト爆発の原因。

## 解決策：3層デリゲーションモデル

コスト最適化の鍵は、**各モデルのユニークな強みだけを使う**こと。

### デリゲーション構造

```
Sonnet (オーケストレーター) - 最安値のClaude
  ├── Codex CLI (workspace-write) → 新規コード生成 [最安]
  ├── Task(model="opus")          → 既存コード修正のみ [高コスト]
  ├── Codex CLI (read-only)       → コードレビュー、分析
  └── Gemini CLI                  → リサーチ、大規模解析
```

### 各モデルの役割

#### 1. Sonnet（セッション本体）

**役割**: ルーティング、意思決定、軽作業

- ユーザーの要求を理解
- 適切なエージェントに振り分け
- 簡単なファイル操作（<50行）
- Git操作、テスト実行

**なぜSonnetか**: オーケストレーションに高度な推論は不要。コストを抑えつつ全体を管理。

#### 2. Codex（新規コード生成）

**役割**: スタンドアロンな新規コードの生成

```bash
# Codex CLI経由で呼び出し
codex exec --model gpt-5.3-codex \
  --sandbox workspace-write \
  --full-auto "CUDAカーネルを新規実装"
```

**なぜCodexか**:

- **コスト**: Opusの1/7.5
- **品質**: コード生成能力はOpusとほぼ同等
- **制約**: ツール統合がないため、既存ファイルの反復修正は苦手

**適用例**:

- 新しいPythonモジュール作成
- 独立したCUDAカーネル実装
- データ処理スクリプト
- テストコード生成

#### 3. Opus（既存コード修正）

**役割**: 既存コードベースの複雑な修正、反復的なビルド・テスト

```python
# Task agentでOpusを明示的に指定
Task(model="opus", prompt="""
既存のCUDAカーネル backward.cu を修正して
メモリリークを修正し、テストが通るまで反復せよ
""")
```

**なぜOpusか**:

- ツール統合：Read/Edit/Bash/Buildを組み合わせた反復作業
- 複雑な依存関係の理解
- エラーからの自己修復能力

**適用例**:

- 既存のマルチファイル修正
- ビルドエラーの修正ループ
- 複雑なバグ修正（スタックトレース→原因特定→修正→検証）
- レガシーコードのリファクタリング

#### 4. Gemini（リサーチ・大規模解析）

**役割**: 情報収集、ドキュメント分析

```bash
# Gemini CLI
gemini -p "CUDA 12.8の新機能を調査" 2>/dev/null

# コードベース全体分析（1Mトークンコンテキスト）
gemini -p "このプロジェクトの設計を分析" \
  --include-directories . 2>/dev/null
```

**なぜGeminiか**:

- 巨大なコンテキスト（1M tokens）
- Google検索と統合
- マルチモーダル（PDF、動画解析）

**適用例**:

- ライブラリの最新ドキュメント調査
- アーキテクチャ全体の把握
- 論文・技術資料の要約

## Codex vs Opus：コード生成能力の本質的な差

### ベンチマーク結果：ほぼ互角

内部ベンチマーク（HyperRasterizer CUDAカーネル実装）：

| タスク | Codex | Opus | 勝者 |
|--------|-------|------|-----|
| 新規カーネル実装（200行） | 1回で動作 | 1回で動作 | 引き分け |
| アルゴリズム最適化 | 正しい提案 | 正しい提案 | 引き分け |
| メモリ効率分析 | 計算ミス（1回） | 正確 | Opus |
| コードスタイル | 一貫性高 | 一貫性高 | 引き分け |

**結論**: 純粋なコード生成能力では、CodexとOpusに大きな差はない。

### 本質的な差：ツール統合

では、なぜOpusを使うのか？答えは**ツール統合**。

**Codex（CLI経由）**:

- 入力：プロンプト（テキスト）
- 出力：コード（テキスト）
- 制約：既存ファイルを読めない、編集できない、実行できない

**Opus（Claude Code Task agent）**:

- 入力：プロンプト
- 処理：Read → 既存コード確認 → Edit → 修正 → Bash → ビルド → エラー確認 → Edit → 再修正
- 制約：コストが高い

### 使い分けの本質

> **ボトルネックは知能ではなく、ツール統合。**
> Codexはコードを書く能力はOpus並みだが、既存ファイルの読み込み、編集、ビルド、テストのループができない。
> **各モデルのユニークな優位性が必要な場所でのみ使え。**

## 具体的な使い分けルール

以下の決定フローに従う：

| 条件 | 選択 | 理由 |
|------|------|-----|
| 新規スタンドアロンコード（1ファイル） | **Codex CLI** | 最安、品質十分、ツール不要 |
| 既存コードの修正（ビルド・テスト必要） | **Opus Task** | ツール統合が必須 |
| 軽微な編集（<50行） | **Sonnet（自分）** | オーケストレーターで十分 |
| コードレビュー、静的解析 | **Codex CLI (read-only)** | 低コスト、読み取りのみで十分 |
| 設計トレードオフ相談 | **Codex CLI (read-only)** | 分析能力十分 |
| ライブラリ調査、最新情報 | **Gemini CLI** | 検索統合、巨大コンテキスト |
| 大規模コードベース理解 | **Gemini CLI** | 1Mトークンコンテキスト |
| Git操作、テスト実行 | **Sonnet（自分）** | 推論不要、コマンド実行のみ |

### 判断に迷ったら

```
このタスクは「既存コードを50行以上修正し、ビルド・テストが必要」か？
  → Yes: Task(model="opus")
  → No:  新規コード？ → Codex CLI
         軽微な修正？ → Sonnet（自分）
         分析？      → Codex CLI (read-only)
         調査？      → Gemini CLI
```

## 実装方法

### 1. セッション起動

```bash
# 常にSonnetで起動（デフォルト）
claude --model sonnet

# Opusは使わない（Task agentで部分的に使う）
```

### 2. Sonnet オーケストレーター設定

`.claude/rules/orchestra.md`（グローバル設定）：

```markdown
# ROLE
You are the Sonnet-class Orchestrator.
You do NOT deeply implement unless explicitly instructed.
Your job is routing, gating, and decision compression.

# DELEGATION MAP

## Opus Task Agent (model="opus") — Implementation ONLY
CUDA kernel implementation → Task(model="opus")
Complex multi-file refactoring → Task(model="opus")
Existing code modification with build/test loop → Task(model="opus")

## Codex CLI — New Code Generation
New standalone script → Codex CLI (workspace-write)
New module implementation → Codex CLI (workspace-write)
Code review → Codex CLI (read-only)
Design analysis → Codex CLI (read-only)

## Sonnet (self) — Everything Else
Light code edits (<50 LOC) → Self
File operations, config changes → Self
Test execution, build commands → Self
Git operations → Self

## Gemini CLI — Research
Library research → Gemini CLI
Codebase analysis → Gemini CLI (--include-directories)
Documentation extraction → Gemini CLI
```

### 3. Codex CLI 呼び出し

Sonnetが判断してCodexを呼ぶ：

```bash
# 新規コード生成
codex exec --model gpt-5.3-codex \
  --sandbox workspace-write \
  --full-auto "新しいCUDAカーネルを実装：
  入力：float* input (N要素)
  出力：float* output (N要素)
  処理：各要素を2倍にする
  ファイル：src/kernels/double.cu"

# コードレビュー
codex exec --model gpt-5.3-codex \
  --sandbox read-only \
  --full-auto "src/kernels/backward.cuをレビューして、
  メモリリークの可能性を指摘せよ"
```

### 4. Opus Task Agent呼び出し

既存コード修正時のみ：

```python
# Python Task agent例
result = Task(
    model="opus",
    prompt="""
    既存のCUDAカーネル backward.cu を修正：

    問題：cudaFree "invalid argument" エラー
    症状：2回目のイテレーションでクラッシュ

    手順：
    1. backward.cuを読んで問題箇所を特定
    2. 修正を実装
    3. ビルド
    4. テスト実行
    5. エラーが出たら1に戻る（最大3回）
    """
)
```

### 5. Gemini CLI 呼び出し

リサーチ時：

```bash
# ライブラリ調査
gemini -p "PyTorch 2.8とCUDA 12.8の互換性問題を調査し、
回避方法を提案せよ" 2>/dev/null

# コードベース全体分析
gemini -p "このプロジェクトのアーキテクチャを分析し、
改善点を3つ提案せよ" \
  --include-directories . 2>/dev/null
```

## コスト削減効果

### Before: Opus中心の構成

```
セッション本体: Opus（常時稼働）
  ├── ファイル読み込み → Opus
  ├── 軽微な編集 → Opus
  ├── コード生成 → Opus
  ├── ビルド実行 → Opus
  ├── テスト実行 → Opus
  └── Git操作 → Opus
```

トークン消費割合：

- Opus: 80%+
- Sonnet: 15%
- 外部ツール: 5%

**週$200のリミットを超過。実質月$800+。**

### After: 3層デリゲーション

```
セッション本体: Sonnet（常時稼働）
  ├── 新規コード → Codex CLI [7.5x cheaper]
  ├── 既存修正 → Task(opus) [必要最小限]
  ├── レビュー → Codex CLI (read-only) [7.5x cheaper]
  ├── リサーチ → Gemini CLI [別課金]
  ├── 軽微編集 → Sonnet (self)
  ├── テスト → Sonnet (self)
  └── Git → Sonnet (self)
```

トークン消費割合（Claude Code内）：

- Opus: 15%（1/5に削減）
- Sonnet: 70%
- Codex経由: 15%（Claude外課金）

**週$200のリミット内に収まる。実質月$200 + Codex API料金（月$50-100程度）。**

### 試算：月額コスト比較

仮定：月間500Mトークン消費（入出力合計）

| 構成 | 内訳 | 月額コスト |
|------|------|-----------|
| **Before（Opus中心）** | Opus 400M + Sonnet 100M | **$800+** |
| **After（3層）** | Opus 75M + Sonnet 350M + Codex 75M | **$280** |
| **削減率** | - | **-65%** |

実際の削減効果は使用パターンに依存するが、**50-70%のコスト削減**は現実的。

## Geminiの戦略的活用

Geminiは別課金（Google AI Studio）だが、Claude Codeと組み合わせると強力。

### 使用例1：大規模コードベース理解

新しいプロジェクトに参加したとき：

```bash
# プロジェクト全体を1回で解析（1M token context）
gemini -p "このコードベースのアーキテクチャを分析：
- 主要コンポーネント
- データフロー
- 依存関係
- 改善提案" \
  --include-directories . \
  > .claude/docs/architecture-analysis.md

# Claude Codeセッションで参照
cat .claude/docs/architecture-analysis.md
```

**効果**: Claudeで全ファイルを逐次読むより圧倒的に安い。

### 使用例2：ライブラリ最新情報

```bash
# 2026年の最新情報を取得（Google検索統合）
gemini -p "PyTorch 2.9とCUDA 12.8の互換性問題、
2026年2月時点の状況と回避策" 2>/dev/null
```

Claude Code単体では知識カットオフ（2025年1月）の制約があるが、Geminiで補完。

### 使用例3：マルチモーダル解析

```bash
# PDF論文から実装ヒントを抽出
gemini -p "この論文のアルゴリズムを抽出し、
Python実装の疑似コードを生成" \
  < paper.pdf 2>/dev/null

# 技術動画から要点抽出
gemini -p "このGPU最適化の講演動画から、
CUDA Shared Memory最適化のベストプラクティスを抽出" \
  < lecture.mp4 2>/dev/null
```

Claudeでは不可能なマルチモーダル処理をGeminiに委譲。

## 注意点：過度なCodex依存の落とし穴

### 問題：統合コストの逆転

Codexに全てを任せると、かえってコストが増える場合がある：

**例：既存コードの反復修正**

```
パターンA（Codex過度依存）:
1. Codex: コード生成 → ファイル出力
2. Sonnet: ファイル読み込み（トークン消費）
3. Sonnet: ビルド実行
4. Sonnet: エラーログ読み込み（トークン消費）
5. Sonnet: エラーをCodexに転送（トークン消費）
6. Codex: 修正コード生成 → ファイル出力
7. Sonnet: ファイル読み込み... （無限ループ）

結果：Sonnetのトークン消費が爆発

パターンB（Opus直接）:
1. Opus Task: Read → 理解 → Edit → 修正 → Build → Test → (必要なら再Edit)

結果：Opusで閉じるため、全体コストは低い
```

### 教訓：反復が必要なタスクはOpusに任せる

**Codexが有効な条件**:

- 1回で完結するコード生成
- 既存コードとの連携が不要
- ビルド・テストが不要（または外部で実行）

**Opusが有効な条件**:

- 既存コードの修正
- ビルド → エラー → 修正のループ
- 複数ファイルの同時編集

### バランスの取り方

```
新規機能開発の例：

1. 設計相談 → Codex (read-only) [安い]
2. 新規ファイル生成 → Codex (workspace-write) [安い]
3. 既存コードとの統合 → Opus Task [高いが必要]
4. テスト追加 → Codex (workspace-write) [安い]
5. バグ修正ループ → Opus Task [高いが必要]
```

**目安**: Opusは全体の15-30%のトークンに抑える。それ以上はアーキテクチャ見直し。

## 実践的なワークフロー例

### ケース1：新しいPythonモジュール作成

```bash
# Step 1: 設計相談（Codex read-only）
codex exec --model gpt-5.3-codex --sandbox read-only \
  --full-auto "データ処理パイプラインの設計：
  入力：CSV（100万行）
  処理：フィルタ → 集計 → 可視化
  出力：HTMLレポート
  最適なアーキテクチャを提案せよ"

# Step 2: 実装（Codex workspace-write）
codex exec --model gpt-5.3-codex --sandbox workspace-write \
  --full-auto "data_pipeline.pyを実装：
  [設計内容をペースト]"

# Step 3: テスト（Sonnet）
uv run pytest tests/test_data_pipeline.py -v

# Step 4: もしテスト失敗 → Opusで修正
# （この段階で初めてOpusを投入）
```

**コスト**: Step 1-3はCodex/Sonnetで済むため、Opusは最小限。

### ケース2：既存CUDAカーネルのバグ修正

```bash
# Step 1: 問題分析（Codex read-only）
codex exec --model gpt-5.3-codex --sandbox read-only \
  --full-auto "src/kernels/backward.cuを分析：
  エラーログ: [ログ貼り付け]
  原因を特定せよ"

# Step 2: 修正実装（Opus Task - ツール統合が必須）
Task(model="opus", prompt="""
Codexの分析によると、thread_localキャッシュが原因。
backward.cuを修正し、ビルド・テストを繰り返して動作確認せよ。
""")
```

**コスト**: 分析はCodex、実装はOpus。役割分担で最適化。

### ケース3：新機能の調査から実装まで

```bash
# Step 1: 技術調査（Gemini）
gemini -p "WebGPUでの3D Gaussian Splattingレンダリング、
2026年のベストプラクティスと既存ライブラリを調査" \
  > .claude/docs/research/webgpu-3dgs.md

# Step 2: 設計（Codex read-only）
codex exec --model gpt-5.3-codex --sandbox read-only \
  --full-auto "$(cat .claude/docs/research/webgpu-3dgs.md)
  この情報を元に、WebGPUレンダラーのアーキテクチャを設計"

# Step 3: 新規実装（Codex workspace-write）
codex exec --model gpt-5.3-codex --sandbox workspace-write \
  --full-auto "WebGPU Gaussian Splatting レンダラーを実装：
  [設計をペースト]"

# Step 4: 既存コードとの統合（Opus Task）
Task(model="opus", prompt="""
生成されたWebGPUレンダラーを既存のビューアに統合せよ。
src/viewer/index.tsを修正し、動作確認。
""")
```

**コスト**: 調査・設計・新規実装は安価なツールで。統合のみOpus。

## まとめ：最もコスパが高い戦略

### 核心的な原則

> **各モデルのユニークな強みだけを使え。**

- **Codex**: 新規コード生成（ツール不要）
- **Opus**: 既存コード修正（ツール統合必須）
- **Sonnet**: オーケストレーション（推論不要）
- **Gemini**: リサーチ・大規模解析（巨大コンテキスト）

### コスト削減のチェックリスト

- [ ] セッションは常にSonnetで起動
- [ ] 新規コード生成はCodex CLIに委譲
- [ ] Opus Taskは既存コード修正のみ
- [ ] コードレビューはCodex read-only
- [ ] 技術調査はGemini CLI
- [ ] Opusのトークン消費率を15-30%に抑える

### 避けるべきアンチパターン

- ❌ セッションをOpusで起動
- ❌ 全てのTask agentをOpusで実行
- ❌ 軽微な編集にOpusを使う
- ❌ ドキュメント執筆にOpusを使う
- ❌ 新規コード生成にOpusを使う（Codexで十分）
- ❌ Codexに既存コード修正を任せる（ツール不要なら良いが）

### 実装の第一歩

1. `.claude/rules/orchestra.md` を作成（本記事の設定例を参考）
2. セッション起動を `claude --model sonnet` に変更
3. 既存のTask呼び出しを見直し、model引数を明示
4. Codex CLI、Gemini CLIをセットアップ

### 期待される効果

- **コスト**: 50-70%削減（月$800 → $280程度）
- **品質**: ほぼ維持（適材適所の配置で）
- **速度**: 軽いタスクはむしろ高速化（Sonnet/Codexの起動が速い）

### 最後に

AI開発ツールのコストは、**モデルの性能ではなく、使い方で決まる**。

Opusは強力だが、全てに使う必要はない。Codexは安価だが、ツール統合が必要な場面では不十分。Sonnetは十分賢く、オーケストレーションには最適。

**ボトルネックは知能ではなく、ツール統合。** この原則を理解すれば、コストを抑えつつ、生産性を最大化できる。

月$800超えで悩んでいる開発者の参考になれば幸いだ。

## 参考

- [Claude Code Documentation](https://docs.anthropic.com/claude-code)
- [OpenAI Codex CLI](https://openai.com/codex)
- [Gemini API Documentation](https://ai.google.dev/)
- [Claude Pricing](https://www.anthropic.com/pricing)

---

**筆者について**: CUDA/3D Graphics開発者。HyperRasterizer（3D Gaussian Splatting高速化）プロジェクトでClaude Code多用。月$800超えの経験から、本記事の最適化手法を確立。現在は月$200-300で運用中。
