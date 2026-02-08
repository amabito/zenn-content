#!/usr/bin/env python3
"""
Auto Proposer - Lancersへの提案を自動送信

使い方:
  python scripts/auto_proposer.py                    # 保留中の提案を全て送信
  python scripts/auto_proposer.py --job la_12345     # 特定の案件のみ
  python scripts/auto_proposer.py --dry-run           # ブラウザ操作するが送信しない

環境変数:
  LANCERS_EMAIL    - Lancersログインメールアドレス
  LANCERS_PASSWORD - Lancersログインパスワード
"""

import asyncio
import io
import json
import os
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
PIPELINE_STATE = REPO_ROOT / ".freelance-pipeline-state.json"


def load_pipeline_state() -> dict:
    if PIPELINE_STATE.exists():
        return json.loads(PIPELINE_STATE.read_text(encoding="utf-8"))
    return {"jobs": {}}


def save_pipeline_state(state: dict):
    PIPELINE_STATE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8"
    )


async def login_lancers(page, email: str, password: str) -> bool:
    """Lancersにログイン"""
    try:
        await page.goto("https://www.lancers.jp/user/login", timeout=30000)
        await page.wait_for_load_state("networkidle")

        # Find email and password fields
        # Lancers login form selectors (may need adjustment)
        email_selector = 'input[name="data[User][email]"], input[type="email"], #UserEmail'
        password_selector = 'input[name="data[User][password]"], input[type="password"], #UserPassword'

        await page.fill(email_selector, email)
        await page.fill(password_selector, password)

        # Click login button
        submit_selector = 'button[type="submit"], input[type="submit"], .login-btn'
        await page.click(submit_selector)

        await page.wait_for_load_state("networkidle")

        # Check if login succeeded (URL should change from /user/login)
        if "/user/login" not in page.url:
            print("[Login] 成功")
            return True
        else:
            print("[Login] 失敗 - URLが変わらない", file=sys.stderr)
            return False

    except Exception as e:
        print(f"[Login] エラー: {e}", file=sys.stderr)
        return False


async def submit_proposal(page, job_url: str, proposal_text: str, price: int, dry_run: bool = False) -> bool:
    """Lancersの案件ページで提案を送信"""
    try:
        await page.goto(job_url, timeout=30000)
        await page.wait_for_load_state("networkidle")

        # Click "提案する" button
        propose_button = page.locator('a:has-text("提案する"), button:has-text("提案する"), .propose-btn')
        if await propose_button.count() == 0:
            print(f"  [Propose] 提案ボタンが見つかりません: {job_url}", file=sys.stderr)
            return False

        await propose_button.first.click()
        await page.wait_for_load_state("networkidle")

        # Fill proposal form
        # Look for textarea for proposal text
        textarea = page.locator('textarea[name*="message"], textarea[name*="proposal"], textarea.proposal-textarea')
        if await textarea.count() > 0:
            await textarea.first.fill(proposal_text)

        # Fill price
        price_input = page.locator('input[name*="price"], input[name*="amount"], input.price-input')
        if await price_input.count() > 0:
            await price_input.first.fill(str(price))

        if dry_run:
            print(f"  [Propose] DRY RUN - 送信スキップ")
            # Take screenshot for verification
            screenshot_path = REPO_ROOT / f".screenshots/proposal_{int(time.time())}.png"
            screenshot_path.parent.mkdir(exist_ok=True)
            await page.screenshot(path=str(screenshot_path))
            print(f"  [Propose] スクリーンショット: {screenshot_path}")
            return True

        # Submit
        submit_button = page.locator('button[type="submit"]:has-text("送信"), button:has-text("提案を送信")')
        if await submit_button.count() > 0:
            await submit_button.first.click()
            await page.wait_for_load_state("networkidle")
            print(f"  [Propose] 送信完了")
            return True
        else:
            print(f"  [Propose] 送信ボタンが見つかりません", file=sys.stderr)
            return False

    except Exception as e:
        print(f"  [Propose] エラー: {e}", file=sys.stderr)
        return False


async def main():
    dry_run = "--dry-run" in sys.argv
    target_job = None
    for i, arg in enumerate(sys.argv):
        if arg == "--job" and i + 1 < len(sys.argv):
            target_job = sys.argv[i + 1]

    email = os.environ.get("LANCERS_EMAIL")
    password = os.environ.get("LANCERS_PASSWORD")

    if not email or not password:
        print("[Error] LANCERS_EMAIL と LANCERS_PASSWORD を .env.local に設定してください")
        sys.exit(1)

    state = load_pipeline_state()
    jobs = state.get("jobs", {})

    # Find jobs ready to propose
    pending = []
    for job_id, job in jobs.items():
        if job.get("status") == "proposed" and job.get("proposal_text"):
            if target_job and job_id != target_job:
                continue
            pending.append(job)

    if not pending:
        print("提案待ちの案件がありません")
        return

    print(f"提案送信: {len(pending)}件")

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("[Error] playwright がインストールされていません")
        print("  pip install playwright && python -m playwright install chromium")
        sys.exit(1)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not dry_run)  # Show browser in dry-run
        context = await browser.new_context()
        page = await context.new_page()

        # Login
        if not await login_lancers(page, email, password):
            print("[Error] ログイン失敗。認証情報を確認してください。")
            await browser.close()
            return

        # Submit proposals
        for job in pending:
            print(f"\n[{job['id']}] {job['title'][:60]}")

            success = await submit_proposal(
                page,
                job["url"],
                job["proposal_text"],
                job.get("suggested_price", 30000),
                dry_run=dry_run
            )

            if success and not dry_run:
                from datetime import datetime, timezone, timedelta
                JST = timezone(timedelta(hours=9))
                job["status"] = "submitted"
                job["proposed_at"] = datetime.now(JST).isoformat()

            await asyncio.sleep(5)  # Wait between proposals

        await browser.close()

    save_pipeline_state(state)
    print("\n完了")


if __name__ == "__main__":
    asyncio.run(main())
