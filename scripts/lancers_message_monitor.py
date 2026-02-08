#!/usr/bin/env python3
"""
Lancers Message Monitor - Check for new messages and notify via Discord

Monitors the Lancers inbox for unread messages and proposal status,
then sends Discord webhook notifications for any new activity.

Usage:
  python scripts/lancers_message_monitor.py --setup    # First-time login (opens browser)
  python scripts/lancers_message_monitor.py             # Check + notify (headless)
  python scripts/lancers_message_monitor.py --dry-run   # Check only, no Discord

Authentication:
  Uses Playwright persistent browser context.
  Run --setup first to log into Lancers (Google OAuth supported).
  Session is saved and reused automatically.

Environment:
  DISCORD_WEBHOOK_URL  - Discord Webhook URL (required, unless --dry-run)
"""

import io
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace"
    )
    sys.stderr = io.TextIOWrapper(
        sys.stderr.buffer, encoding="utf-8", errors="replace"
    )

import requests

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
STATE_FILE = REPO_ROOT / ".lancers-message-state.json"
AUTH_DIR = Path.home() / ".lancers-auth"

JST = timezone(timedelta(hours=9))
EMBED_COLOR = 0x00CC66

MYPAGE_URL = "https://www.lancers.jp/mypage"
MESSAGE_URL = "https://www.lancers.jp/message"
PROPOSAL_URL = "https://www.lancers.jp/mypage/proposals"
LOGIN_URL = "https://www.lancers.jp/user/login"

PAGE_TIMEOUT_MS = 30_000

# ---------------------------------------------------------------------------
# State Management
# ---------------------------------------------------------------------------


def load_state() -> dict:
    """Load seen message IDs from state file."""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"last_check": None, "seen_message_ids": [], "seen_proposal_ids": []}


def save_state(state: dict) -> None:
    """Save state, keeping last 500 seen IDs."""
    state["last_check"] = datetime.now(JST).isoformat()
    for key in ("seen_message_ids", "seen_proposal_ids"):
        if len(state.get(key, [])) > 500:
            state[key] = state[key][-500:]
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Playwright Auth
# ---------------------------------------------------------------------------


def setup_login() -> bool:
    """Open a visible browser for user to log into Lancers.

    Saves the session to AUTH_DIR for later headless use.
    Supports Google OAuth login flow.
    """
    from playwright.sync_api import sync_playwright

    AUTH_DIR.mkdir(parents=True, exist_ok=True)

    print("[Setup] ブラウザを起動します。Lancersにログインしてください。")
    print("[Setup] Google OAuthログインもサポートしています。")
    print("[Setup] ログイン完了後、ブラウザを閉じてください。\n")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(AUTH_DIR),
            channel="chrome",  # Use real Chrome (not Chromium) for Google OAuth
            headless=False,
            locale="ja-JP",
            viewport={"width": 1280, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )

        page = context.pages[0] if context.pages else context.new_page()
        page.goto(LOGIN_URL, timeout=PAGE_TIMEOUT_MS)

        # Poll until user reaches mypage or closes browser (no stdin needed)
        print("[Setup] ログイン待機中... (マイページ到達で自動完了、またはブラウザを閉じてください)")
        logged_in = False
        for _ in range(600):  # 10 min max
            time.sleep(1)
            try:
                if page.is_closed():
                    break
                current_url = page.url
                if "mypage" in current_url:
                    logged_in = True
                    print("[Setup] ログイン成功!")
                    time.sleep(2)  # Let cookies settle
                    break
            except Exception:
                break

        if not logged_in:
            print("[Setup] ログインが確認できませんでした。")
            print("[Setup] ブラウザでログイン後、再度 --setup を実行してください。")

        try:
            context.close()
        except Exception:
            pass

    print("[Setup] セッション保存完了")
    print(f"[Setup] 保存先: {AUTH_DIR}")
    return True


def is_logged_in(page) -> bool:
    """Check if the current page shows a logged-in state."""
    url = page.url
    if "login" in url:
        return False

    content = page.content()
    if "logout" in content.lower() or "マイページ" in content:
        return True

    return "login" not in url


# ---------------------------------------------------------------------------
# Message Checking (Playwright)
# ---------------------------------------------------------------------------


