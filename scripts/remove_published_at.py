#!/usr/bin/env python3
"""
published_at一括削除スクリプト

published_at行を削除して再設定可能にする
"""

import re
from pathlib import Path

ARTICLES_DIR = Path(__file__).parent.parent / "articles"

def remove_published_at(file_path):
    """published_at行を削除"""
    content = file_path.read_text(encoding="utf-8")

    # published_at: "..." の行を削除
    new_content = re.sub(r'^published_at:.*\n', '', content, flags=re.MULTILINE)

    if new_content != content:
        file_path.write_text(new_content, encoding="utf-8")
        return True
    return False

def main():
    count = 0
    for md_file in ARTICLES_DIR.glob("*.md"):
        if remove_published_at(md_file):
            print(f"[REMOVED] {md_file.name}")
            count += 1

    print()
    print(f"[SUCCESS] Removed published_at from {count} files")

if __name__ == "__main__":
    main()
