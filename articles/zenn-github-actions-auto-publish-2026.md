---
title: "ZennをGitHub Actionsで完全自動化：キュー式スケジュール投稿の作り方"
emoji: "🤖"
type: "tech"
topics: ["Zenn", "GitHubActions", "自動化", "ブログ"]
published: true
---

## はじめに

Zennの記事執筆を自動化したい——多くのブロガーが考えることですが、実装すると意外な落とし穴があります。

本記事では、**GitHub Actionsを使ったキュー式スケジュール投稿システム**の実装方法を解説します。実際に運用中のシステムを基に、Zennの仕様の罠と回避策を詳しく紹介します。

## Zennの `published_at` の罠

### 期待：未来の日時を指定して予約投稿

Zennの記事frontmatterには `published_at` フィールドがあります。

```markdown
---
title: "明日公開される記事"
published: true
published_at: 2026-02-10 09:00
---
```

**期待される動作:**
「2026-02-10 09:00になったら公開される」

### 現実：未来日時 = 403エラー

**実際の動作:**
- `published: true` + 未来の `published_at` → **全記事リンクが403エラー**
- Zenn CLIでは正常に見えるが、デプロイ後に全記事が閲覧不能に

```
https://zenn.dev/username/articles/article-slug
→ 403 Forbidden（未来のpublished_atが1つでもあると全記事に波及）
```

### 実際に起きた事故

```yaml
# 事故当時のfrontmatter
published: true
published_at: 2026-02-08 09:00  # 2日後の日時を指定

# 結果
→ デプロイ直後、全記事が403エラー
→ ダッシュボードでは記事一覧が見える
→ ユーザーからは全記事がアクセス不能
```

**原因:**
Zennの仕様として、`published_at` に未来の日時を指定すると、記事は「存在するが公開されていない」状態になり、403エラーを返します。これが1記事でもあると、なぜか他の記事にも影響する（Zenn側のバグの可能性）。

## 解決策：キュー式スケジュール投稿

`published_at` による予約投稿は諦め、**GitHub Actionsで定期的に1記事ずつ公開する**方式に切り替えました。

### アーキテクチャ

```
publish-queue.txt          # 投稿待ち記事のキュー（1行1スラッグ）
      ↓
GitHub Actions cron        # 1日4回実行（07:00, 12:00, 18:00, 21:00 JST）
      ↓
scheduled_publish.py       # キューから1記事取り出し、published: true に変更
      ↓
tweet_new_articles.py      # 新規公開記事を自動ツイート
      ↓
git commit & push          # 変更をリポジトリにコミット
      ↓
Zenn自動デプロイ           # GitHub連携により自動反映
```

### ディレクトリ構成

```
zenn/
├── articles/
│   ├── article-1.md
│   ├── article-2.md
│   └── article-3.md
├── publish-queue.txt       # 投稿キュー
├── scripts/
│   ├── scheduled_publish.py    # スケジュール投稿スクリプト
│   └── tweet_new_articles.py   # Twitter連携スクリプト
└── .github/
    └── workflows/
        └── scheduled-publish.yml  # GitHub Actions定義
```

## 実装：キュー管理

### publish-queue.txt

1行に1つの記事スラッグを記載。上から順に処理されます。

```
git-worktree-parallel-ai-development
zenn-github-actions-auto-publish-2026
claude-code-hooks-recipes-2026
```

**運用ルール:**
- 上の記事から順に公開される
- 公開済みの記事は自動的にキューから削除される
- 新規記事を追加する場合は末尾に追記

## 実装：scheduled_publish.py

キューから1記事を取り出し、`published: true` に変更するスクリプト。

