#!/usr/bin/env python3
"""
Zenn記事を非公開にするスクリプト

使い方:
  python scripts/unpublish_articles.py [記事slug...]
  python scripts/unpublish_articles.py --all  # 全記事を非公開
  python scripts/unpublish_articles.py --list # 公開中の記事一覧

例:
  python scripts/unpublish_articles.py engineer-salary-1000man claude-code-productivity
"""

import os
import re
import sys
from pathlib import Path

ARTICLES_DIR = Path(__file__).parent.parent / "articles"

# レートリミットされた記事（デプロイ失敗した記事）
RATE_LIMITED_ARTICLES = [
    "3dgs-business-guide",
    "3dgs-image-preprocessing-paid",
    "3dgs-rasterizer-comparison",
    "claude-code-productivity-paid",
    "claude-code-productivity",
    "construction-3dgs",
    "construction-consultant-business-model",
    "construction-consultant-reality",
    "construction-consultant-reality-paid",
    "construction-consultant-salary",
    "construction-dx-failure",
    "construction-value-chain",
    "cuda-memory-management-paid",
    "cuda-memory-management",
    "cuda-optimization-basics",
    "cuda-warp-sync-trap-paid",
    "cuda-warp-sync-trap",
    "drone-survey-guide",
    "engineer-salary-1000man-paid",
    "engineer-salary-1000man",
    "gpu-programming-intro",
    "gpu-programming-paid",
    "iconstruction-2-reality",
    "legacy-industry-dx-paid",
    "legacy-industry-dx",
    "nerf-now-2026",
    "nerf-vs-3dgs-2026",
    "pytorch-cuda-extension-paid",
    "pytorch-cuda-extension",
    "realestate-3dgs",
    "rtx5090-cuda-optimization-paid",
    "rtx5090-cuda-optimization",
    "small-construction-survival",
    "tech-career-2026",
]


def get_published_articles():
    """published: true の記事を取得"""
    published = []

    for md_file in ARTICLES_DIR.glob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
        if not match:
            continue

        frontmatter = match.group(1)
        if re.search(r'^published:\s*true\s*$', frontmatter, re.MULTILINE):
            published.append(md_file.stem)

    return published


def unpublish_article(slug: str):
    """記事を非公開にする"""
    md_file = ARTICLES_DIR / f"{slug}.md"

    if not md_file.exists():
        print(f"  [ERROR] {slug} (file not found)")
        return False

    content = md_file.read_text(encoding="utf-8")

    # published: true → published: false
    new_content = re.sub(
        r'^(published:\s*)true(\s*)$',
        r'\1false\2',
        content,
        flags=re.MULTILINE
    )

    if content == new_content:
        print(f"  [SKIP] {slug} (already unpublished)")
        return False

    md_file.write_text(new_content, encoding="utf-8")
    print(f"  [OK] {slug}")
    return True


def main():
    if len(sys.argv) < 2:
        print("使い方:")
        print("  python scripts/unpublish_articles.py --rate-limited  # レートリミット記事を非公開")
        print("  python scripts/unpublish_articles.py --list          # 公開中の記事一覧")
        print("  python scripts/unpublish_articles.py slug1 slug2 ... # 指定記事を非公開")
        return

    if sys.argv[1] == "--list":
        published = get_published_articles()
        print(f"公開中の記事: {len(published)}件")
        for slug in sorted(published):
            print(f"  - {slug}")
        return

    if sys.argv[1] == "--rate-limited":
        slugs = RATE_LIMITED_ARTICLES
        print(f"レートリミットされた記事を非公開にします: {len(slugs)}件")
    else:
        slugs = sys.argv[1:]
        print(f"指定された記事を非公開にします: {len(slugs)}件")

    print()
    count = 0
    for slug in slugs:
        if unpublish_article(slug):
            count += 1

    print(f"\n{count}件を非公開にしました")


if __name__ == "__main__":
    main()
