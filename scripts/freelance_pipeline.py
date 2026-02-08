#!/usr/bin/env python3
"""
Freelance Automation Pipeline - Lancers job evaluation, proposal generation, and project build

Pipeline stages:
  found -> evaluated -> proposed -> accepted -> building -> delivered
  found -> skipped (score < threshold)

Commands:
  python scripts/freelance_pipeline.py scan          # Evaluate new jobs + generate proposals
  python scripts/freelance_pipeline.py propose        # List proposal-ready jobs
  python scripts/freelance_pipeline.py build JOB_ID   # Auto-build project for accepted job
  python scripts/freelance_pipeline.py status         # Show pipeline status
  python scripts/freelance_pipeline.py accept JOB_ID  # Mark job as accepted

Environment:
  DISCORD_WEBHOOK_URL  - Discord Webhook URL (required)

Dependencies:
  - requests
  - Claude CLI (claude) in PATH
"""

import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

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
PIPELINE_STATE_FILE = REPO_ROOT / ".freelance-pipeline-state.json"
JOB_MONITOR_STATE_FILE = REPO_ROOT / ".job-monitor-state.json"
FREELANCE_WORKSPACE_ROOT = Path("D:/work/freelance")

JST = timezone(timedelta(hours=9))
REQUEST_DELAY = 3.0
SCORE_THRESHOLD = 70
MAX_STATE_COMPLETED_JOBS = 200
CLAUDE_CLI_TIMEOUT = 120  # seconds

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

EMBED_COLOR_INFO = 0x3399FF
EMBED_COLOR_BUILD = 0x9933FF

MY_SKILLS = (
    "Python, CUDA/GPU programming, 3D Gaussian Splatting, AI/LLM integration, "
    "Discord Bot development, WebGPU, web scraping, data analysis, automation, "
    "FastAPI, PyTorch. I have RTX 5090 GPU. "
    "I use Claude Code for 3-5x faster development."
)

MY_PROFILE = (
    "- Python/CUDA/GPU専門エンジニア（RTX 5090所持）\n"
    "- 3D Gaussian Splatting、AI/LLM、Discord Bot開発の実績あり\n"
    "- 10,000行超のCUDAラスタライザを個人開発\n"
    "- 65本以上の技術記事をZennに掲載\n"
    "- Claude Code活用で通常の3-5倍速の開発スピード"
)

# ---------------------------------------------------------------------------
# State Management
# ---------------------------------------------------------------------------


def load_pipeline_state() -> dict:
    """Load the pipeline state from disk."""
    if PIPELINE_STATE_FILE.exists():
        text = PIPELINE_STATE_FILE.read_text(encoding="utf-8")
        return json.loads(text)
    return {"jobs": {}}


def save_pipeline_state(state: dict) -> None:
    """Save the pipeline state to disk, trimming old completed/skipped jobs."""
    jobs = state.get("jobs", {})

    # Trim old completed/skipped jobs to keep state file manageable
    terminal_statuses = {"delivered", "skipped"}
    terminal_jobs = [
        (jid, j)
        for jid, j in jobs.items()
        if j.get("status") in terminal_statuses
    ]

    if len(terminal_jobs) > MAX_STATE_COMPLETED_JOBS:
        # Sort by found_at ascending, remove oldest
        terminal_jobs.sort(key=lambda x: x[1].get("found_at", ""))
        excess = len(terminal_jobs) - MAX_STATE_COMPLETED_JOBS
        for jid, _ in terminal_jobs[:excess]:
            del jobs[jid]

    PIPELINE_STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_job_monitor_state() -> dict:
    """Load the job monitor state to get known job IDs."""
    if JOB_MONITOR_STATE_FILE.exists():
        text = JOB_MONITOR_STATE_FILE.read_text(encoding="utf-8")
        return json.loads(text)
    return {"seen_jobs": []}


# ---------------------------------------------------------------------------
# Lancers Page Fetching
# ---------------------------------------------------------------------------


