---
title: "【有料】Claude Code完全活用ガイド【プロンプト集+自動化設定】"
emoji: "🚀"
type: "tech"
topics: ["Claude", "AI", "生産性", "自動化", "プログラミング"]
published: true
published_at: "2026-01-05 07:00"
price: 980
---

# この記事で得られるもの

**Claude Codeを使い倒すための実践的なノウハウ。**

- コピペで使える**プロンプトテンプレート集**
- 開発効率を最大化する**CLAUDE.md設定例**
- 繰り返し作業を自動化する**スキル設定**
- 実際のプロジェクトでの**活用事例**

**対象読者:** Claude Codeを使い始めた人、もっと効率を上げたい人

---

# 無料記事のおさらい

- Claude Codeで開発効率3倍
- コンテキストを与える、段階的に依頼
- セキュリティクリティカルな場面は避ける

今回は**実践的なテクニック**を解説する。

---

:::message
ここから有料パートです。
:::

# プロンプトテンプレート集

## 1. 新機能実装

```markdown
# タスク
[機能名] を実装してください。

# 要件
- [要件1]
- [要件2]
- [要件3]

# 技術的な制約
- 既存の [ファイル名] のパターンに従う
- [ライブラリ名] を使用する
- テストも一緒に書く

# 参考ファイル
- src/services/example.ts（似た機能の実装例）

# 出力
- 実装コード
- テストコード
- 必要に応じてマイグレーション
```

## 2. バグ修正

```markdown
# エラー内容
[エラーメッセージをコピペ]

# 再現手順
1. [手順1]
2. [手順2]
3. [手順3]

# 期待する動作
[正しい動作の説明]

# 調査と修正をお願いします
- 原因の特定
- 修正コード
- 再発防止策（必要であれば）
```

## 3. リファクタリング

```markdown
# 対象
[ファイルパス or ディレクトリ]

# 目的
- [目的1: 例) 可読性向上]
- [目的2: 例) パフォーマンス改善]
- [目的3: 例) テスタビリティ向上]

# 制約
- 外部インターフェースは変更しない
- 既存のテストが通ること
- 段階的に変更（1ファイルずつ確認）

# 進め方
1. まず計画を提示してください
2. 私が承認したら実行してください
```

## 4. コードレビュー

```markdown
# レビュー対象
[ファイルパス or git diff]

# 観点
- [ ] ロジックの正しさ
- [ ] エッジケースの考慮
- [ ] セキュリティ
- [ ] パフォーマンス
- [ ] 可読性
- [ ] テストの網羅性

# 出力形式
| 重要度 | ファイル:行 | 指摘内容 | 修正案 |
|--------|------------|---------|--------|
| 高/中/低 | path:line | ... | ... |
```

## 5. テスト生成

```markdown
# 対象
[ファイルパス]

# テストフレームワーク
[Jest / pytest / Go testing など]

# 要件
- ユニットテスト
- 正常系・異常系を網羅
- エッジケースを含む
- モックは [ライブラリ名] を使用

# 特に確認してほしいケース
- [ケース1]
- [ケース2]
```

## 6. ドキュメント生成

```markdown
# 対象
[ファイルパス or プロジェクト全体]

# ドキュメント種類
- [ ] README.md
- [ ] API仕様書
- [ ] 関数のJSDoc/docstring
- [ ] 設計ドキュメント

# フォーマット
[Markdown / OpenAPI / など]

# 含める内容
- 概要
- インストール方法
- 使用例
- APIリファレンス
```

---

# CLAUDE.md設定例

## 基本テンプレート

```markdown
# プロジェクト設定

## 概要
[プロジェクトの簡単な説明]

## 技術スタック
- 言語: TypeScript 5.x
- フレームワーク: Next.js 14 (App Router)
- DB: PostgreSQL + Prisma
- テスト: Jest + React Testing Library
- CI: GitHub Actions

## ディレクトリ構造
```
src/
├── app/          # Next.js App Router
├── components/   # Reactコンポーネント
├── lib/          # ユーティリティ
├── services/     # ビジネスロジック
└── types/        # 型定義
```

## コーディング規約
- 関数: アロー関数で統一
- 命名: camelCase（変数・関数）、PascalCase（型・コンポーネント）
- インポート順: React → ライブラリ → 内部モジュール
- コメント: 「なぜ」を書く、「何を」は書かない

## コミットメッセージ
```
<type>: <subject>

<body>
```
type: feat, fix, refactor, test, docs, chore

## よく使うコマンド
- `npm run dev`: 開発サーバー起動
- `npm run test`: テスト実行
- `npm run lint`: リント
- `npm run build`: ビルド

## 注意事項
- 環境変数は .env.local に（.env.example を参照）
- 機密情報はコードに含めない
- PRを作る前に `npm run lint && npm run test` を実行
```

## プロジェクト固有の追加設定

```markdown
## API設計方針
- RESTful（リソース指向）
- レスポンスは { data, error, meta } 形式
- エラーは HTTP ステータスコードに従う

## 状態管理
- サーバー状態: React Query
- クライアント状態: Zustand
- フォーム: React Hook Form + Zod

## 認証
- JWT（アクセストークン + リフレッシュトークン）
- トークンは httpOnly Cookie に保存
- 認証が必要なAPIは /api/auth/* 以下

## デプロイ
- main ブランチへのマージで自動デプロイ（Vercel）
- 本番環境への変更は必ずPRを経由
```

