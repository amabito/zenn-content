---
title: "Git Worktreeで並列AI開発：Claude Codeを3-5セッション同時運用する方法"
emoji: "🌳"
type: "tech"
topics: ["Git", "ClaudeCode", "開発効率", "AI開発"]
published: true
---

## はじめに

AI駆動開発では、Claude CodeやCursor、GitHub Copilotなどのツールが強力なコンテキストを保持しながら作業を進めます。しかし、従来の `git checkout` によるブランチ切り替えは、このコンテキストを破壊してしまいます。

Boris Cherny氏（『Programming TypeScript』著者）は、**Git Worktreeを使った並列セッション運用**を「生産性向上のための最重要テクニック」として推奨しています。本記事では、実際の3DGS開発プロジェクトでの運用経験を基に、その実践方法を解説します。

## なぜWorktreeなのか

### 従来の問題点：Branch切り替えによるContext破壊

```bash
# Feature Aの開発中...
$ git checkout feature-a
$ claude-code  # AIが文脈を理解してコーディング

# 急にFeature Bの修正が必要に
$ git checkout feature-b  # ← ここでファイルが書き換わる
$ claude-code  # さっきのコンテキストが失われている
```

**問題:**
- ブランチ切り替えで作業ディレクトリのファイルが物理的に変更される
- Claude Codeのセッションコンテキストが無効になる
- 再度説明が必要（時間とトークンのロス）

### Worktreeによる解決：物理的な分離

```bash
# 各機能が独立したディレクトリに存在
D:\work\Projects\project\              # main branch
D:\work\Projects\project-feature-a\    # feature-a branch
D:\work\Projects\project-feature-b\    # feature-b branch
```

**メリット:**
- ブランチごとに完全に独立した作業環境
- 各ディレクトリでClaude Codeセッションを起動
- コンテキスト切り替えゼロ
- 同時に複数の機能を並行開発可能

## Worktreeのセットアップ

### 基本コマンド

```bash
# メインリポジトリ（通常通りclone）
$ git clone https://github.com/user/project.git
$ cd project

# Feature A用のworktreeを作成
$ git worktree add ../project-feature-a feature-a

# Feature B用のworktreeを作成
$ git worktree add ../project-feature-b feature-b

# 実験用worktreeを作成
$ git worktree add ../project-exp experiments

# 作成されたworktreeを確認
$ git worktree list
/path/to/project              abc123 [main]
/path/to/project-feature-a    def456 [feature-a]
/path/to/project-feature-b    ghi789 [feature-b]
/path/to/project-exp          jkl012 [experiments]
```

### 新規ブランチと同時にworktreeを作成

```bash
# ブランチがまだ存在しない場合
$ git worktree add -b new-feature ../project-new-feature

# -b オプションで新規ブランチを同時に作成
```

## 推奨構成パターン

Boris Cherny氏の推奨する4種類のworktree構成を紹介します。

### 1. Main Worktree（安定版）

**用途:**
- 安定版の開発
- レビュー済みコードのマージ
- リリース準備
- ドキュメント更新

**Claude Codeの使い方:**
- 安定的なタスク
- バグ修正
- リファクタリング

### 2. Feature Worktrees（並列機能開発）

**用途:**
- 独立した機能の並行開発
- 各機能が独自のブランチを持つ

**Claude Codeの使い方:**
- 各worktreeで独立したセッションを起動
- 機能Aと機能Bを同時に開発

```bash
# Terminal 1: Feature A専用
$ cd D:\work\Projects\project-feature-a
$ claude-code
# 「Feature Aの実装を続けてください」

# Terminal 2: Feature B専用（同時実行）
$ cd D:\work\Projects\project-feature-b
$ claude-code
# 「Feature Bのテストを追加してください」
```

### 3. Experiment Worktree（実験用）

**用途:**
- リスクの高い実験
- 大規模リファクタリング
- 新技術の検証
- 失敗しても良い環境での探索的開発

**Claude Codeの使い方:**
- 「これは実験なので、大胆にリファクタリングして」
- 失敗してもmainに影響しない安心感

### 4. Analysis Worktree（データ分析専用）

**用途:**
- ログファイルの読み込み・分析
- BigQueryでのデータ調査
- プロファイリング結果の解析

**Claude Codeの使い方:**
- 大容量ログファイルの分析
- Gemini連携での大規模データ処理

```bash
# ログ分析専用worktree
$ cd D:\work\Projects\project-analysis
$ gemini -p "Analyze error patterns in production logs" < logs/prod-2026-02.log
```

## 実例：3DGS開発プロジェクトでの運用

私が開発している3DGS（3D Gaussian Splatting）プロジェクトでの実例を紹介します。

### プロジェクト構成

```
D:\work\Projects\
├── 3dgs-unified\              # Main: 安定版HyperSplat V26開発
├── 3dgs-unified-exp\          # Experiments: 実験的機能
└── hyper-viewer\              # 別プロジェクト（WebGPUビューア）
```

### ワークフロー例

```bash
# Main worktree: 安定版の開発
$ cd D:\work\Projects\3dgs-unified
$ claude-code
# 「V26のバグ修正を進めてください」

# Experiment worktree: Stream Compaction実験（並行実行）
$ cd D:\work\Projects\3dgs-unified-exp
$ git checkout exp/stream-compaction
$ claude-code
# 「Phase 7-Bのstream compactionを最適化してください」
```

### マージフロー

