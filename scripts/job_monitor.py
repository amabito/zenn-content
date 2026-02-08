#!/usr/bin/env python3
"""
Freelance Job Monitor - Lancersから関連案件を検出しDiscordに通知

監視対象:
  - Lancers (ランサーズ) - サーバーサイドレンダリングで安定取得可能

検索キーワード:
  Python, CUDA, GPU, AI, 3D, Bot, Discord, API, スクレイピング,
  データ分析, 自動化, LLM, ChatGPT, Web開発

フィルタ:
  - 重複検出: .job-monitor-state.json で既読管理

使い方:
  python scripts/job_monitor.py           # 監視 + Discord通知
  python scripts/job_monitor.py --dry-run  # Discord通知しない

環境変数:
  DISCORD_WEBHOOK_URL  - Discord Webhook URL（必須、--dry-run時は不要）
"""

import io
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import requests

SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
STATE_FILE = REPO_ROOT / ".job-monitor-state.json"
JST = timezone(timedelta(hours=9))

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

SEARCH_QUERIES = [
    "Python",
    "CUDA GPU",
    "AI 自動化",
    "Discord Bot",
    "スクレイピング",
    "3D モデル",
    "LLM ChatGPT",
    "データ分析 Python",
]

REQUEST_DELAY = 3.0
EMBED_COLOR = 0xFF6600


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"last_run": None, "seen_jobs": []}


def save_state(state: dict):
    state["last_run"] = datetime.now(JST).isoformat()
    if len(state.get("seen_jobs", [])) > 1000:
        state["seen_jobs"] = state["seen_jobs"][-1000:]
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def fetch_lancers(seen_set: set) -> list[dict]:
    """Lancersの案件を検索"""
    jobs = []

    for query in SEARCH_QUERIES:
        try:
            search_url = (
                f"https://www.lancers.jp/work/search/system"
                f"?keyword={quote(query)}&sort=started&open=1"
            )
            print(f"  [Lancers] 検索: {query}...", file=sys.stderr)

            resp = requests.get(
                search_url, timeout=15, headers={"User-Agent": USER_AGENT}
            )
            resp.raise_for_status()
            resp.encoding = "utf-8"
            html = resp.text

            # Split HTML into job card blocks to check each card's context
            for m in re.finditer(
                r'<a\s[^>]*href="(/work/detail/(\d+))"[^>]*>(.*?)</a>',
                html,
                re.DOTALL,
            ):
                path = m.group(1)
                job_num = m.group(2)
                inner = re.sub(r"<[^>]+>", " ", m.group(3)).strip()
                inner = re.sub(r"\s+", " ", inner).strip()

                if len(inner) < 8:
                    continue

                job_id = f"la_{job_num}"
                if job_id in seen_set:
                    continue

                # Check surrounding context for closed indicators
                start = max(0, m.start() - 500)
                end = min(len(html), m.end() + 500)
                context = html[start:end]
                if re.search(
                    r"募集終了|終了しました|受付終了|キャンセル",
                    context,
                ):
                    continue

                job_url = f"https://www.lancers.jp{path}"

                jobs.append({
                    "id": job_id,
                    "title": inner,
                    "url": job_url,
                    "query": query,
                })
                seen_set.add(job_id)

            time.sleep(REQUEST_DELAY)

        except Exception as e:
            print(f"  [Lancers] エラー ({query}): {e}", file=sys.stderr)

    # Deduplicate by job number
    seen_nums = set()
    unique_jobs = []
    for job in jobs:
        num = job["id"]
        if num not in seen_nums:
            seen_nums.add(num)
            unique_jobs.append(job)

    return unique_jobs


def build_discord_payload(jobs: list[dict]) -> dict:
    """Discord Webhook用ペイロードを構築"""
    lines = []
    for job in jobs[:20]:
        title = job["title"][:80]
        lines.append(f"• [{title}]({job['url']})")

    description = "\n".join(lines)
    if len(jobs) > 20:
        description += f"\n\n...他 {len(jobs) - 20}件"

    now = datetime.now(JST)
    next_check = now + timedelta(hours=3)

    return {
        "username": "💼 案件アラート",
        "embeds": [
            {
                "title": f"新着フリーランス案件 ({len(jobs)}件)",
                "description": description,
                "color": EMBED_COLOR,
                "footer": {
                    "text": (
                        f"Lancers | "
                        f"次回チェック: {next_check.strftime('%H:%M')} JST"
                    )
                },
                "timestamp": now.isoformat(),
            }
        ],
    }


def post_to_discord(jobs: list[dict]):
    """Discord Webhookに投稿"""
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("[Discord] DISCORD_WEBHOOK_URL が未設定", file=sys.stderr)
        return

    payload = build_discord_payload(jobs)

    try:
        resp = requests.post(webhook_url, json=payload, timeout=15)
        if resp.status_code == 204:
            print(f"[Discord] 投稿成功 ({len(jobs)}件)")
        else:
            print(
                f"[Discord] HTTP {resp.status_code}: {resp.text[:200]}",
                file=sys.stderr,
            )
    except Exception as e:
        print(f"[Discord] エラー: {e}", file=sys.stderr)


def main():
    dry_run = "--dry-run" in sys.argv

    print(f"[Job Monitor] 開始: {datetime.now(JST).strftime('%Y/%m/%d %H:%M')}")

    state = load_state()
    if state.get("last_run"):
        print(f"[Job Monitor] 前回: {state['last_run']}")

    seen_set = set(state.get("seen_jobs", []))
    initial_count = len(seen_set)

    print("[Lancers] 案件検索中...")
    jobs = fetch_lancers(seen_set)

    print(f"\n新規案件: {len(jobs)}件 (既知: {initial_count}件)")

    if not jobs:
        print("新着案件なし")
        save_state(state)
        return

    for job in jobs:
        print(f"  • {job['title'][:70]}")
        print(f"    {job['url']}")

    if dry_run:
        print(f"\n[dry-run] Discord投稿スキップ ({len(jobs)}件)")
    else:
        post_to_discord(jobs)

    state["seen_jobs"] = list(seen_set)
    save_state(state)
    print("\n[Job Monitor] 完了")


if __name__ == "__main__":
    main()
