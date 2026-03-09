---
title: "OSSにPRを出したら1 pushで30本のCIジョブが全滅した話"
emoji: "🔥"
type: "tech"
topics: ["oss", "github", "ci", "typescript", "continuede"]
published: false
published_at: "2026-02-26 21:00"
---

## はじめに

OSSへのコントリビュートは楽しい。が、油断すると地獄になる。

先日、Continue.dev（VS Code向けのAI coding assistant拡張）にPRを出した。`ToolExtras`という型を拡張する、シンプルな機能追加のつもりだった。

結果として、**4〜5回のpushで30本以上のCIジョブが毎回発火**し、GitHubのメール通知が爆発した。

この記事では、その失敗の詳細と、「二度とやらない」ために策定したルールを共有する。

---

## 何をやろうとしていたか

Continue.devは`ToolExtras`という型を使って、ツール実行時に追加コンテキストをAIに渡せる。

```typescript
// 変更前
export interface ToolExtras {
  ide: IDE;
  llm: ILLM;
}

// 変更後（提案）
export interface ToolExtras {
  ide: IDE;
  llm: ILLM;
  fetch: (url: string, options?: RequestInit) => Promise<Response>;
  tool: Tool;
  config: ContinueConfig;
}
```

小さな変更だ。型に3フィールドを追加して、呼び出し側で渡すだけ。

---

## 何が起きたか: push地獄の全記録

### 1回目のpush: 「動くでしょ」

TypeScriptのコードを書き、ローカルで軽く確認してpushした。

**CI結果**: 30本以上のジョブが発火。`prettier`チェックで複数ファイルが失敗。

```
Run pnpm prettier --check .
[warn] src/extension/src/tools/definitions.ts
[warn] src/core/tools/callTool.ts
[warn] Forgot to run Prettier?
```

「あ、フォーマット忘れた」と思い、変更ファイルだけに`prettier --write`を実行してpush。

### 2回目のpush: 「今度こそ」

**CI結果**: またfail。今度は違うファイルでprettierエラー。

```
[warn] extensions/vscode/src/extension.ts
[warn] gui/src/components/mainInput/ToolCallDisplay.tsx
```

「え、俺が変更してないファイルまで？」と混乱した。

`prettier --write`を実行した範囲が狭すぎた。**変更ファイルだけでは不十分だった**のだ。

### 3回目のpush: リポジトリ全体にフォーマット

`pnpm format`でリポジトリ全体にフォーマットをかけた。ローカルで`pnpm format:check`を実行して0 issues。pushした。

**CI結果**: またfail。今度は自分が変更していないファイルでprettierエラーが出ている。

絶望した。「なぜ？ローカルでは0 issuesだったのに」

調査すると原因がわかった。**mainブランチに新しいコミットが入っており、そのコミットが未フォーマットのファイルを持ち込んでいた**。

自分のブランチはmainから分岐した時点のスナップショットを持っており、mainの更新を反映していなかった。

### 4回目のpush: rebase + format

```bash
git fetch origin main
git rebase origin/main
pnpm format
pnpm format:check  # 0 issues
git add <明示的にファイル指定>
git commit --amend --no-edit
git push --force-with-lease
```

**CI結果**: prettierは通った。今度はTypeScriptの型エラー。

```
src/core/tools/callTool.ts:47:5 - error TS2339: Property 'fetch' does not exist on type 'ToolExtras'.
```

自分でフィールドを追加したのに、呼び出し側の一部で型が更新されていなかった。

### 5回目のpush: 全エラーを一括修正して最終push

`tsc --noEmit`で全エラーをリストアップ。一括修正してpush。

ようやくCIが緑になった。

---

## 学んだこと: なぜ失敗したか

### 根本原因: 「1つ直したらpush」思考

```
エラー発見 → 修正 → push → CI wait(5-10分) → 次のエラー発見 → 修正 → push → ...
```

この繰り返しが地獄の元凶だ。

1 push = 30+ CIジョブ = 5〜10分の待ち + 30通の通知メール。

**4〜5回のpush = 150本以上のCIジョブ発火 = 通知の嵐**だった。

### 問題点の整理

| 問題 | 根本原因 |
|------|---------|
| prettier失敗（変更ファイル外） | 全体フォーマットを忘れた |
| prettier失敗（mainの新コミット） | git rebase origin/mainを忘れた |
| rebase後のprettier再適用忘れ | 新ファイルのフォーマット漏れ |
| TypeScript型エラー | tsc --noEmitをpush前に実行していなかった |

---

## 策定したルール: Push前チェックリスト