```python
#!/usr/bin/env python3
"""
Scheduled publish script for Zenn articles.
Publishes one article from the queue per execution.
"""
import os
import re
from pathlib import Path
from datetime import datetime

def read_queue(queue_file: Path) -> list[str]:
    """Read article slugs from queue file."""
    if not queue_file.exists():
        return []
    with open(queue_file, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]

def write_queue(queue_file: Path, slugs: list[str]):
    """Write remaining slugs back to queue file."""
    with open(queue_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(slugs) + '\n' if slugs else '')

def update_frontmatter(article_file: Path) -> bool:
    """Update article frontmatter to published: true."""
    with open(article_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Check current published status
    if re.search(r'^published:\s*true', content, re.MULTILINE):
        print(f"Already published: {article_file.name}")
        return False

    # Replace published: false with published: true
    new_content = re.sub(
        r'^published:\s*false',
        'published: true',
        content,
        count=1,
        flags=re.MULTILINE
    )

    # Remove published_at if exists (to avoid 403 error)
    new_content = re.sub(
        r'^published_at:.*$\n',
        '',
        new_content,
        flags=re.MULTILINE
    )

    if new_content == content:
        print(f"No changes needed: {article_file.name}")
        return False

    with open(article_file, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print(f"Published: {article_file.name}")
    return True

def main():
    """Main function."""
    repo_root = Path(__file__).parent.parent
    queue_file = repo_root / 'publish-queue.txt'
    articles_dir = repo_root / 'articles'

    # Read queue
    queue = read_queue(queue_file)
    if not queue:
        print("Queue is empty. No articles to publish.")
        return

    # Get next article
    next_slug = queue[0]
    article_file = articles_dir / f"{next_slug}.md"

    if not article_file.exists():
        print(f"Article not found: {article_file}")
        # Remove from queue and continue
        write_queue(queue_file, queue[1:])
        return

    # Publish article
    if update_frontmatter(article_file):
        # Remove from queue
        write_queue(queue_file, queue[1:])
        print(f"Successfully published and removed from queue: {next_slug}")
    else:
        # Already published, remove from queue anyway
        write_queue(queue_file, queue[1:])

if __name__ == '__main__':
    main()
```

**ポイント:**
- `published: false` → `published: true` に置換
- `published_at` があれば削除（403エラー回避）
- すでに公開済みの場合もキューから削除

## 実装：tweet_new_articles.py

新規公開された記事を自動的にTwitterに投稿するスクリプト。

```python
#!/usr/bin/env python3
"""
Tweet new Zenn articles using tweepy (Twitter API v2).
"""
import os
import re
from pathlib import Path
from datetime import datetime, timezone
import tweepy

def parse_frontmatter(content: str) -> dict:
    """Parse article frontmatter."""
    match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
    if not match:
        return {}

    frontmatter = {}
    for line in match.group(1).split('\n'):
        if ':' in line:
            key, value = line.split(':', 1)
            frontmatter[key.strip()] = value.strip().strip('"')

    return frontmatter

def is_newly_published(article_file: Path) -> bool:
    """Check if article was recently published (within last 2 hours)."""
    with open(article_file, 'r', encoding='utf-8') as f:
        content = f.read()

    fm = parse_frontmatter(content)

    # Check if published
    if fm.get('published') != 'true':
        return False

    # Check if published_at is within last 2 hours (if exists)
    if 'published_at' in fm:
        try:
            pub_time = datetime.fromisoformat(fm['published_at'].replace(' ', 'T'))
            now = datetime.now(timezone.utc)
            if (now - pub_time).total_seconds() > 7200:  # 2 hours
                return False
        except ValueError:
            pass

    # Check file modification time
    mtime = datetime.fromtimestamp(article_file.stat().st_mtime, tz=timezone.utc)
    now = datetime.now(timezone.utc)

    return (now - mtime).total_seconds() < 7200  # 2 hours

def tweet_article(title: str, slug: str):
    """Tweet article using Twitter API v2."""
    # Get credentials from environment
    api_key = os.environ.get('TWITTER_API_KEY')
    api_secret = os.environ.get('TWITTER_API_SECRET')
    access_token = os.environ.get('TWITTER_ACCESS_TOKEN')
    access_secret = os.environ.get('TWITTER_ACCESS_SECRET')
    username = os.environ.get('ZENN_USERNAME', 'your_username')

    if not all([api_key, api_secret, access_token, access_secret]):
        print("Twitter credentials not found. Skipping tweet.")
        return

    # Initialize tweepy client
    client = tweepy.Client(
        consumer_key=api_key,
        consumer_secret=api_secret,
        access_token=access_token,
        access_token_secret=access_secret
    )

    # Create tweet
    url = f"https://zenn.dev/{username}/articles/{slug}"
    tweet_text = f"📝 新しい記事を公開しました\n\n{title}\n\n{url}\n\n#Zenn"

    try:
        client.create_tweet(text=tweet_text)
        print(f"Tweeted: {title}")
    except Exception as e:
        print(f"Failed to tweet: {e}")

def main():
    """Main function."""
    repo_root = Path(__file__).parent.parent
    articles_dir = repo_root / 'articles'

    # Find newly published articles
    for article_file in articles_dir.glob('*.md'):
        if is_newly_published(article_file):
            with open(article_file, 'r', encoding='utf-8') as f:
                content = f.read()

            fm = parse_frontmatter(content)
            title = fm.get('title', 'Untitled')
            slug = article_file.stem

            tweet_article(title, slug)

if __name__ == '__main__':
    main()
```

