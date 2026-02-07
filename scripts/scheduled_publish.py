#!/usr/bin/env python3
"""
Scheduled article publisher for Zenn.

Publishes the next article from the publish queue file.
Designed to be called by GitHub Actions cron (4x/day).

Queue file format (publish-queue.txt):
  One slug per line, published in order (top = next).
  Lines starting with # are comments.
  Empty lines are ignored.
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
ARTICLES_DIR = REPO_ROOT / "articles"
QUEUE_FILE = REPO_ROOT / "publish-queue.txt"


def load_queue() -> list[str]:
    """Load publish queue, return list of slugs."""
    if not QUEUE_FILE.exists():
        return []
    lines = QUEUE_FILE.read_text(encoding="utf-8").strip().splitlines()
    return [
        line.strip()
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    ]


def save_queue(slugs: list[str]):
    """Save remaining queue back to file."""
    header = "# Zenn publish queue - one slug per line, top = next\n"
    content = header + "\n".join(slugs) + "\n" if slugs else header
    QUEUE_FILE.write_text(content, encoding="utf-8")


def publish_article(slug: str) -> bool:
    """Set published: false -> true for a given slug."""
    md_file = ARTICLES_DIR / f"{slug}.md"
    if not md_file.exists():
        print(f"  WARN: {slug}.md not found, skipping")
        return False

    content = md_file.read_text(encoding="utf-8")

    if not re.search(r"^published:\s*false", content, re.MULTILINE):
        print(f"  SKIP: {slug} is already published")
        return False

    new_content = re.sub(
        r"^(published:\s*)false",
        r"\1true",
        content,
        flags=re.MULTILINE,
    )
    md_file.write_text(new_content, encoding="utf-8")
    print(f"  PUBLISHED: {slug}")
    return True


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 1

    queue = load_queue()
    if not queue:
        print("Queue is empty. No articles to publish.")
        return

    print(f"Queue: {len(queue)} articles remaining")
    print(f"Publishing: {min(count, len(queue))} article(s)\n")

    published = 0
    while published < count and queue:
        slug = queue.pop(0)
        if publish_article(slug):
            published += 1
        # If skipped (already published or not found), still remove from queue

    save_queue(queue)

    print(f"\nDone: {published} article(s) published")
    if queue:
        print(f"Next in queue: {queue[0]}")
        print(f"Remaining: {len(queue)}")


if __name__ == "__main__":
    main()
