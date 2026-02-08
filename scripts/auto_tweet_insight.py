#!/usr/bin/env python3
"""
Auto Tweet Insight - トレンド技術に対する考察ツイートを自動投稿

日次ダイジェストで収集した情報からAIが考察を生成し、Twitter/Xに投稿する。
1日3-4回、ランダムな遅延(0-45分)で自然な投稿パターンを実現。

使い方:
  python scripts/auto_tweet_insight.py           # 考察ツイート投稿
  python scripts/auto_tweet_insight.py --dry-run  # 投稿せずに確認のみ

環境変数:
  TWITTER_API_KEY, TWITTER_API_SECRET,
  TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET
"""

import io
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
STATE_FILE = REPO_ROOT / ".digest-state.json"
TWEET_LOG = REPO_ROOT / ".insight-tweets.json"
JST = timezone(timedelta(hours=9))
MAX_TWEET_LENGTH = 280


def load_digest_state() -> dict:
    """ダイジェストの状態ファイルを読み込み"""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def load_tweet_log() -> dict:
    """ツイート済みログを読み込み"""
    if TWEET_LOG.exists():
        return json.loads(TWEET_LOG.read_text(encoding="utf-8"))
    return {"tweeted": [], "last_tweet": None}


def save_tweet_log(log: dict):
    """ツイート済みログを保存"""
    if len(log.get("tweeted", [])) > 200:
        log["tweeted"] = log["tweeted"][-200:]
    TWEET_LOG.write_text(
        json.dumps(log, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def collect_recent_topics() -> list[dict]:
    """ダイジェスト状態から最近の話題を収集（seen = 最近収集されたもの）"""
    state = load_digest_state()
    topics = []

    # HF papers (arXiv IDs)
    for paper_id in state.get("hf_seen", [])[-10:]:
        topics.append({
            "type": "paper",
            "id": paper_id,
            "url": f"https://huggingface.co/papers/{paper_id}",
        })

    # Reddit posts
    for post_id in state.get("reddit_seen", [])[-8:]:
        topics.append({
            "type": "reddit",
            "id": post_id,
            "url": f"https://reddit.com/comments/{post_id}",
        })

    # Anthropic news
    for url in state.get("anthropic_seen", [])[-5:]:
        topics.append({
            "type": "anthropic",
            "id": url,
            "url": url,
        })

    return topics


def pick_topic(topics: list[dict], tweet_log: dict) -> dict | None:
    """まだツイートしていないトピックをランダムに選択"""
    tweeted_ids = set(tweet_log.get("tweeted", []))
    untweeted = [t for t in topics if t["id"] not in tweeted_ids]

    if not untweeted:
        return None

    # 新しいものを優先（後ろの方が新しい）
    weights = [i + 1 for i in range(len(untweeted))]
    return random.choices(untweeted, weights=weights, k=1)[0]


def generate_insight(topic: dict) -> str | None:
    """Claude CLIでトピックに対する考察ツイートを生成"""
    claude_cmd = shutil.which("claude")
    if not claude_cmd:
        print("[Insight] claude CLI not found", file=sys.stderr)
        return None

    prompt = f"""You are a Japanese tech engineer who specializes in 3DGS, CUDA, GPU programming, and AI.
Generate a single insightful tweet (in Japanese) about this topic.

Topic URL: {topic['url']}
Topic type: {topic['type']}

Rules:
- Write in Japanese, casual but knowledgeable tone (エンジニア目線)
- 200-270 characters max (leave room for URL)
- Include your personal take/insight, not just a summary
- Add 1-2 relevant hashtags (e.g. #3DGS #CUDA #AI #LLM #GPU)
- Do NOT include the URL (it will be appended separately)
- Do NOT use emoji excessively (max 1-2)
- Sound like a real engineer sharing thoughts, not a bot
- If the topic is about a paper, comment on its significance or limitations
- If the topic is about a product/release, comment on practical implications

Output ONLY the tweet text, nothing else."""

    try:
        import tempfile
        prompt_file = Path(tempfile.gettempdir()) / "insight_tweet_prompt.txt"
        prompt_file.write_text(prompt, encoding="utf-8")

        if sys.platform == "win32":
            shell_cmd = f'chcp 65001 >nul && "{claude_cmd}" -p < "{prompt_file}"'
        else:
            shell_cmd = f'"{claude_cmd}" -p < "{prompt_file}"'

        result = subprocess.run(
            shell_cmd, capture_output=True, timeout=120, shell=True,
        )
        prompt_file.unlink(missing_ok=True)

        if result.returncode != 0:
            print(f"[Insight] Claude CLI failed: {result.returncode}", file=sys.stderr)
            return None

        output = result.stdout.decode("utf-8", errors="replace").strip()

        # Clean up: remove quotes if wrapped
        if output.startswith('"') and output.endswith('"'):
            output = output[1:-1]
        if output.startswith("'") and output.endswith("'"):
            output = output[1:-1]

        return output if output else None

    except subprocess.TimeoutExpired:
        print("[Insight] Claude CLI timeout", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[Insight] Error: {e}", file=sys.stderr)
        return None


def compose_tweet(insight: str, topic: dict) -> str:
    """ツイート本文を組み立て（URL付き）"""
    url = topic["url"]
    # URL is always 23 chars on Twitter (t.co shortening)
    max_text = MAX_TWEET_LENGTH - 24  # 23 for URL + 1 for newline
    text = insight[:max_text]
    return f"{text}\n{url}"


def post_tweet(tweet_text: str, dry_run: bool = False) -> bool:
    """Twitter/Xに投稿"""
    if dry_run:
        print(f"\n[DRY RUN] Would tweet:\n{tweet_text}")
        return True

    api_key = os.environ.get("TWITTER_API_KEY")
    api_secret = os.environ.get("TWITTER_API_SECRET")
    access_token = os.environ.get("TWITTER_ACCESS_TOKEN")
    access_secret = os.environ.get("TWITTER_ACCESS_TOKEN_SECRET")

    if not all([api_key, api_secret, access_token, access_secret]):
        print("[Tweet] Twitter API credentials not set", file=sys.stderr)
        return False

    try:
        import tweepy
        client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret,
        )
        resp = client.create_tweet(text=tweet_text)
        tweet_id = resp.data["id"]
        print(f"[Tweet] Posted: https://x.com/i/status/{tweet_id}")
        return True
    except Exception as e:
        print(f"[Tweet] Error: {e}", file=sys.stderr)
        return False


def random_delay(max_minutes: int = 45):
    """自然な投稿パターンのためのランダム遅延"""
    delay = random.randint(0, max_minutes * 60)
    if delay > 60:
        print(f"[Insight] Random delay: {delay // 60}m {delay % 60}s")
        time.sleep(delay)


def main():
    dry_run = "--dry-run" in sys.argv
    no_delay = "--no-delay" in sys.argv

    print(f"[Insight] Start: {datetime.now(JST).strftime('%Y/%m/%d %H:%M')}")

    # Random delay for natural posting pattern
    if not dry_run and not no_delay:
        random_delay(45)

    # Collect topics
    topics = collect_recent_topics()
    if not topics:
        print("[Insight] No topics available")
        return

    print(f"[Insight] {len(topics)} topics available")

    # Pick untweeted topic
    tweet_log = load_tweet_log()
    topic = pick_topic(topics, tweet_log)
    if not topic:
        print("[Insight] All topics already tweeted")
        return

    print(f"[Insight] Selected: {topic['type']} - {topic['url']}")

    # Generate insight
    insight = generate_insight(topic)
    if not insight:
        print("[Insight] Failed to generate insight")
        return

    # Compose and post
    tweet_text = compose_tweet(insight, topic)
    print(f"[Insight] Tweet ({len(tweet_text)} chars):\n{tweet_text}")

    if post_tweet(tweet_text, dry_run=dry_run):
        tweet_log["tweeted"].append(topic["id"])
        tweet_log["last_tweet"] = datetime.now(JST).isoformat()
        save_tweet_log(tweet_log)
        print("[Insight] Done")
    else:
        print("[Insight] Tweet failed")


if __name__ == "__main__":
    main()