**重要な修正ポイント:**
- `published: true` かつ `published_at` が現在時刻以前の記事のみツイート
- 未来の `published_at` を持つ記事はツイートしない（403エラー回避）
- ファイルの更新時刻を確認（2時間以内に更新された記事のみ）

## 実装：GitHub Actions

### .github/workflows/scheduled-publish.yml

```yaml
name: Scheduled Publish

on:
  schedule:
    # JST 07:00 = UTC 22:00 (前日)
    - cron: '0 22 * * *'
    # JST 12:00 = UTC 03:00
    - cron: '0 3 * * *'
    # JST 18:00 = UTC 09:00
    - cron: '0 9 * * *'
    # JST 21:00 = UTC 12:00
    - cron: '0 12 * * *'
  workflow_dispatch:  # Manual trigger for testing

jobs:
  publish:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          token: ${{ secrets.GITHUB_TOKEN }}

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install tweepy

      - name: Publish next article
        run: |
          python scripts/scheduled_publish.py

      - name: Tweet new articles
        env:
          TWITTER_API_KEY: ${{ secrets.TWITTER_API_KEY }}
          TWITTER_API_SECRET: ${{ secrets.TWITTER_API_SECRET }}
          TWITTER_ACCESS_TOKEN: ${{ secrets.TWITTER_ACCESS_TOKEN }}
          TWITTER_ACCESS_SECRET: ${{ secrets.TWITTER_ACCESS_SECRET }}
          ZENN_USERNAME: ${{ secrets.ZENN_USERNAME }}
        run: |
          python scripts/tweet_new_articles.py

      - name: Commit and push changes
        run: |
          git config --local user.email "action@github.com"
          git config --local user.name "GitHub Action"
          git add -A
          git diff --quiet && git diff --staged --quiet || (git commit -m "chore: scheduled publish" && git push)
```

**スケジュール:**
- 1日4回実行（JST 07:00, 12:00, 18:00, 21:00）
- `workflow_dispatch` でマニュアル実行も可能

## セットアップ手順

### 1. リポジトリにファイルを配置

```bash
# スクリプトディレクトリを作成
mkdir -p scripts

# スクリプトをコピー
cp scheduled_publish.py scripts/
cp tweet_new_articles.py scripts/

# 実行権限を付与
chmod +x scripts/*.py

# キューファイルを作成
touch publish-queue.txt
```

### 2. Twitter API認証情報を設定

GitHub リポジトリの Settings → Secrets → Actions で以下を追加：

```
TWITTER_API_KEY
TWITTER_API_SECRET
TWITTER_ACCESS_TOKEN
TWITTER_ACCESS_SECRET
ZENN_USERNAME
```