---

# スキル設定（自動化）

## スキルとは

繰り返し行うタスクをコマンド化できる機能。

```
~/.claude/skills/
├── commit/
│   └── SKILL.md
├── review/
│   └── SKILL.md
└── test/
    └── SKILL.md
```

## コミットスキル

```markdown
# ~/.claude/skills/commit/SKILL.md

# Commit Skill

## 使い方
`/commit` または `/commit -m "メッセージ"`

## 動作
1. `git status` で変更を確認
2. `git diff` で差分を確認
3. 適切なコミットメッセージを生成
4. ユーザーに確認
5. `git add` & `git commit` を実行

## コミットメッセージ規約
- feat: 新機能
- fix: バグ修正
- refactor: リファクタリング
- test: テスト追加
- docs: ドキュメント
- chore: その他

## 例
```
feat: ユーザー認証機能を追加

- JWT認証を実装
- ログイン/ログアウトAPIを追加
- 認証ミドルウェアを追加
```
```

## レビュースキル

```markdown
# ~/.claude/skills/review/SKILL.md

# Review Skill

## 使い方
`/review` または `/review src/services/user.ts`

## 動作
1. 対象ファイルを読み込む（指定がなければ変更ファイル）
2. 以下の観点でレビュー:
   - ロジックの正しさ
   - セキュリティ
   - パフォーマンス
   - 可読性
   - テスト網羅性
3. 問題点を一覧で出力
4. 重要度（高/中/低）を付与

## 出力形式
| 重要度 | 場所 | 問題 | 修正案 |
|--------|------|------|--------|
```

## テストスキル

```markdown
# ~/.claude/skills/test/SKILL.md

# Test Skill

## 使い方
`/test src/services/user.ts`

## 動作
1. 対象ファイルを解析
2. 関数・メソッドを抽出
3. 各関数のテストを生成:
   - 正常系
   - 異常系
   - エッジケース
4. テストファイルを作成

## 設定
- フレームワーク: Jest
- モック: jest.mock()
- 配置: 同ディレクトリに .test.ts
```

---

# 実践的な活用事例

## 事例1: APIエンドポイント追加（15分）

```bash
# プロンプト
> /implement
> 商品検索APIを追加してください
>
> エンドポイント: GET /api/products/search
> クエリパラメータ:
> - q: 検索キーワード（必須）
> - category: カテゴリID（任意）
> - minPrice, maxPrice: 価格範囲（任意）
> - page, limit: ページネーション
>
> レスポンス: { data: Product[], meta: { total, page, limit } }
>
> src/app/api/products/route.ts のパターンに従ってください

# Claude Codeの出力
1. src/app/api/products/search/route.ts を作成
2. src/services/product.ts に searchProducts() を追加
3. src/types/product.ts に SearchParams 型を追加
4. テストファイルを作成
```

## 事例2: バグ修正（10分）

```bash
# プロンプト
> このエラーが本番で発生しています:
>
> TypeError: Cannot read property 'email' of null
> at sendWelcomeEmail (src/services/email.ts:42)
>
> ユーザー登録後にウェルカムメールを送る処理で、
> 稀に user が null になるようです。
>
> 原因を調査して修正してください。

# Claude Codeの出力
1. 原因特定: 非同期処理の競合状態
2. 修正: null チェックを追加
3. 根本対策: トランザクションで囲む提案
4. テスト追加: 競合状態のテストケース
```

## 事例3: レガシーコード移行（1時間）

```bash
# プロンプト
> src/legacy/ 以下のJavaScriptファイルを
> TypeScriptに移行してください。
>
> 進め方:
> 1. まず移行計画を提示
> 2. 私が確認したら1ファイルずつ移行
> 3. 各ファイルの移行後にテスト実行
>
> 制約:
> - any は使わない
> - 外部インターフェースは変更しない
> - 移行前後でテストが通ること

# Claude Codeの出力
1. 移行計画（依存関係を考慮した順序）
2. ファイルごとの型定義
3. 段階的な移行（確認しながら）
4. 移行完了レポート
```

---

# 効率化のための設定

## .claudeignore

```
# Claude Codeに読ませないファイル
node_modules/
.git/
dist/
build/
*.log
.env*
credentials.json
```

## エイリアス設定

```bash
# ~/.bashrc or ~/.zshrc
alias cc="claude"
alias ccr="claude --resume"  # 前回のセッションを継続
```

---

# まとめ

| カテゴリ | 内容 |
|---------|------|
| プロンプト | テンプレート化で品質安定 |
| CLAUDE.md | プロジェクト設定を明文化 |
| スキル | 繰り返しタスクを自動化 |
| 活用事例 | 実装/バグ修正/移行 |

**Claude Codeは「設定」と「プロンプト」で効率が大きく変わる。**

---

# 関連記事

- [Claude Codeで開発効率3倍](https://zenn.dev/amabito/articles/claude-code-productivity) - 無料版
- [エンジニア1年目で年収1000万](https://zenn.dev/amabito/articles/engineer-salary-1000man) - キャリア