```bash
# Experimentで実験が成功した場合
$ cd D:\work\Projects\3dgs-unified-exp
$ git add .
$ git commit -m "feat: Implement stream compaction optimization"
$ git push origin exp/stream-compaction

# Main worktreeでマージ
$ cd D:\work\Projects\3dgs-unified
$ git checkout main
$ git merge exp/stream-compaction
$ git push origin main
```

## 効率化Tips

### 1. エイリアスでディレクトリ移動を高速化

PowerShellプロファイルに追加：

```powershell
# C:\Users\<user>\Documents\PowerShell\Microsoft.PowerShell_profile.ps1
function za { cd D:\work\Projects\project\ }           # Main
function zb { cd D:\work\Projects\project-feature-a\ } # Feature A
function zc { cd D:\work\Projects\project-feature-b\ } # Feature B
function zd { cd D:\work\Projects\project-exp\ }       # Experiments
function ze { cd D:\work\Projects\project-analysis\ }  # Analysis
```

Bashの場合：

```bash
# ~/.bashrc
alias za='cd ~/projects/project'
alias zb='cd ~/projects/project-feature-a'
alias zc='cd ~/projects/project-feature-b'
alias zd='cd ~/projects/project-exp'
alias ze='cd ~/projects/project-analysis'
```

### 2. Terminal タブの色分け

Windows Terminalの設定例：

```json
{
  "profiles": {
    "list": [
      {
        "name": "Main",
        "startingDirectory": "D:\\work\\Projects\\project",
        "tabColor": "#00FF00"
      },
      {
        "name": "Feature A",
        "startingDirectory": "D:\\work\\Projects\\project-feature-a",
        "tabColor": "#0000FF"
      },
      {
        "name": "Experiments",
        "startingDirectory": "D:\\work\\Projects\\project-exp",
        "tabColor": "#FFFF00"
      }
    ]
  }
}
```

### 3. Worktree命名規則

```
<project>-<purpose>

例:
- hyper-viewer-webgpu-refactor
- igs-cuda-optimization
- systemoverlay-ui-redesign
```

**ポイント:**
- プロジェクト名を含める（複数プロジェクトがある場合）
- 目的を明確に（feature名、実験名など）
- ケバブケースで統一

### 4. 定期的なクリーンアップ

```bash
# Feature完成後、worktreeを削除
$ git worktree remove ../project-feature-a

# リモートブランチも削除する場合
$ git branch -d feature-a
$ git push origin --delete feature-a

# 孤立したworktreeのクリーンアップ
$ git worktree prune
```

## 最適なWorktree数

Boris Cherny氏の推奨：**3-5個**

**理由:**
- 3個未満：並列開発のメリットが薄い
- 5個超：コンテキスト切り替えコストが増大

**推奨パターン:**
```
1. Main（安定版）
2. Feature A（主機能開発）
3. Feature B（サブ機能開発）
4. Experiments（実験）
5. Analysis（データ分析）
```

## Claude Codeセッション管理

### 各Worktreeで独立したセッション

```
Worktree A (Feature A) → Claude Code セッション A
Worktree B (Feature B) → Claude Code セッション B
Worktree C (Experiments) → Claude Code セッション C
```

**重要ポイント:**
- 各セッションは完全に独立したコンテキストを持つ
- セッションAでの会話内容はセッションBに影響しない
- 同時に複数セッションを起動可能（リソース許す限り）

### セッション起動のベストプラクティス

```bash
# 各worktreeのルートディレクトリで起動
$ cd D:\work\Projects\project-feature-a
$ claude-code

# プロジェクトの文脈を最初に伝える
# 「このworktreeはFeature Aの開発用です。
#  mainブランチからの差分を確認して、続きを実装してください」
```

## トラブルシューティング

### 問題1: Worktree削除後もディレクトリが残る

```bash
# 手動でディレクトリを削除した場合
$ git worktree prune  # Gitの管理情報をクリーンアップ
```

### 問題2: 異なるWorktreeで同じブランチをチェックアウトできない

```bash
# エラー例
$ git worktree add ../project-feature-a feature-a
fatal: 'feature-a' is already checked out at '/path/to/project-feature-a'

# 解決策: 既存のworktreeを削除してから再作成
$ git worktree remove ../project-feature-a
$ git worktree add ../project-feature-a feature-a
```

### 問題3: Worktreeで.gitファイルが見つからない

Worktreeでは `.git` がディレクトリではなくファイルになります（本体を指すポインタ）。

```bash
# Worktree内
$ cat .git
gitdir: /path/to/project/.git/worktrees/project-feature-a
```

通常は問題ありませんが、`.git` がディレクトリであることを前提とするツールでは注意が必要です。

## まとめ

Git Worktreeを使った並列AI開発のメリット：

1. **コンテキスト保持**: ブランチ切り替えでAIの文脈が失われない
2. **並列開発**: 複数機能を同時進行できる
3. **安全な実験**: 実験用worktreeで失敗を恐れず試せる
4. **効率化**: エイリアス・色分けで高速な環境切り替え

**推奨構成:**
- Main（安定版）
- Feature A/B（並列開発）
- Experiments（実験）
- Analysis（データ分析）

**最適数:** 3-5個（Boris Cherny氏推奨）

Claude CodeなどのAI駆動開発では、コンテキストの維持が生産性の鍵です。Worktreeを活用して、並列セッションで開発速度を最大化しましょう。

## 参考資料

- Boris Cherny's productivity tips (Claude Code best practices)
- Git公式ドキュメント: [git-worktree](https://git-scm.com/docs/git-worktree)
- Claude Desktop App: Native worktree support by @amorriscode
