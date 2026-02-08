#!/usr/bin/env python3
"""
Lancers Message Monitor - Check for new messages and notify via Discord

Monitors the Lancers inbox for unread messages and sends
Discord webhook notifications for any new ones.

Usage:
  python scripts/lancers_message_monitor.py           # Check + notify
  python scripts/lancers_message_monitor.py --dry-run  # Check only, no Discord

Environment:
  LANCERS_EMAIL        - Lancers login email (required)
  LANCERS_PASSWORD     - Lancers login password (required)
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
from typing import Optional

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

JST = timezone(timedelta(hours=9))
EMBED_COLOR = 0x00CC66

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

LOGIN_URL = "https://www.lancers.jp/user/login"
MYPAGE_URL = "https://www.lancers.jp/mypage"
MESSAGE_URL = "https://www.lancers.jp/mypage/message"
PROPOSAL_URL = "https://www.lancers.jp/mypage/proposal"

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
# Lancers Session
# ---------------------------------------------------------------------------


def create_lancers_session(email: str, password: str) -> Optional[requests.Session]:
    """Login to Lancers and return an authenticated session."""
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    try:
        # Step 1: GET login page to obtain CSRF token
        print("[Login] ログインページを取得中...", file=sys.stderr)
        resp = session.get(LOGIN_URL, timeout=15)
        resp.raise_for_status()
        resp.encoding = "utf-8"

        # Extract CSRF token (_token or authenticity_token)
        token = None
        token_patterns = [
            r'name="_token"\s+value="([^"]+)"',
            r'name="authenticity_token"\s+value="([^"]+)"',
            r'"_token"\s*:\s*"([^"]+)"',
            r'name="csrf[_-]token"\s+content="([^"]+)"',
            r'<meta\s+name="csrf-token"\s+content="([^"]+)"',
        ]
        for pattern in token_patterns:
            match = re.search(pattern, resp.text, re.IGNORECASE)
            if match:
                token = match.group(1)
                break

        # Step 2: POST login credentials
        print("[Login] ログイン中...", file=sys.stderr)
        login_data = {
            "email": email,
            "password": password,
        }
        if token:
            login_data["_token"] = token

        resp = session.post(
            LOGIN_URL,
            data=login_data,
            timeout=15,
            allow_redirects=True,
        )

        # Check if login succeeded by looking for mypage redirect or user menu
        if "logout" in resp.text.lower() or "mypage" in resp.url:
            print("[Login] ログイン成功", file=sys.stderr)
            return session

        # Check for error messages
        if "メールアドレスまたはパスワードが正しくありません" in resp.text:
            print("[Login] エラー: メールアドレスまたはパスワードが正しくありません", file=sys.stderr)
            return None

        # Try accessing mypage to verify
        resp = session.get(MYPAGE_URL, timeout=15, allow_redirects=True)
        if "login" in resp.url:
            print("[Login] エラー: ログインに失敗しました（リダイレクト）", file=sys.stderr)
            return None

        print("[Login] ログイン成功（マイページ確認）", file=sys.stderr)
        return session

    except Exception as e:
        print(f"[Login] 例外: {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Message Checking
# ---------------------------------------------------------------------------


def check_messages(session: requests.Session) -> list[dict]:
    """Check for unread messages in the inbox."""
    messages = []

    try:
        print("[Messages] メッセージ一覧を取得中...", file=sys.stderr)
        resp = session.get(MESSAGE_URL, timeout=15)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        html = resp.text

        # Parse message list items
        # Look for message board entries with unread indicators
        msg_patterns = [
            # Message board links with IDs
            r'<a[^>]*href="(/mypage/message\?boardId=(\d+))"[^>]*>(.*?)</a>',
            r'<a[^>]*href="(/message/(\d+))"[^>]*>(.*?)</a>',
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
                messages.append({
                    "id": f"msg_{msg_id}",
                    "title": inner[:100],
                    "url": url,
                    "type": "message",
                })

        # Also check for unread badge count
        unread_match = re.search(
            r'(?:未読|unread)[^<]*?(\d+)',
            html,
            re.IGNORECASE,
        )
        if unread_match:
            count = int(unread_match.group(1))
            print(f"[Messages] 未読メッセージ: {count}件", file=sys.stderr)

    except Exception as e:
        print(f"[Messages] エラー: {e}", file=sys.stderr)

    return messages


def check_proposals(session: requests.Session) -> list[dict]:
    """Check for proposal status updates (accepted, rejected, etc.)."""
    proposals = []

    try:
        print("[Proposals] 提案状況を確認中...", file=sys.stderr)
        resp = session.get(PROPOSAL_URL, timeout=15)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        html = resp.text

        # Look for proposal entries with status changes
        proposal_patterns = [
            r'<a[^>]*href="(/work/detail/(\d+)[^"]*)"[^>]*>(.*?)</a>',
        ]

        for pattern in proposal_patterns:
            for m in re.finditer(pattern, html, re.DOTALL):
                path = m.group(1)
                job_id = m.group(2)
                inner = re.sub(r"<[^>]+>", " ", m.group(3)).strip()
                inner = re.sub(r"\s+", " ", inner).strip()

                if not inner or len(inner) < 5:
                    continue

                url = f"https://www.lancers.jp{path}"

                # Check surrounding context for status indicators
                start = max(0, m.start() - 300)
                end = min(len(html), m.end() + 300)
                context = html[start:end]

                status = "unknown"
                if re.search(r"選定|当選|採用|受注", context):
                    status = "accepted"
                elif re.search(r"落選|不採用|辞退", context):
                    status = "rejected"
                elif re.search(r"提案中|検討中", context):
                    status = "pending"

                proposals.append({
                    "id": f"prop_{job_id}",
                    "title": inner[:100],
                    "url": url,
                    "type": "proposal",
                    "status": status,
                })

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
        emoji = "💬" if item["type"] == "message" else "📋"
        status_text = ""
        if item.get("status") == "accepted":
            emoji = "🎉"
            status_text = " **【受注！】**"
        elif item.get("status") == "rejected":
            emoji = "❌"
            status_text = " （落選）"

        title = item["title"][:80]
        lines.append(f"{emoji} [{title}]({item['url']}){status_text}")

    description = "\n".join(lines)

    payload = {
        "username": "📨 Lancers通知",
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
    dry_run = "--dry-run" in sys.argv

    email = os.environ.get("LANCERS_EMAIL")
    password = os.environ.get("LANCERS_PASSWORD")

    if not email or not password:
        print(
            "エラー: LANCERS_EMAIL と LANCERS_PASSWORD を環境変数に設定してください",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"[Monitor] 開始: {datetime.now(JST).strftime('%Y/%m/%d %H:%M')}")

    state = load_state()
    if state.get("last_check"):
        print(f"[Monitor] 前回チェック: {state['last_check']}")

    seen_msg_ids = set(state.get("seen_message_ids", []))
    seen_prop_ids = set(state.get("seen_proposal_ids", []))

    # Login
    session = create_lancers_session(email, password)
    if not session:
        print("[Monitor] ログイン失敗、終了", file=sys.stderr)
        sys.exit(1)

    time.sleep(1)

    # Check messages
    messages = check_messages(session)
    new_messages = [m for m in messages if m["id"] not in seen_msg_ids]

    time.sleep(1)

    # Check proposals
    proposals = check_proposals(session)
    new_proposals = [p for p in proposals if p["id"] not in seen_prop_ids]

    # Combine new items
    new_items = new_messages + new_proposals

    print(f"\n[Monitor] メッセージ: {len(messages)}件 (新規: {len(new_messages)}件)")
    print(f"[Monitor] 提案: {len(proposals)}件 (新規: {len(new_proposals)}件)")

    if new_items:
        for item in new_items:
            emoji = "💬" if item["type"] == "message" else "📋"
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
    for p in proposals:
        seen_prop_ids.add(p["id"])

    state["seen_message_ids"] = list(seen_msg_ids)
    state["seen_proposal_ids"] = list(seen_prop_ids)
    save_state(state)

    print("[Monitor] 完了")


if __name__ == "__main__":
    main()