def fetch_job_detail(job_id: str, url: str) -> Optional[dict]:
    """Fetch and parse a Lancers job detail page.

    Returns a dict with keys: description, budget, deadline, or None on failure.
    """
    try:
        print(f"  [{job_id}] 案件詳細を取得中: {url}", file=sys.stderr)
        resp = requests.get(url, timeout=15, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        resp.encoding = "utf-8"
        html = resp.text

        detail = _parse_lancers_detail(html)
        return detail

    except Exception as e:
        print(f"  [{job_id}] 取得エラー: {e}", file=sys.stderr)
        return None


def _parse_lancers_detail(html: str) -> dict:
    """Extract description, budget, and deadline from Lancers detail page HTML."""
    description = ""
    budget = ""
    deadline = ""

    # Extract job description from the main content area
    # Lancers uses various structures; try multiple patterns
    desc_patterns = [
        # Main description block (common pattern)
        r'<div[^>]*class="[^"]*p-work-detail__description[^"]*"[^>]*>(.*?)</div>',
        # Alternative: job_offer_detail or similar
        r'<div[^>]*class="[^"]*job_offer_detail[^"]*"[^>]*>(.*?)</div>',
        # Generic content area
        r'<section[^>]*class="[^"]*detail[^"]*"[^>]*>(.*?)</section>',
        # Fallback: large text block within main content
        r'<div[^>]*id="work_detail"[^>]*>(.*?)</div>',
    ]

    for pattern in desc_patterns:
        match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
        if match:
            raw = match.group(1)
            description = _strip_html(raw)
            if len(description) > 50:
                break

    # If no structured description found, try extracting from og:description
    if len(description) < 50:
        og_match = re.search(
            r'<meta\s+property="og:description"\s+content="([^"]*)"',
            html,
            re.IGNORECASE,
        )
        if og_match:
            description = og_match.group(1).strip()

    # Extract budget
    budget_patterns = [
        r'(?:報酬|予算|金額|価格)[^<]*?([0-9,]+\s*円)',
        r'(?:報酬|予算|金額|価格)[^<]*?(\d[\d,]*\s*[-~]\s*\d[\d,]*\s*円)',
        r'<[^>]*class="[^"]*price[^"]*"[^>]*>([^<]+)',
        r'<[^>]*class="[^"]*budget[^"]*"[^>]*>([^<]+)',
        r'(\d{1,3}(?:,\d{3})*\s*円)',
    ]

    for pattern in budget_patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            budget = _strip_html(match.group(1)).strip()
            if budget:
                break

    # Try to extract budget from structured data
    if not budget:
        price_match = re.search(
            r'"price"[^:]*:\s*"?(\d[\d,]*)"?', html
        )
        if price_match:
            budget = f"{price_match.group(1)}円"

    # Extract deadline
    deadline_patterns = [
        r'(?:納期|期限|締切|期日)[^<]*?(\d{4}[/-]\d{1,2}[/-]\d{1,2})',
        r'<[^>]*class="[^"]*deadline[^"]*"[^>]*>([^<]+)',
        r'<[^>]*class="[^"]*due[^"]*"[^>]*>([^<]+)',
        r'(?:納期|期限|締切)[^<]*?(\d{1,2}[/-]\d{1,2})',
        r'(?:納期|期限|締切)[^<]*?(\d+\s*(?:日|週間?|ヶ月|ヵ月|か月))',
    ]

    for pattern in deadline_patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            deadline = _strip_html(match.group(1)).strip()
            if deadline:
                break

    # Truncate description to avoid Claude CLI token overflow
    max_desc_len = 3000
    if len(description) > max_desc_len:
        description = description[:max_desc_len] + "..."

    return {
        "description": description or "(詳細取得不可)",
        "budget": budget or "(未記載)",
        "deadline": deadline or "(未記載)",
    }


def _strip_html(html_text: str) -> str:
    """Remove HTML tags and normalize whitespace."""
    text = re.sub(r"<br\s*/?>", "\n", html_text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&#\d+;", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Claude CLI Integration
# ---------------------------------------------------------------------------


def call_claude_json(prompt: str) -> Optional[dict]:
    """Call Claude CLI expecting JSON output. Returns parsed dict or None."""
    return _call_claude(prompt, expect_json=True)


def call_claude_text(prompt: str) -> Optional[str]:
    """Call Claude CLI expecting plain text output. Returns string or None."""
    return _call_claude(prompt, expect_json=False)


def _call_claude(prompt: str, *, expect_json: bool) -> Any:
    """Internal: call Claude CLI with prompt via temp file for long prompts."""
    tmp_path: Optional[str] = None
    try:
        # Write prompt to temp file to avoid command-line length limits
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".txt",
            encoding="utf-8",
            delete=False,
        ) as tmp:
            tmp.write(prompt)
            tmp_path = tmp.name

        cmd = ["claude", "-p"]
        if expect_json:
            cmd.extend(["--output-format", "json"])

        # Read prompt from stdin via file redirect
        with open(tmp_path, "r", encoding="utf-8") as f:
            result = subprocess.run(
                cmd,
                stdin=f,
                capture_output=True,
                text=True,
                timeout=CLAUDE_CLI_TIMEOUT,
                encoding="utf-8",
                errors="replace",
            )

        if result.returncode != 0:
            print(
                f"  [Claude CLI] エラー (exit {result.returncode}): "
                f"{result.stderr[:300]}",
                file=sys.stderr,
            )
            return None

        output = result.stdout.strip()
        if not output:
            print("  [Claude CLI] 空の出力", file=sys.stderr)
            return None

        if expect_json:
            return _extract_json(output)
        return output

    except subprocess.TimeoutExpired:
        print(
            f"  [Claude CLI] タイムアウト ({CLAUDE_CLI_TIMEOUT}s)",
            file=sys.stderr,
        )
        return None
    except Exception as e:
        print(f"  [Claude CLI] 例外: {e}", file=sys.stderr)
        return None
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _extract_json(text: str) -> Optional[dict]:
    """Extract JSON from Claude CLI output, handling --output-format json wrapper."""
    # When using --output-format json, Claude CLI wraps output in a JSON object
    # with a "result" field containing the actual text
    try:
        wrapper = json.loads(text)
        if isinstance(wrapper, dict) and "result" in wrapper:
            inner = wrapper["result"]
            # The inner result may be a JSON string that needs parsing
            if isinstance(inner, str):
                return _parse_json_from_text(inner)
            if isinstance(inner, dict):
                return inner
        # If the wrapper itself looks like our expected output
        if isinstance(wrapper, dict) and "score" in wrapper:
            return wrapper
        return wrapper
    except json.JSONDecodeError:
        pass

    # Fallback: try to parse the raw text
    return _parse_json_from_text(text)


def _parse_json_from_text(text: str) -> Optional[dict]:
    """Try to extract a JSON object from text that may contain extra content."""
    # Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find JSON block between curly braces
    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # Find JSON block with nested braces
    match = re.search(r"\{(?:[^{}]|\{[^{}]*\})*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    print(f"  [Claude CLI] JSON解析失敗: {text[:200]}", file=sys.stderr)
    return None


# ---------------------------------------------------------------------------
# Job Evaluation
# ---------------------------------------------------------------------------


def build_evaluation_prompt(
    title: str, description: str, budget: str, deadline: str
) -> str:
    """Build the prompt for Claude to evaluate a job posting."""
    return (
        "You are evaluating a freelance job posting for fit.\n\n"
        f"My skills: {MY_SKILLS}\n\n"
        "Job details:\n"
        f"Title: {title}\n"
        f"Description: {description}\n"
        f"Budget: {budget}\n"
        f"Deadline: {deadline}\n\n"
        "Evaluate and return ONLY valid JSON (no markdown, no explanation):\n"
        "{\n"
        '  "score": <0-100 integer, how well this job fits my skills>,\n'
        '  "reason": "<1-2 sentence explanation in Japanese>",\n'
        '  "estimated_hours": <number>,\n'
        '  "suggested_price": <integer in JPY>,\n'
        '  "difficulty": "<easy|medium|hard>",\n'
        '  "can_automate": <true if Claude Code can build this autonomously>\n'
        "}\n"
    )


def build_proposal_prompt(
    title: str,
    description: str,
    budget: str,
    suggested_price: int,
    estimated_hours: int,
) -> str:
    """Build the prompt for Claude to generate a proposal."""
    estimated_days = max(1, (estimated_hours + 7) // 8)

    return (
        "あなたはフリーランスエンジニアです。以下の案件に提案文を書いてください。\n\n"
        "案件情報:\n"
        f"タイトル: {title}\n"
        f"詳細: {description}\n"
        f"予算: {budget}\n\n"
        "あなたのプロフィール:\n"
        f"{MY_PROFILE}\n\n"
        "ルール:\n"
        "- 自然な日本語で、プロフェッショナルだが温かみのある文体\n"
        "- 200-400文字程度\n"
        "- 具体的な実装方針を1-2行含める\n"
        f"- 見積もり金額: {suggested_price:,}円\n"
        f"- 納期: {estimated_days}日\n"
        "- 案件への質問を1つ含める（真剣に取り組む姿勢を見せる）\n\n"
        "提案文のみ出力してください（説明や前置き不要）。"
    )


def evaluate_job(
    job_id: str,
    title: str,
    url: str,
    *,
    prefetched_html: Optional[str] = None,
) -> Optional[dict]:
    """Evaluate a single job: fetch detail (or use prefetched), call Claude.

    Args:
        job_id: Lancers job identifier (e.g., "la_12345").
        title: Job title extracted from the listing page.
        url: Full URL to the Lancers job detail page.
        prefetched_html: If provided, skip fetching and parse this HTML instead.

    Returns:
        Enriched job data dict, or None on unrecoverable failure.
    """
    now_iso = datetime.now(JST).isoformat()

    # Parse detail from prefetched HTML or fetch fresh
    if prefetched_html is not None:
        detail = _parse_lancers_detail(prefetched_html)
    else:
        detail = fetch_job_detail(job_id, url)

    if not detail:
        return {
            "id": job_id,
            "title": title,
            "url": url,
            "status": "skipped",
            "score": 0,
            "evaluation": {"reason": "詳細ページの取得に失敗"},
            "found_at": now_iso,
        }

    description = detail["description"]
    budget = detail["budget"]
    deadline = detail["deadline"]

    # Evaluate with Claude
    eval_prompt = build_evaluation_prompt(title, description, budget, deadline)
    evaluation = call_claude_json(eval_prompt)

    if not evaluation or "score" not in evaluation:
        print(f"  [{job_id}] 評価失敗、スキップ", file=sys.stderr)
        return {
            "id": job_id,
            "title": title,
            "url": url,
            "status": "skipped",
            "score": 0,
            "evaluation": {"reason": "Claude評価に失敗"},
            "found_at": now_iso,
        }

    score = int(evaluation.get("score", 0))
    suggested_price = int(evaluation.get("suggested_price", 0))
    estimated_hours = int(evaluation.get("estimated_hours", 0))

    job_data: dict[str, Any] = {
        "id": job_id,
        "title": title,
        "url": url,
        "score": score,
        "evaluation": {
            "reason": evaluation.get("reason", ""),
            "estimated_hours": estimated_hours,
            "difficulty": evaluation.get("difficulty", "medium"),
            "can_automate": evaluation.get("can_automate", False),
        },
        "suggested_price": suggested_price,
        "found_at": now_iso,
        "proposed_at": None,
        "accepted_at": None,
        "completed_at": None,
    }

    if score >= SCORE_THRESHOLD:
        # Generate proposal
        print(
            f"  [{job_id}] スコア {score} >= {SCORE_THRESHOLD}、提案文生成中...",
            file=sys.stderr,
        )
        proposal_prompt = build_proposal_prompt(
            title, description, budget, suggested_price, estimated_hours
        )
        proposal_text = call_claude_text(proposal_prompt)

        if proposal_text:
            job_data["status"] = "evaluated"
            job_data["proposal_text"] = proposal_text
        else:
            # Evaluation succeeded but proposal failed; still save evaluation
            job_data["status"] = "evaluated"
            job_data["proposal_text"] = "(提案文の生成に失敗)"
    else:
        job_data["status"] = "skipped"
        job_data["proposal_text"] = None

    return job_data


# ---------------------------------------------------------------------------
# Discord Notifications
# ---------------------------------------------------------------------------


def post_to_discord(payload: dict) -> None:
    """Send a webhook payload to Discord."""
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("[Discord] DISCORD_WEBHOOK_URL が未設定", file=sys.stderr)
        return

    try:
        resp = requests.post(webhook_url, json=payload, timeout=15)
        if resp.status_code == 204:
            print("[Discord] 投稿成功")
        else:
            print(
                f"[Discord] HTTP {resp.status_code}: {resp.text[:200]}",
                file=sys.stderr,
            )
    except Exception as e:
        print(f"[Discord] エラー: {e}", file=sys.stderr)


def notify_scan_results(
    ready_jobs: list[dict], skipped_jobs: list[dict]
) -> None:
    """Send Discord notification with scan results."""
    if not ready_jobs and not skipped_jobs:
        return

    now = datetime.now(JST)
    parts = []

    if ready_jobs:
        parts.append(f"**提案準備完了 ({len(ready_jobs)}件)**")
        for j in ready_jobs[:10]:
            title = j["title"][:60]
            score = j.get("score", 0)
            price = j.get("suggested_price", 0)
            parts.append(
                f"  [{title}]({j['url']}) - "
                f"スコア: {score} - {price:,}円"
            )

    if skipped_jobs:
        if parts:
            parts.append("")
        parts.append(f"**スキップ ({len(skipped_jobs)}件)**")
        for j in skipped_jobs[:5]:
            title = j["title"][:60]
            score = j.get("score", 0)
            reason = j.get("evaluation", {}).get("reason", "")[:60]
            parts.append(
                f"  [{title}]({j['url']}) - "
                f"スコア: {score} - {reason}"
            )
        if len(skipped_jobs) > 5:
            parts.append(f"  ...他 {len(skipped_jobs) - 5}件")

    payload = {
        "username": "Freelance Pipeline",
        "embeds": [
            {
                "title": "案件スキャン完了",
                "description": "\n".join(parts),
                "color": EMBED_COLOR_INFO,
                "footer": {"text": f"Pipeline | {now.strftime('%Y/%m/%d %H:%M')} JST"},
                "timestamp": now.isoformat(),
            }
        ],
    }
    post_to_discord(payload)


def notify_build_complete(job_data: dict, workspace: str) -> None:
    """Send Discord notification when a project build completes."""
    now = datetime.now(JST)
    payload = {
        "username": "Freelance Pipeline",
        "embeds": [
            {
                "title": "プロジェクト完成",
                "description": (
                    f"**案件**: [{job_data['title']}]({job_data['url']})\n"
                    f"**ワークスペース**: `{workspace}`\n\n"
                    "確認してから納品してください"
                ),
                "color": EMBED_COLOR_BUILD,
                "footer": {"text": f"Pipeline | {now.strftime('%Y/%m/%d %H:%M')} JST"},
                "timestamp": now.isoformat(),
            }
        ],
    }
    post_to_discord(payload)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_scan() -> None:
    """Evaluate new jobs from job monitor and generate proposals."""
    print(
        f"[Pipeline] スキャン開始: "
        f"{datetime.now(JST).strftime('%Y/%m/%d %H:%M')}",
    )

    # Load states
    monitor_state = load_job_monitor_state()
    pipeline_state = load_pipeline_state()
    pipeline_jobs = pipeline_state.get("jobs", {})

    # Find new job IDs not yet in pipeline
    monitor_ids = set(monitor_state.get("seen_jobs", []))
    pipeline_ids = set(pipeline_jobs.keys())
    new_ids = monitor_ids - pipeline_ids

    if not new_ids:
        print("[Pipeline] 新規案件なし")
        save_pipeline_state(pipeline_state)
        return

    print(f"[Pipeline] 新規案件: {len(new_ids)}件")

    ready_jobs: list[dict] = []
    skipped_jobs: list[dict] = []
    processed = 0

    for job_id in sorted(new_ids):
        # Extract job number from ID (la_XXXXX -> XXXXX)
        job_num = job_id.replace("la_", "")
        url = f"https://www.lancers.jp/work/detail/{job_num}"

        # We don't have the title from the monitor state; use placeholder
        # until we fetch the detail page. The monitor only stores IDs.
        title = f"案件 #{job_num}"
        prefetched_html: Optional[str] = None

        # Fetch page once: extract title and pass HTML to evaluate_job
        try:
            print(
                f"\n[{processed + 1}/{len(new_ids)}] {job_id} を評価中...",
                file=sys.stderr,
            )
            resp = requests.get(
                url, timeout=15, headers={"User-Agent": USER_AGENT}
            )
            resp.raise_for_status()
            resp.encoding = "utf-8"
            prefetched_html = resp.text

            # Extract title from og:title or <title> tag
            title_match = re.search(
                r'<meta\s+property="og:title"\s+content="([^"]*)"',
                prefetched_html,
                re.IGNORECASE,
            )
            if title_match:
                title = title_match.group(1).strip()
            else:
                title_match = re.search(
                    r"<title>([^<]+)</title>",
                    prefetched_html,
                    re.IGNORECASE,
                )
                if title_match:
                    title = title_match.group(1).strip()
                    # Remove common suffixes
                    title = re.sub(
                        r"\s*[|\-].*ランサーズ.*$", "", title
                    ).strip()

        except Exception as e:
            print(f"  [{job_id}] ページ取得失敗: {e}", file=sys.stderr)

        # Evaluate the job (reuse fetched HTML to avoid double request)
        job_data = evaluate_job(
            job_id, title, url, prefetched_html=prefetched_html
        )
        if job_data is None:
            continue

        pipeline_jobs[job_id] = job_data

        if job_data.get("status") == "evaluated":
            ready_jobs.append(job_data)
            print(
                f"  -> 提案準備完了 (スコア: {job_data.get('score', 0)}, "
                f"{job_data.get('suggested_price', 0):,}円)"
            )
        else:
            skipped_jobs.append(job_data)
            reason = job_data.get("evaluation", {}).get("reason", "")
            print(
                f"  -> スキップ (スコア: {job_data.get('score', 0)}) {reason}"
            )

        processed += 1

        # Rate limit between job fetches
        if processed < len(new_ids):
            time.sleep(REQUEST_DELAY)

    # Save state
    pipeline_state["jobs"] = pipeline_jobs
    save_pipeline_state(pipeline_state)

    # Discord notification
    notify_scan_results(ready_jobs, skipped_jobs)

    print(
        f"\n[Pipeline] スキャン完了: "
        f"提案準備 {len(ready_jobs)}件, スキップ {len(skipped_jobs)}件"
    )


def cmd_propose() -> None:
    """List jobs that have proposals ready for submission."""
    pipeline_state = load_pipeline_state()
    jobs = pipeline_state.get("jobs", {})

    evaluated = [
        j for j in jobs.values() if j.get("status") == "evaluated"
    ]

    if not evaluated:
        print("[Pipeline] 提案可能な案件なし")
        return

    print(f"\n提案可能な案件 ({len(evaluated)}件):")
    print("=" * 80)

    for j in sorted(evaluated, key=lambda x: x.get("score", 0), reverse=True):
        score = j.get("score", 0)
        price = j.get("suggested_price", 0)
        difficulty = j.get("evaluation", {}).get("difficulty", "?")
        hours = j.get("evaluation", {}).get("estimated_hours", 0)
        can_auto = j.get("evaluation", {}).get("can_automate", False)

        print(f"\nID: {j['id']}")
        print(f"  Title:      {j['title']}")
        print(f"  URL:        {j['url']}")
        print(f"  Score:      {score}")
        print(f"  Price:      {price:,}円")
        print(f"  Difficulty: {difficulty}")
        print(f"  Hours:      {hours}h")
        print(f"  Automate:   {'Yes' if can_auto else 'No'}")
        print(f"  Reason:     {j.get('evaluation', {}).get('reason', '')}")
        print()

        proposal = j.get("proposal_text", "")
        if proposal and proposal != "(提案文の生成に失敗)":
            print("  --- Proposal ---")
            for line in proposal.split("\n"):
                print(f"  {line}")
            print("  ----------------")

    print()
    print(
        "提案を提出するには Lancers サイトで手動提出してください。\n"
        "提出後: python scripts/freelance_pipeline.py accept <JOB_ID>"
    )


def cmd_accept(job_id: str) -> None:
    """Mark a job as accepted (proposal was submitted and client accepted)."""
    pipeline_state = load_pipeline_state()
    jobs = pipeline_state.get("jobs", {})

    if job_id not in jobs:
        print(f"[Pipeline] エラー: {job_id} が見つかりません")
        sys.exit(1)

    job = jobs[job_id]
    job["status"] = "accepted"
    job["accepted_at"] = datetime.now(JST).isoformat()

    save_pipeline_state(pipeline_state)
    print(f"[Pipeline] {job_id} を accepted に更新しました")
    print(f"  Title: {job['title']}")
    print(
        f"\n次のステップ: python scripts/freelance_pipeline.py build {job_id}"
    )


def cmd_build(job_id: str) -> None:
    """Auto-build a project for an accepted job using Claude Code."""
    pipeline_state = load_pipeline_state()
    jobs = pipeline_state.get("jobs", {})

    if job_id not in jobs:
        print(f"[Pipeline] エラー: {job_id} が見つかりません")
        sys.exit(1)

    job = jobs[job_id]

    if job.get("status") not in ("accepted", "evaluated"):
        print(
            f"[Pipeline] 警告: {job_id} のステータスは '{job.get('status')}' です。"
            f" 通常は accepted の案件を build します。"
        )
        confirm = input("続行しますか? [y/N]: ").strip().lower()
        if confirm != "y":
            print("[Pipeline] 中止")
            return

    # Create workspace
    workspace = FREELANCE_WORKSPACE_ROOT / job_id
    workspace.mkdir(parents=True, exist_ok=True)
    print(f"[Pipeline] ワークスペース: {workspace}")

    # Write requirements.md
    requirements_path = workspace / "requirements.md"
    evaluation = job.get("evaluation", {})
    proposal = job.get("proposal_text", "")

    requirements_content = (
        f"# {job['title']}\n\n"
        f"## Source\n"
        f"- URL: {job['url']}\n"
        f"- Score: {job.get('score', 0)}\n"
        f"- Difficulty: {evaluation.get('difficulty', 'unknown')}\n"
        f"- Estimated Hours: {evaluation.get('estimated_hours', 0)}\n"
        f"- Suggested Price: {job.get('suggested_price', 0):,}円\n\n"
        f"## Evaluation\n"
        f"{evaluation.get('reason', '')}\n\n"
        f"## Proposal\n"
        f"{proposal}\n\n"
        f"## Job Description\n"
        f"Please refer to the original posting for full details:\n"
        f"{job['url']}\n"
    )
    requirements_path.write_text(requirements_content, encoding="utf-8")
    print(f"[Pipeline] requirements.md を作成しました")

    # Update status
    job["status"] = "building"
    job["workspace"] = str(workspace)
    save_pipeline_state(pipeline_state)

    # Run Claude Code to build the project
    build_prompt = (
        "Build a complete project based on requirements.md. "
        "Create all necessary source files, tests, and a README.md "
        "with setup instructions. Make it production-ready."
    )

    print("[Pipeline] Claude Code でプロジェクトをビルド中...")
    try:
        result = subprocess.run(
            [
                "claude",
                "--dangerously-skip-permissions",
                "-p",
                build_prompt,
            ],
            capture_output=True,
            text=True,
            timeout=600,  # 10 minutes for build
            encoding="utf-8",
            errors="replace",
            cwd=str(workspace),
        )

        if result.returncode == 0:
            print("[Pipeline] ビルド成功")
            job["status"] = "delivered"
            job["completed_at"] = datetime.now(JST).isoformat()
        else:
            print(
                f"[Pipeline] ビルド警告 (exit {result.returncode})",
                file=sys.stderr,
            )
            if result.stderr:
                print(f"  stderr: {result.stderr[:500]}", file=sys.stderr)
            # Still mark as delivered; user should review
            job["status"] = "delivered"
            job["completed_at"] = datetime.now(JST).isoformat()

        # Log build output
        build_log = workspace / "build.log"
        log_content = ""
        if result.stdout:
            log_content += f"=== STDOUT ===\n{result.stdout}\n"
        if result.stderr:
            log_content += f"=== STDERR ===\n{result.stderr}\n"
        if log_content:
            build_log.write_text(log_content, encoding="utf-8")
            print(f"[Pipeline] ビルドログ: {build_log}")

    except subprocess.TimeoutExpired:
        print("[Pipeline] ビルドタイムアウト (10分)", file=sys.stderr)
        job["status"] = "delivered"
        job["completed_at"] = datetime.now(JST).isoformat()

    except Exception as e:
        print(f"[Pipeline] ビルドエラー: {e}", file=sys.stderr)
        job["status"] = "accepted"  # Revert to accepted so user can retry

    save_pipeline_state(pipeline_state)

    # Discord notification
    if job.get("status") == "delivered":
        notify_build_complete(job, str(workspace))
        print(
            f"\n[Pipeline] プロジェクト完成: {workspace}\n"
            f"確認してから納品してください。"
        )


def cmd_status() -> None:
    """Print a summary table of all jobs in the pipeline."""
    pipeline_state = load_pipeline_state()
    jobs = pipeline_state.get("jobs", {})

    if not jobs:
        print("[Pipeline] パイプラインにジョブなし")
        return

    # Group by status
    status_groups: dict[str, list[dict]] = {}
    for j in jobs.values():
        status = j.get("status", "unknown")
        status_groups.setdefault(status, []).append(j)

    status_order = [
        "building",
        "accepted",
        "evaluated",
        "found",
        "delivered",
        "skipped",
    ]
    status_labels = {
        "found": "発見",
        "evaluated": "提案準備完了",
        "proposed": "提案済み",
        "accepted": "受注済み",
        "building": "ビルド中",
        "delivered": "納品済み",
        "skipped": "スキップ",
    }

    total = len(jobs)
    print(f"\n[Pipeline] ジョブ一覧 ({total}件)")
    print("=" * 90)

    for status in status_order:
        group = status_groups.pop(status, [])
        if not group:
            continue

        label = status_labels.get(status, status)
        print(f"\n--- {label} ({len(group)}件) ---")

        # Sort by score descending
        group.sort(key=lambda x: x.get("score", 0), reverse=True)

        for j in group:
            score = j.get("score", 0)
            price = j.get("suggested_price", 0)
            title = j.get("title", "?")[:50]
            job_id = j.get("id", "?")

            print(
                f"  {job_id:15s}  "
                f"Score:{score:3d}  "
                f"{price:>8,}円  "
                f"{title}"
            )

    # Any remaining statuses
    for status, group in status_groups.items():
        if not group:
            continue
        label = status_labels.get(status, status)
        print(f"\n--- {label} ({len(group)}件) ---")
        for j in group:
            print(f"  {j.get('id', '?'):15s}  {j.get('title', '?')[:50]}")

    # Summary line
    print()
    print("サマリー:")
    for status in status_order:
        count = len([j for j in jobs.values() if j.get("status") == status])
        if count > 0:
            label = status_labels.get(status, status)
            print(f"  {label}: {count}件")


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------


def print_usage() -> None:
    """Print usage information."""
    print(
        "使い方:\n"
        "  python scripts/freelance_pipeline.py scan           "
        "# 新規案件の評価 + 提案文生成\n"
        "  python scripts/freelance_pipeline.py propose        "
        "# 提案可能な案件一覧\n"
        "  python scripts/freelance_pipeline.py accept JOB_ID  "
        "# 受注済みに変更\n"
        "  python scripts/freelance_pipeline.py build JOB_ID   "
        "# プロジェクト自動ビルド\n"
        "  python scripts/freelance_pipeline.py status         "
        "# パイプライン状態一覧\n"
    )


def main() -> None:
    """Parse command and dispatch."""
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "scan":
        cmd_scan()

    elif command == "propose":
        cmd_propose()

    elif command == "accept":
        if len(sys.argv) < 3:
            print("エラー: JOB_ID を指定してください")
            print("  python scripts/freelance_pipeline.py accept la_12345")
            sys.exit(1)
        cmd_accept(sys.argv[2])

    elif command == "build":
        if len(sys.argv) < 3:
            print("エラー: JOB_ID を指定してください")
            print("  python scripts/freelance_pipeline.py build la_12345")
            sys.exit(1)
        cmd_build(sys.argv[2])

    elif command == "status":
        cmd_status()

    else:
        print(f"不明なコマンド: {command}")
        print_usage()
        sys.exit(1)


if __name__ == "__main__":
    main()
