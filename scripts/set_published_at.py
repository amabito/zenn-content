#!/usr/bin/env python3
"""
published_at一括設定スクリプト

published: true でpublished_at未設定の記事に対して、
過去日付を順次設定してタイムライン露出を増やす。
"""

import os
import re
from datetime import datetime, timedelta
from pathlib import Path

# 設定
ARTICLES_DIR = Path(__file__).parent.parent / "articles"
START_DATE = datetime(2026, 1, 1, 7, 0)  # 1月1日 7:00から開始
ARTICLES_PER_DAY = 4  # 1日あたり4記事
TIME_SLOTS = ["07:00", "12:00", "18:00", "21:00"]  # 公開時刻

def get_unpublished_at_articles():
    """published: true でpublished_at未設定の記事を取得"""
    articles = []

    for md_file in ARTICLES_DIR.glob("*.md"):
        content = md_file.read_text(encoding="utf-8")

        # published: true かつ published_at: がない記事
        if re.search(r'^published:\s*true', content, re.MULTILINE) and \
           not re.search(r'^published_at:', content, re.MULTILINE):
            articles.append(md_file)

    return sorted(articles)  # ファイル名順でソート

def add_published_at(file_path, published_at_str):
    """published_at行をfront matterに追加"""
    content = file_path.read_text(encoding="utf-8")

    # published: true の行を探して、その次の行に published_at を挿入
    pattern = r'(^published:\s*true)'
    replacement = f'\\1\npublished_at: "{published_at_str}"'

    new_content = re.sub(pattern, replacement, content, flags=re.MULTILINE)

    # バックアップ
    backup_path = file_path.with_suffix('.md.bak')
    file_path.rename(backup_path)

    # 新しい内容を書き込み
    file_path.write_text(new_content, encoding="utf-8")

    return backup_path

def main():
    articles = get_unpublished_at_articles()

    if not articles:
        print("[INFO] All articles already have published_at set.")
        return

    print(f"[INFO] Target articles: {len(articles)}")
    print(f"[INFO] Start date: {START_DATE.strftime('%Y-%m-%d')}")
    print(f"[INFO] Articles per day: {ARTICLES_PER_DAY}")
    print()

    # 日付を割り当て（自動実行）
    current_date = START_DATE
    time_slot_index = 0
    backups = []

    for i, article in enumerate(articles):
        # 時刻スロットを取得
        time_str = TIME_SLOTS[time_slot_index]
        published_at = f"{current_date.strftime('%Y-%m-%d')} {time_str}"

        # published_atを追加
        backup = add_published_at(article, published_at)
        backups.append(backup)

        print(f"[OK] {article.name}: {published_at}")

        # 次の時刻スロットへ
        time_slot_index += 1
        if time_slot_index >= len(TIME_SLOTS):
            time_slot_index = 0
            current_date += timedelta(days=1)

    print()
    print(f"[SUCCESS] Updated {len(articles)} articles")
    print(f"[BACKUP] Created {len(backups)} backup files (.md.bak)")
    print()
    print("[NEXT] To remove backups:")
    print(f"   cd {ARTICLES_DIR}")
    print("   del *.md.bak")

if __name__ == "__main__":
    main()
