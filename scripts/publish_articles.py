#!/usr/bin/env python3
"""
Zenn記事の段階的公開スクリプト

使い方:
  python scripts/publish_articles.py [公開数]

例:
  python scripts/publish_articles.py 5  # 5件公開
  python scripts/publish_articles.py    # デフォルト5件公開
"""

import os
import re
import sys
from pathlib import Path

ARTICLES_DIR = Path(__file__).parent.parent / "articles"


def get_unpublished_articles():
    """published: false の記事を取得"""
    unpublished = []

    for md_file in ARTICLES_DIR.glob("*.md"):
        content = md_file.read_text(encoding="utf-8")

        # frontmatterを解析
        match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
        if not match:
            continue

        frontmatter = match.group(1)

        # published: false を探す
        if re.search(r'^published:\s*false\s*$', frontmatter, re.MULTILINE):
            unpublished.append(md_file)

    return unpublished


def publish_article(md_file: Path):
    """記事を公開状態にする"""
    content = md_file.read_text(encoding="utf-8")

    # published: false → published: true
    new_content = re.sub(
        r'^(published:\s*)false(\s*)$',
        r'\1true\2',
        content,
        flags=re.MULTILINE
    )

    md_file.write_text(new_content, encoding="utf-8")
    print(f"  [OK] {md_file.name}")


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 5

    unpublished = get_unpublished_articles()

    if not unpublished:
        print("公開待ちの記事はありません")
        return

    print(f"公開待ち: {len(unpublished)}件")
    print(f"今回公開: {min(count, len(unpublished))}件")
    print()

    for md_file in unpublished[:count]:
        publish_article(md_file)

    remaining = len(unpublished) - count
    if remaining > 0:
        print(f"\n残り: {remaining}件（明日以降に公開）")


if __name__ == "__main__":
    main()