def check_messages_pw(page) -> list[dict]:
    """Check for messages using Playwright page."""
    messages = []

    try:
        print("[Messages] メッセージ一覧を取得中...", file=sys.stderr)
        page.goto(MESSAGE_URL, timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
        time.sleep(3)
        html = page.content()

        # Parse message threads from /message page
        # Lancers uses /mypage/message/?userId=X&workId=Y or /message/boardId patterns
        msg_patterns = [
            r'<a[^>]*href="(/mypage/message/?\?[^"]*(?:boardId|userId)=(\d+)[^"]*)"[^>]*>(.*?)</a>',
            r'<a[^>]*href="(/message[^"]*(?:boardId|userId)=(\d+)[^"]*)"[^>]*>(.*?)</a>',
        ]

        for pattern in msg_patterns:
            for m in re.finditer(pattern, html, re.DOTALL):
                path = m.group(1)
                msg_id = m.group(2)
                inner = re.sub(r"<[^>]+>", " ", m.group(3)).strip()
                inner = re.sub(r"\s+", " ", inner).strip()

                if not inner or len(inner) < 2:
                    continue

                url = f"https://www.lancers.jp{path}"
                messages.append(
                    {
                        "id": f"msg_{msg_id}",
                        "title": inner[:100],
                        "url": url,
                        "type": "message",
                    }
                )

        # Also check dashboard for message indicators
        if not messages:
            page.goto(MYPAGE_URL, timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
            time.sleep(2)
            dash_html = page.content()

            # Dashboard has message links like /mypage/message/?userId=X&workId=Y
            for m in re.finditer(
                r'<a[^>]*href="(/mypage/message/?\?[^"]*workId=(\d+)[^"]*)"[^>]*>(.*?)</a>',
                dash_html,
                re.DOTALL,
            ):
                path = m.group(1).replace("&amp;", "&")
                work_id = m.group(2)
                inner = re.sub(r"<[^>]+>", " ", m.group(3)).strip()
                inner = re.sub(r"\s+", " ", inner).strip()
                if not inner:
                    inner = f"Work #{work_id} message"

                url = f"https://www.lancers.jp{path}"
                messages.append(
                    {
                        "id": f"msg_w{work_id}",
                        "title": inner[:100],
                        "url": url,
                        "type": "message",
                    }
                )

        print(f"[Messages] 検出: {len(messages)}件", file=sys.stderr)

    except Exception as e:
        print(f"[Messages] エラー: {e}", file=sys.stderr)

    return messages


def check_proposals_pw(page) -> list[dict]:
    """Check for proposal status updates using Playwright page."""
    proposals = []

    try:
        print("[Proposals] 提案状況を確認中...", file=sys.stderr)
        page.goto(PROPOSAL_URL, timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
        time.sleep(3)
        html = page.content()

        # Lancers proposal list: <a class="c-link c-link--black" href="/work/detail/{id}">title</a>
        # Inside <li class="p-mypage-work__media c-media-job">
        for m in re.finditer(
            r'<a[^>]*href="/work/detail/(\d+)"[^>]*>\s*(.*?)\s*</a>',
            html,
            re.DOTALL,
        ):
            job_id = m.group(1)
            title = re.sub(r"<[^>]+>", " ", m.group(2)).strip()
            title = re.sub(r"\s+", " ", title).strip()

            if not title or len(title) < 5:
                continue

            url = f"https://www.lancers.jp/work/detail/{job_id}"

            # Check surrounding <li> block for status
            start = max(0, m.start() - 1000)
            end = min(len(html), m.end() + 2000)
            context = html[start:end]

            status = "pending"
            if re.search(r"c-media-job__status--active", context):
                # Active status - check the text
                status_match = re.search(
                    r'c-media-job__status--active[^>]*>.*?<span>(.*?)</span>',
                    context,
                    re.DOTALL,
                )
                if status_match:
                    status_text = status_match.group(1).strip()
                    status_text = re.sub(r"<[^>]+>", "", status_text).strip()
                    if status_text:
                        status = f"active:{status_text}"

            if re.search(r"選定|当選|採用|受注", context):
                status = "accepted"
            elif re.search(r"落選|不採用|辞退|キャンセル", context):
                status = "rejected"

            proposals.append(
                {
                    "id": f"prop_{job_id}",
                    "title": title[:100],
                    "url": url,
                    "type": "proposal",
                    "status": status,
                }
            )

        print(f"[Proposals] 検出: {len(proposals)}件", file=sys.stderr)

    except Exception as e:
        print(f"[Proposals] エラー: {e}", file=sys.stderr)

    return proposals


# ---------------------------------------------------------------------------
# Discord Notification
# ---------------------------------------------------------------------------


def notify_discord(items: list[dict]) -> None:
    """Send new messages/proposals to Discord."""
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("[Discord] DISCORD_WEBHOOK_URL が未設定", file=sys.stderr)
        return

    now = datetime.now(JST)
    lines = []

    for item in items[:15]:
        emoji = "\U0001f4ac" if item["type"] == "message" else "\U0001f4cb"
        status_text = ""
        if item.get("status") == "accepted":
            emoji = "\U0001f389"
            status_text = " **【受注！】**"
        elif item.get("status") == "rejected":
            emoji = "\u274c"
            status_text = " （落選）"

        title = item["title"][:80]
        lines.append(f"{emoji} [{title}]({item['url']}){status_text}")

    description = "\n".join(lines)

    payload = {
        "username": "\U0001f4e8 Lancers通知",
        "embeds": [
            {
                "title": f"Lancers新着通知 ({len(items)}件)",
                "description": description,
                "color": EMBED_COLOR,
                "footer": {
                    "text": f"Lancers Monitor | {now.strftime('%Y/%m/%d %H:%M')} JST",
                },
                "timestamp": now.isoformat(),
            }
        ],
    }

    try:
        resp = requests.post(webhook_url, json=payload, timeout=15)
        if resp.status_code == 204:
            print(f"[Discord] 投稿成功 ({len(items)}件)")
        else:
            print(
                f"[Discord] HTTP {resp.status_code}: {resp.text[:200]}",
                file=sys.stderr,
            )
    except Exception as e:
        print(f"[Discord] エラー: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    setup_mode = "--setup" in sys.argv
    dry_run = "--dry-run" in sys.argv

    if setup_mode:
        setup_login()
        return

    # Verify auth directory exists
    if not AUTH_DIR.exists():
        print("[Monitor] 初回セットアップが必要です。")
        print("[Monitor] 実行: python scripts/lancers_message_monitor.py --setup")
        sys.exit(1)

    from playwright.sync_api import sync_playwright

    print(f"[Monitor] 開始: {datetime.now(JST).strftime('%Y/%m/%d %H:%M')}")

    state = load_state()
    if state.get("last_check"):
        print(f"[Monitor] 前回チェック: {state['last_check']}")

    seen_msg_ids = set(state.get("seen_message_ids", []))
    seen_prop_ids = set(state.get("seen_proposal_ids", []))

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(AUTH_DIR),
            channel="chrome",
            headless=True,
            locale="ja-JP",
            args=["--disable-blink-features=AutomationControlled"],
        )

        page = context.pages[0] if context.pages else context.new_page()

        # Verify we're still logged in
        print("[Auth] セッション確認中...", file=sys.stderr)
        page.goto(MYPAGE_URL, timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
        time.sleep(2)

        if not is_logged_in(page):
            print("[Auth] セッション期限切れ。再ログインが必要です。", file=sys.stderr)
            print("[Auth] 実行: python scripts/lancers_message_monitor.py --setup")
            context.close()
            sys.exit(1)

        print("[Auth] 認証OK", file=sys.stderr)

        # Check messages
        messages = check_messages_pw(page)
        new_messages = [m for m in messages if m["id"] not in seen_msg_ids]

        time.sleep(1)

        # Check proposals
        proposals = check_proposals_pw(page)
        new_proposals = [p for p in proposals if p["id"] not in seen_prop_ids]

        context.close()

    # Combine new items
    new_items = new_messages + new_proposals

    print(f"\n[Monitor] メッセージ: {len(messages)}件 (新規: {len(new_messages)}件)")
    print(f"[Monitor] 提案: {len(proposals)}件 (新規: {len(new_proposals)}件)")

    if new_items:
        for item in new_items:
            emoji = "\U0001f4ac" if item["type"] == "message" else "\U0001f4cb"
            print(f"  {emoji} {item['title'][:60]}")
            print(f"    {item['url']}")

        if dry_run:
            print(f"\n[dry-run] Discord投稿スキップ ({len(new_items)}件)")
        else:
            notify_discord(new_items)
    else:
        print("\n新着通知なし")

    # Update seen IDs
    for m in messages:
        seen_msg_ids.add(m["id"])
    for p_item in proposals:
        seen_prop_ids.add(p_item["id"])

    state["seen_message_ids"] = list(seen_msg_ids)
    state["seen_proposal_ids"] = list(seen_prop_ids)
    save_state(state)

    print("[Monitor] 完了")


if __name__ == "__main__":
    main()