**取得方法:**
1. [Twitter Developer Portal](https://developer.twitter.com/) でアプリを作成
2. API Key と API Secret を取得
3. User authentication settings で Read and Write 権限を有効化
4. Access Token と Access Secret を生成

### 3. GitHub Actionsワークフローを配置

```bash
mkdir -p .github/workflows
cp scheduled-publish.yml .github/workflows/
```

### 4. 初回テスト

```bash
# マニュアル実行でテスト
# GitHub Actions画面で "Run workflow" をクリック

# または、ローカルでテスト
python scripts/scheduled_publish.py
python scripts/tweet_new_articles.py
```

## 運用フロー

### 新規記事の追加

```markdown
1. 記事を執筆（published: false）
2. publish-queue.txt に記事スラッグを追記
3. git push
```

```bash
# 例
echo "new-article-slug" >> publish-queue.txt
git add articles/new-article-slug.md publish-queue.txt
git commit -m "docs: add new article"
git push
```

### 自動公開の流れ

```
1. GitHub Actions が定期実行（1日4回）
2. キューから次の記事を取得
3. published: false → published: true に変更
4. Twitter に自動投稿
5. git commit & push
6. Zenn に自動反映
```

### キューの確認

```bash
# 現在のキュー状態を確認
cat publish-queue.txt

# 公開予定記事数を確認
wc -l publish-queue.txt
```

## トラブルシューティング

### 問題1: 403エラーが発生する

**原因:**
- `published_at` に未来の日時が指定されている

**解決策:**
```bash
# 全記事から published_at を削除
grep -l "published_at:" articles/*.md | xargs sed -i '/^published_at:/d'
```

### 問題2: Twitter連携が動かない

**チェック項目:**
1. Twitter API v2 を使用しているか（v1.1は2023年に廃止）
2. User authentication settings で Read and Write 権限があるか
3. GitHub Secrets が正しく設定されているか

**デバッグ:**
```bash
# ローカルで環境変数を設定してテスト
export TWITTER_API_KEY="..."
export TWITTER_API_SECRET="..."
export TWITTER_ACCESS_TOKEN="..."
export TWITTER_ACCESS_SECRET="..."
export ZENN_USERNAME="your_username"

python scripts/tweet_new_articles.py
```

### 問題3: 記事が公開されない

**確認項目:**
1. `publish-queue.txt` にスラッグが記載されているか
2. 記事ファイルが `articles/` に存在するか
3. GitHub Actions が正常に実行されているか（Actions タブで確認）

**手動実行:**
```bash
# ローカルで実行してエラーを確認
python scripts/scheduled_publish.py
```

## まとめ

Zennの自動投稿システムを構築する際のポイント：

1. **published_at の罠**: 未来日時指定は403エラーを引き起こす
2. **キュー式投稿**: GitHub Actionsで定期的に1記事ずつ公開
3. **Twitter連携**: tweepy + API v2で自動ツイート
4. **運用の簡素化**: キューに追加するだけで自動公開

**避けるべきこと:**
- `published_at` に未来の日時を指定
- `published: true` なのに記事が見えない状態

**推奨する構成:**
- キューファイルで投稿順を管理
- GitHub Actionsで定期実行（1日4回推奨）
- Twitter API v2で自動告知

この仕組みにより、記事を書き溜めてキューに追加するだけで、定期的に自動公開・自動ツイートが行われます。Zennでのブログ運用を完全自動化し、執筆に集中できる環境を構築しましょう。

## 参考資料

- [Zenn CLIガイド](https://zenn.dev/zenn/articles/zenn-cli-guide)
- [GitHub Actions ドキュメント](https://docs.github.com/ja/actions)
- [tweepy v4 Documentation](https://docs.tweepy.org/en/stable/)
- [Twitter API v2](https://developer.twitter.com/en/docs/twitter-api)