```bash
# 1. mainブランチのリベース（必須）
git fetch origin main && git rebase origin/main

# 2. リポジトリ全体のフォーマット（変更ファイルだけではNG）
pnpm format

# 3. フォーマットチェック（0 issuesになるまで進まない）
pnpm format:check

# 4. TypeScriptコンパイルチェック
pnpm tsc --noEmit 2>&1 | grep 'error TS'

# 5. テスト実行
pnpm vitest run <変更に関係するテストファイル>

# 6. コミットメールの確認（CLAボット対策）
git log --format='%ae %an' -1

# 全部OKになってから → push（1回だけ）
git push
```

### CLAボット問題

Continue.devはCLA（Contributor License Agreement）署名を要求する。PRを作ると、CLAボットがコメントを投稿し、PRコメントで`I have read the CLA Document and I hereby sign the CLA`と返信することで署名完了になる。

が、**コミットのemailがGitHubアカウントに紐付いていない**と、CLAボットがfailする。

```bash
# NG: ローカルのデフォルト設定
git log --format='%ae %an' -1
amabito@local  # GitHubに登録されていないメール

# OK: GitHubアカウントに紐付いたメール
amabito@users.noreply.github.com
```

これもpush前に確認すべきチェック項目だ。

---

## Continue.dev固有の注意点

### テストフレームワークの混在

Continue.devのリポジトリには`vitest`と`Jest`が混在している。

```
*.vitest.ts → vitestで実行
*.test.ts → Jestで実行
```

**命名を間違えるとフレームワーク競合でCIが全滅する**。

変更するコードに近いテストがどちらのフレームワークを使っているか、まず確認する必要がある。

```bash
# 確認方法
grep -r "from \"vitest\"" --include="*.ts" -l | head -5
grep -r "from \"jest\"" --include="*.ts" -l | head -5
```

### ToolExtras型の必須フィールド

`ToolExtras`を実装する全ての箇所で、新フィールドを渡す必要がある。

```typescript
// callTool.tsなど、ToolExtrasを構築している全箇所
const extras: ToolExtras = {
  ide,
  llm,
  fetch,  // 追加した全フィールドが必要
  tool,
  config,
};
```

`tsc --noEmit`は必ず実行すること。

---

## OpenClaw（別のPR）で学んだこと

同時期に、OpenClaw（Rustベースのコードフォーマッター）にもPRを出した。ここでは**さらに厄介な問題**が起きた。

OpenClawは`oxfmt 0.33.0`を使っており、`experimentalSortImports`オプションが有効になっている。このため、フォーマットの変更のほぼ全てが**import順序の変更**になる。

### 二重のrebase問題

1. 自分がmainから分岐してPRを作成
2. 他の誰かがmainにコミットを入れる（そのコミットも未フォーマットファイルを含む）
3. 自分がrebase → pnpm format → push

という手順でも失敗した。なぜなら、**step 2で入ったコミットのファイルがフォーマットされていないまま**で、CIでは自分のPRに起因するフォーマットエラーとして検出されるからだ。

**解決策**:

```bash
# 毎回このフローを守る
git fetch origin main
git rebase origin/main
pnpm format        # rebase後にもう一度実行
pnpm format:check  # 0 issuesを確認
```

### `git add -A`は使わない

`.archive/`ディレクトリや一時ファイルを巻き込む可能性がある。

```bash
# NG
git add -A

# OK: ファイルを明示的に指定
git add src/core/tools/callTool.ts
git add src/extension/src/tools/definitions.ts
```

---

## 結論: 1 push原則

**OSSにPRを出すときの鉄則は「ローカルで全検証してから1回だけpush」だ。**

```
1. git fetch origin main && git rebase origin/main
2. pnpm format（全体）
3. pnpm format:check（0 issues確認）
4. pnpm tsc --noEmit（型エラー0確認）
5. pnpm vitest run <関連テスト>
6. git log --format='%ae' -1（メール確認）
↓
全部OK → git push（1回だけ）
```

CIは「確認ツール」ではなく「最終検証ツール」として使う。

「CIで確認しながら直す」という姿勢が、通知地獄の元凶だった。

---

## まとめ

| 失敗パターン | 原因 | 対策 |
|------------|------|------|
| 変更ファイルだけprettier | 全体フォーマット必要 | `pnpm format`（全体） |
| rebase後のformat忘れ | mainの新コミットに未フォーマットあり | rebase後に再format |
| TypeScriptエラー | tsc確認未実施 | `tsc --noEmit`必須 |
| CLA fail | コミットメール不一致 | GitHub登録メール確認 |
| テスト命名ミス | vitest/Jest混在 | フレームワーク確認 |

**4〜5回のpushで150本以上のCIジョブを発火させた経験を、次のOSS貢献に活かす。**
