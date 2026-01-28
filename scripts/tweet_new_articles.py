#!/usr/bin/env python3
"""
Zenn記事の自動ツイートスクリプト

新しく公開された記事を検出し、Twitter/Xに自動投稿する。
.tweeted-articles で既にツイート済みの記事を管理。

使い方:
  python scripts/tweet_new_articles.py          # 通常実行
  python scripts/tweet_new_articles.py --dry-run # ツイートせずに確認のみ

環境変数:
  TWITTER_API_KEY, TWITTER_API_SECRET,
  TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET
"""

import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
ARTICLES_DIR = REPO_ROOT / "articles"
TWEETED_FILE = REPO_ROOT / ".tweeted-articles"
ZENN_BASE_URL = "https://zenn.dev/amabito/articles"
MAX_TWEET_LENGTH = 280


def parse_frontmatter(content: str) -> dict:
    """frontmatterからtitle, published, topicsを抽出"""
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}

    fm = match.group(1)
    result = {}

    title_match = re.search(r'^title:\s*["\']?(.*?)["\']?\s*$', fm, re.MULTILINE)
    if title_match:
        result["title"] = title_match.group(1)

    published_match = re.search(r"^published:\s*(true|false)\s*$", fm, re.MULTILINE)
    if published_match:
        result["published"] = published_match.group(1) == "true"

    topics_match = re.search(r"^topics:\s*\[(.*?)\]", fm, re.MULTILINE)
    if topics_match:
        raw = topics_match.group(1)
        result["topics"] = [
            t.strip().strip("\"'") for t in raw.split(",") if t.strip()
        ]

    return result


def get_published_articles() -> dict:
    """published: true の全記事を {slug: {title, topics}} で返す"""
    articles = {}
    for md_file in ARTICLES_DIR.glob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        meta = parse_frontmatter(content)
        if meta.get("published"):
            slug = md_file.stem
            articles[slug] = {
                "title": meta.get("title", slug),
                "topics": meta.get("topics", []),
            }
    return articles


def load_tweeted_slugs() -> set:
    """ツイート済みスラッグを読み込む"""
    if not TWEETED_FILE.exists():
        return set()
    lines = TWEETED_FILE.read_text(encoding="utf-8").strip().splitlines()
    return {line.strip() for line in lines if line.strip()}


def save_tweeted_slugs(slugs: set):
    """ツイート済みスラッグを保存"""
    sorted_slugs = sorted(slugs)
    TWEETED_FILE.write_text("\n".join(sorted_slugs) + "\n", encoding="utf-8")


def compose_tweet(slug: str, title: str, topics: list) -> str:
    """ツイート本文を組み立てる"""
    url = f"{ZENN_BASE_URL}/{slug}"
    hashtags = " ".join(f"#{t}" for t in topics[:3]) if topics else ""

    tweet = f"\U0001f4dd {title}\n\n{url}"
    if hashtags:
        candidate = f"{tweet}\n\n{hashtags}"
        if len(candidate) <= MAX_TWEET_LENGTH:
            tweet = candidate

    if len(tweet) > MAX_TWEET_LENGTH:
        truncated_title = title[: MAX_TWEET_LENGTH - len(url) - 10] + "..."
        tweet = f"\U0001f4dd {truncated_title}\n\n{url}"

    return tweet


def post_tweet(text: str) -> bool:
    """Twitter API v2でツイートを投稿"""
    try:
        import tweepy
    except ImportError:
        print("ERROR: tweepy がインストールされていません")
        print("  pip install tweepy")
        return False

    api_key = os.environ.get("TWITTER_API_KEY")
    api_secret = os.environ.get("TWITTER_API_SECRET")
    access_token = os.environ.get("TWITTER_ACCESS_TOKEN")
    access_token_secret = os.environ.get("TWITTER_ACCESS_TOKEN_SECRET")

    if not all([api_key, api_secret, access_token, access_token_secret]):
        print("ERROR: Twitter API credentials not set")
        return False

    client = tweepy.Client(
        consumer_key=api_key,
        consumer_secret=api_secret,
        access_token=access_token,
        access_token_secret=access_token_secret,
    )

    try:
        response = client.create_tweet(text=text)
        tweet_id = response.data["id"]
        print(f"  -> https://twitter.com/i/status/{tweet_id}")
        return True
    except tweepy.errors.Unauthorized as e:
        print(f"  ERROR 401: {e}")
        print(f"  API Key starts with: {api_key[:6]}...")
        print(f"  Access Token starts with: {access_token[:6]}...")
        print("  -> Consumer KeyとAccess Tokenを全て再生成してください")
        return False
    except tweepy.errors.Forbidden as e:
        print(f"  ERROR 403: {e}")
        print("  -> アプリの権限が「読み取りと書き込み」になっているか確認")
        return False
    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {e}")
        return False


def main():
    dry_run = "--dry-run" in sys.argv

    published = get_published_articles()
    tweeted = load_tweeted_slugs()
    new_slugs = set(published.keys()) - tweeted

    if not new_slugs:
        print("新しいツイート対象の記事はありません")
        return

    print(f"新規ツイート対象: {len(new_slugs)}件")
    if dry_run:
        print("(dry-run モード: ツイートしません)\n")

    success_count = 0
    for slug in sorted(new_slugs):
        info = published[slug]
        tweet_text = compose_tweet(slug, info["title"], info["topics"])

        print(f"\n[{slug}]")
        print(f"  {tweet_text}")

        if dry_run:
            tweeted.add(slug)
            success_count += 1
        else:
            if post_tweet(tweet_text):
                tweeted.add(slug)
                success_count += 1
            else:
                print(f"  FAILED: {slug}")

    save_tweeted_slugs(tweeted)
    print(f"\n完了: {success_count}/{len(new_slugs)}件 ツイート済み")


if __name__ == "__main__":
    main()
