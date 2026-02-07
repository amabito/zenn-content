#!/usr/bin/env python3
"""
Daily Tech Digest - 3DGS/CUDA/AI関連の新着情報を収集しDiscordに通知

情報源:
  - 日本語テックニュース (Gigazine, ITmedia AI+, Publickey, AI-SCHOLAR)
  - AI/MLまとめ (Hugging Face Daily Papers, Papers With Code)
  - Reddit (r/3DGaussianSplatting, r/MachineLearning, r/LocalLLaMA)
  - YouTube (Two Minute Papers, Yannic Kilcher, 3Blue1Brown)
  - GitHub Releases (gsplat, nerfstudio等)
  - Anthropic News

使い方:
  python scripts/daily_tech_digest.py                # 収集 + Discord投稿
  python scripts/daily_tech_digest.py --collect-only  # 収集のみ（stdout出力）
  python scripts/daily_tech_digest.py --auto-summarize # claude CLIで要約 + Discord投稿
  python scripts/daily_tech_digest.py --dry-run        # Discord投稿しない

環境変数:
  DISCORD_WEBHOOK_URL  - Discord Webhook URL（必須、--dry-run時は不要）
  GITHUB_TOKEN         - GitHub API トークン（任意、レート上限緩和）
"""

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Windows stdout エンコーディング対策
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import feedparser
import requests

# ──────────────────────────────────────────────
# 定数
# ──────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
STATE_FILE = REPO_ROOT / ".digest-state.json"

JST = timezone(timedelta(hours=9))
USER_AGENT = "TechDigestBot/2.0"

# ── 日本語テックニュース RSS ──
JP_RSS_FEEDS = {
    "Gigazine": "https://gigazine.net/news/rss_2.0/",
    "ITmedia AI+": "https://rss.itmedia.co.jp/rss/2.0/aiplus.xml",
    "Publickey": "https://www.publickey1.jp/atom.xml",
}
# 日本語フィードのキーワードフィルタ
JP_KEYWORDS = [
    "ai", "gpu", "cuda", "nvidia", "3d", "gaussian", "nerf",
    "レンダリング", "生成ai", "llm", "claude", "chatgpt", "gemini",
    "pytorch", "機械学習", "深層学習", "ディープラーニング",
    "webgpu", "ガウシアン", "点群", "ビジョン",
    "rtx", "blackwell", "geforce", "自動運転",
]

# ── AI/MLまとめ系 ──
HF_DAILY_PAPERS_URL = "https://huggingface.co/api/daily_papers"
PAPERS_WITH_CODE_URL = "https://paperswithcode.com/latest"

# ── Reddit ──
REDDIT_SUBREDDITS = [
    "3DGaussianSplatting",
    "MachineLearning",
    "LocalLLaMA",
]
REDDIT_MIN_SCORE = 20  # 最低スコア（ノイズ除去）

# ── YouTube チャンネル ──
YOUTUBE_CHANNELS = {
    "Two Minute Papers": "UCbfYPyITQ-7l4upoX8nvctg",
    "Yannic Kilcher": "UCZHmQk67mSJgfCCTn7xBfew",
    "3Blue1Brown": "UCYO_jab_esuFRV4b17AJtAw",
}

# ── GitHub Releases（重要リポジトリのみ）──
GITHUB_WATCH_REPOS = [
    "nerfstudio-project/gsplat",
    "nerfstudio-project/nerfstudio",
    "nv-tlabs/ppisp",
    "nv-tlabs/3dgrut",
    "pytorch/pytorch",
]

# ── Anthropic News ──
ANTHROPIC_NEWS_URL = "https://www.anthropic.com/news"

# ── Discord Embed色 ──
EMBED_COLOR_JP = 0xE60033       # 日本語ニュース 赤
EMBED_COLOR_AI = 0x9B59B6       # AI/MLまとめ 紫
EMBED_COLOR_REDDIT = 0xFF4500   # Reddit オレンジ
EMBED_COLOR_YOUTUBE = 0xFF0000  # YouTube 赤
EMBED_COLOR_GITHUB = 0x238636   # GitHub 緑
EMBED_COLOR_ANTHROPIC = 0xD4A574  # Anthropic ベージュ
EMBED_COLOR_SUMMARY = 0xF5A623  # 要約 オレンジ


# ──────────────────────────────────────────────
# State管理
# ──────────────────────────────────────────────

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"last_run": None}


def save_state(state: dict):
    state["last_run"] = datetime.now(JST).isoformat()
    for key, val in state.items():
        if isinstance(val, list) and len(val) > 500:
            state[key] = val[-500:]
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _seen_set(state: dict, key: str) -> set:
    return set(state.get(key, []))


def _save_seen(state: dict, key: str, seen: set):
    state[key] = list(seen)


# ──────────────────────────────────────────────
# 1. 日本語テックニュース
# ──────────────────────────────────────────────

def fetch_jp_news(state: dict) -> list[dict]:
    """日本語テックサイトのRSSから関連ニュースを取得"""
    items = []
    seen = _seen_set(state, "jp_seen")
    cutoff = datetime.now(timezone.utc) - timedelta(days=3)

    for name, url in JP_RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:30]:
                entry_id = entry.get("link", entry.get("id", ""))
                if not entry_id or entry_id in seen:
                    continue

                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                    if pub < cutoff:
                        continue

                title = re.sub(r"<[^>]+>", "", entry.get("title", "")).strip()
                summary = re.sub(r"<[^>]+>", "", entry.get("summary", "")[:300]).strip()

                text_lower = (title + " " + summary).lower()
                if not any(kw in text_lower for kw in JP_KEYWORDS):
                    continue

                items.append({
                    "source": "jp_news",
                    "id": entry_id,
                    "feed_name": name,
                    "title": title,
                    "url": entry_id,
                    "summary": summary[:150],
                })
                seen.add(entry_id)
        except Exception as e:
            print(f"[JP News] {name}: {e}", file=sys.stderr)

    _save_seen(state, "jp_seen", seen)
    return items


# ──────────────────────────────────────────────
# 2. AI/MLまとめ系
# ──────────────────────────────────────────────

def fetch_hf_daily_papers(state: dict) -> list[dict]:
    """Hugging Face Daily Papersから注目論文を取得"""
    items = []
    seen = _seen_set(state, "hf_seen")

    try:
        resp = requests.get(HF_DAILY_PAPERS_URL, timeout=15,
                            headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        papers = resp.json()

        for paper in papers[:20]:
            paper_data = paper.get("paper", {})
            paper_id = paper_data.get("id", "")
            if not paper_id or paper_id in seen:
                continue

            title = paper_data.get("title", "").replace("\n", " ").strip()
            summary = paper_data.get("summary", "")[:200].replace("\n", " ").strip()
            upvotes = paper.get("numUpvotes", 0)

            items.append({
                "source": "hf_papers",
                "id": paper_id,
                "title": title,
                "url": f"https://huggingface.co/papers/{paper_id}",
                "summary": summary,
                "upvotes": upvotes,
            })
            seen.add(paper_id)
    except Exception as e:
        print(f"[HF Papers] エラー: {e}", file=sys.stderr)

    _save_seen(state, "hf_seen", seen)
    return items


# ──────────────────────────────────────────────
# 3. Reddit
# ──────────────────────────────────────────────

def fetch_reddit(state: dict) -> list[dict]:
    """Redditの関連サブレディットからホットな投稿を取得"""
    items = []
    seen = _seen_set(state, "reddit_seen")

    for subreddit in REDDIT_SUBREDDITS:
        try:
            url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit=15"
            resp = requests.get(url, timeout=15, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            data = resp.json()

            for post in data.get("data", {}).get("children", []):
                pdata = post.get("data", {})
                post_id = pdata.get("id", "")
                if not post_id or post_id in seen:
                    continue

                score = pdata.get("score", 0)
                if score < REDDIT_MIN_SCORE:
                    continue

                # stickied投稿はスキップ
                if pdata.get("stickied"):
                    continue

                title = pdata.get("title", "").strip()
                permalink = pdata.get("permalink", "")

                items.append({
                    "source": "reddit",
                    "id": post_id,
                    "subreddit": subreddit,
                    "title": title,
                    "url": f"https://reddit.com{permalink}" if permalink else "",
                    "score": score,
                    "comments": pdata.get("num_comments", 0),
                })
                seen.add(post_id)

            time.sleep(1)
        except Exception as e:
            print(f"[Reddit] r/{subreddit}: {e}", file=sys.stderr)

    _save_seen(state, "reddit_seen", seen)
    return items


# ──────────────────────────────────────────────
# 4. YouTube
# ──────────────────────────────────────────────

def fetch_youtube(state: dict) -> list[dict]:
    """YouTubeチャンネルの最新動画を取得（Atom RSS）"""
    items = []
    seen = _seen_set(state, "youtube_seen")
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    for channel_name, channel_id in YOUTUBE_CHANNELS.items():
        try:
            url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
            feed = feedparser.parse(url)

            for entry in feed.entries[:5]:
                video_id = entry.get("yt_videoid", entry.get("id", ""))
                if not video_id or video_id in seen:
                    continue

                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                    if pub < cutoff:
                        continue

                title = entry.get("title", "").strip()
                link = entry.get("link", "")

                items.append({
                    "source": "youtube",
                    "id": video_id,
                    "channel": channel_name,
                    "title": title,
                    "url": link,
                })
                seen.add(video_id)
        except Exception as e:
            print(f"[YouTube] {channel_name}: {e}", file=sys.stderr)

    _save_seen(state, "youtube_seen", seen)
    return items


# ──────────────────────────────────────────────
# 5. GitHub Releases（重要リポジトリのみ）
# ──────────────────────────────────────────────

def _github_headers() -> dict:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_github_releases(state: dict) -> list[dict]:
    """監視対象リポジトリの新しいリリースを取得"""
    items = []
    seen = _seen_set(state, "github_releases_seen")
    headers = _github_headers()
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    for repo in GITHUB_WATCH_REPOS:
        try:
            resp = requests.get(
                f"https://api.github.com/repos/{repo}/releases",
                headers=headers, params={"per_page": 3}, timeout=15,
            )
            if resp.status_code == 404:
                continue
            resp.raise_for_status()

            for release in resp.json():
                release_id = f"{repo}/{release['tag_name']}"
                if release_id in seen:
                    continue

                pub = datetime.fromisoformat(
                    release["published_at"].replace("Z", "+00:00")
                )
                if pub < cutoff:
                    continue

                body = (release.get("body") or "")[:200].replace("\n", " ").strip()
                items.append({
                    "source": "github_release",
                    "id": release_id,
                    "title": f"{repo.split('/')[-1]} {release['tag_name']}",
                    "repo": repo,
                    "url": release["html_url"],
                    "summary": body,
                })
                seen.add(release_id)

            time.sleep(0.5)
        except Exception as e:
            print(f"[GitHub] {repo}: {e}", file=sys.stderr)

    _save_seen(state, "github_releases_seen", seen)
    return items


# ──────────────────────────────────────────────
# 6. Anthropic News
# ──────────────────────────────────────────────

def fetch_anthropic_news(state: dict) -> list[dict]:
    """Anthropicニュースページから新着記事を取得"""
    items = []
    seen = _seen_set(state, "anthropic_seen")

    try:
        resp = requests.get(ANTHROPIC_NEWS_URL, timeout=15,
                            headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        html = resp.text

        pattern = r'<a[^>]*href="(/news/[^"]+)"[^>]*>(.*?)</a>'
        matches = re.findall(pattern, html, re.DOTALL)

        for path, title_html in matches[:15]:
            url = f"https://www.anthropic.com{path}"
            if url in seen:
                continue

            raw_title = re.sub(r"<[^>]+>", "", title_html).strip()
            raw_title = raw_title.replace("&#x27;", "'").replace("&amp;", "&")
            if not raw_title or len(raw_title) < 5:
                continue

            cleaned = raw_title
            _labels = ["Announcements", "Product", "Policy", "Research",
                       "Case Study", "Company"]
            _date_re = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}"
            for _ in range(3):
                cleaned = re.sub(_date_re, "", cleaned).strip()
                for label in _labels:
                    if cleaned.startswith(label):
                        cleaned = cleaned[len(label):].strip()
                    if cleaned.endswith(label):
                        cleaned = cleaned[:-len(label)].strip()

            if len(cleaned) > 100:
                split_match = re.search(r'[a-z0-9][A-Z]', cleaned)
                if split_match:
                    title = cleaned[:split_match.start() + 1]
                else:
                    title = cleaned[:150]
            else:
                title = cleaned

            if len(title) < 5:
                continue

            items.append({
                "source": "anthropic",
                "id": url,
                "title": title[:150],
                "url": url,
            })
            seen.add(url)

    except Exception as e:
        print(f"[Anthropic] エラー: {e}", file=sys.stderr)

    _save_seen(state, "anthropic_seen", seen)
    return items


# ──────────────────────────────────────────────
# フォーマット
# ──────────────────────────────────────────────

SOURCE_LABELS = {
    "jp_news": "日本語テックニュース",
    "hf_papers": "AI/ML注目論文",
    "reddit": "Reddit",
    "youtube": "YouTube",
    "github_release": "GitHub リリース",
    "anthropic": "Anthropic",
}


def format_raw(items: list[dict]) -> str:
    """収集結果をテキスト形式で出力"""
    lines = [f"=== テックダイジェスト {datetime.now(JST).strftime('%Y/%m/%d %H:%M')} ===\n"]

    by_source = {}
    for item in items:
        by_source.setdefault(item["source"], []).append(item)

    for source, label in SOURCE_LABELS.items():
        source_items = by_source.get(source, [])
        if not source_items:
            continue
        lines.append(f"\n--- {label} ({len(source_items)}件) ---\n")
        for item in source_items:
            title = item.get("title_ja") or item["title"]
            if item.get("feed_name"):
                title = f"[{item['feed_name']}] {title}"
            if item.get("channel"):
                title = f"[{item['channel']}] {title}"
            if item.get("subreddit"):
                title = f"r/{item['subreddit']}: {title}"
            lines.append(f"  {title}")
            lines.append(f"  {item.get('url', '')}")
            if item.get("score"):
                lines.append(f"  Score: {item['score']}")
            if item.get("upvotes"):
                lines.append(f"  Upvotes: {item['upvotes']}")
            if item.get("summary"):
                lines.append(f"  概要: {item['summary'][:150]}")
            lines.append("")

    lines.append(f"合計: {len(items)}件")
    return "\n".join(lines)


# ──────────────────────────────────────────────
# Claude CLI要約
# ──────────────────────────────────────────────

def _translate_via_anthropic_api(titles: list[str]) -> dict[int, str]:
    """Anthropic Messages APIで英語タイトルを日本語翻訳"""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {}

    lines = [f"{idx}: {t[:120]}" for idx, t in enumerate(titles, 1)]
    prompt = (
        "Translate these English tech article titles to Japanese. "
        "Keep proper nouns and tech terms (3DGS, CUDA, LLM, PyTorch, Claude etc.) as-is. "
        "Output ONLY numbered translations, no explanations.\n\n"
        + "\n".join(lines)
    )

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 2048,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        resp.raise_for_status()
        output = resp.json()["content"][0]["text"]

        translations = {}
        for line in output.strip().split("\n"):
            m = re.match(r"(\d+)\s*[:：．.\)）\-\>→]\s*(.+)", line.strip())
            if m:
                translations[int(m.group(1))] = m.group(2).strip()
        return translations
    except Exception as e:
        print(f"[翻訳API] エラー: {e}", file=sys.stderr)
        return {}


def _translate_via_claude_cli(titles: list[str]) -> dict[int, str]:
    """Claude CLIで英語タイトルを日本語翻訳"""
    claude_cmd = shutil.which("claude")
    if not claude_cmd:
        return {}

    lines = [f"{idx}: {t[:120]}" for idx, t in enumerate(titles, 1)]
    prompt = (
        "Translate these English tech article titles to Japanese. "
        "Keep proper nouns and tech terms (3DGS, CUDA, LLM, PyTorch, Claude etc.) as-is. "
        "Output ONLY numbered translations, no explanations.\n\n"
        + "\n".join(lines)
    )

    try:
        import tempfile
        prompt_file = Path(tempfile.gettempdir()) / "digest_translate_prompt.txt"
        prompt_file.write_text(prompt, encoding="utf-8")

        if sys.platform == "win32":
            shell_cmd = f'chcp 65001 >nul && "{claude_cmd}" -p < "{prompt_file}"'
        else:
            shell_cmd = f'"{claude_cmd}" -p < "{prompt_file}"'

        result = subprocess.run(
            shell_cmd, capture_output=True, timeout=180, shell=True,
        )
        prompt_file.unlink(missing_ok=True)

        if result.returncode != 0 or not result.stdout.strip():
            return {}

        output = result.stdout.decode("utf-8", errors="replace")
        translations = {}
        for line in output.strip().split("\n"):
            m = re.match(r"(\d+)\s*[:：．.\)）\-\>→]\s*(.+)", line.strip())
            if m:
                translations[int(m.group(1))] = m.group(2).strip()
        return translations
    except Exception:
        return {}


def translate_english_items(items: list[dict]):
    """英語アイテムのタイトルを日本語翻訳（API優先、CLI fallback）"""
    english_sources = {"hf_papers", "reddit", "youtube", "github_release", "anthropic"}
    en_items = [
        (i, item) for i, item in enumerate(items)
        if item["source"] in english_sources and item.get("title")
    ]
    if not en_items:
        return

    titles = [item["title"] for _, item in en_items]
    print(f"[翻訳] {len(en_items)}件の英語タイトルを日本語化中...")

    # Anthropic API → Claude CLI の優先順で試行
    translations = _translate_via_anthropic_api(titles)
    if not translations:
        print("[翻訳] API未設定、Claude CLIで翻訳を試行...", file=sys.stderr)
        translations = _translate_via_claude_cli(titles)

    if not translations:
        print("[翻訳] 翻訳手段なし、原文のまま出力", file=sys.stderr)
        return

    applied = 0
    for idx, (i, _) in enumerate(en_items, 1):
        if idx in translations:
            items[i]["title_ja"] = translations[idx]
            applied += 1

    print(f"[翻訳] {applied}/{len(en_items)}件を翻訳完了")


def call_claude_cli(raw_text: str) -> str:
    """claude CLIで要約を生成"""
    prompt = (
        "以下のテック情報ダイジェストを日本語で簡潔に要約してください。\n"
        "各セクションごとに注目ポイントを1-2行で。\n"
        "英語タイトルは日本語に意訳してください。\n"
        "最後に「今日の注目」として最も重要な1件を選んでください。\n"
        "300文字以内で。\n\n"
        f"{raw_text}"
    )
    claude_cmd = shutil.which("claude")
    if not claude_cmd:
        print("[Claude CLI] claude コマンドが見つかりません", file=sys.stderr)
        return ""
    try:
        result = subprocess.run(
            [claude_cmd, "-p", prompt],
            capture_output=True, timeout=120,
        )
        output = result.stdout.decode("utf-8", errors="replace")
        if result.returncode == 0 and output.strip():
            return output.strip()
        print(f"[Claude CLI] 戻り値: {result.returncode}", file=sys.stderr)
        if result.stderr:
            print(f"[Claude CLI] stderr: {result.stderr[:200]}", file=sys.stderr)
    except FileNotFoundError:
        print("[Claude CLI] claude コマンドが見つかりません", file=sys.stderr)
    except subprocess.TimeoutExpired:
        print("[Claude CLI] タイムアウト", file=sys.stderr)
    except Exception as e:
        print(f"[Claude CLI] エラー: {e}", file=sys.stderr)

    return ""


# ──────────────────────────────────────────────
# Discord Webhook
# ──────────────────────────────────────────────

def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def build_discord_embeds(items: list[dict], summary: str) -> list[dict]:
    """Discord Embed形式のペイロードを構築"""
    embeds = []

    by_source = {}
    for item in items:
        by_source.setdefault(item["source"], []).append(item)

    # 日本語ニュース
    jp_items = by_source.get("jp_news", [])
    if jp_items:
        lines = []
        for item in jp_items[:6]:
            name = item.get("feed_name", "")
            lines.append(f"**[{name}] [{item['title'][:70]}]({item['url']})**")
        embeds.append({
            "title": f"🇯🇵 日本語テックニュース ({len(jp_items)}件)",
            "description": _truncate("\n".join(lines), 2048),
            "color": EMBED_COLOR_JP,
        })

    # AI/ML Papers
    hf_items = by_source.get("hf_papers", [])
    if hf_items:
        lines = []
        for item in hf_items[:6]:
            votes = f" 👍{item['upvotes']}" if item.get("upvotes") else ""
            t = (item.get("title_ja") or item["title"])[:70]
            lines.append(f"**[{t}]({item['url']})**{votes}")
        embeds.append({
            "title": f"🧠 AI/ML注目論文 ({len(hf_items)}件)",
            "description": _truncate("\n".join(lines), 2048),
            "color": EMBED_COLOR_AI,
        })

    # Reddit
    reddit_items = by_source.get("reddit", [])
    if reddit_items:
        lines = []
        for item in reddit_items[:6]:
            sr = item.get("subreddit", "")
            score = f" ⬆{item['score']}" if item.get("score") else ""
            t = (item.get("title_ja") or item["title"])[:60]
            lines.append(f"**r/{sr}**: [{t}]({item['url']}){score}")
        embeds.append({
            "title": f"💬 Reddit ({len(reddit_items)}件)",
            "description": _truncate("\n".join(lines), 2048),
            "color": EMBED_COLOR_REDDIT,
        })

    # YouTube
    yt_items = by_source.get("youtube", [])
    if yt_items:
        lines = []
        for item in yt_items[:5]:
            ch = item.get("channel", "")
            t = (item.get("title_ja") or item["title"])[:60]
            lines.append(f"**[{ch}]** [{t}]({item['url']})")
        embeds.append({
            "title": f"▶️ YouTube ({len(yt_items)}件)",
            "description": _truncate("\n".join(lines), 2048),
            "color": EMBED_COLOR_YOUTUBE,
        })

    # GitHub Releases
    gh_items = by_source.get("github_release", [])
    if gh_items:
        lines = []
        for item in gh_items[:5]:
            t = item.get("title_ja") or item["title"]
            line = f"**[{t}]({item['url']})**"
            if item.get("summary"):
                line += f"\n{item['summary'][:80]}"
            lines.append(line)
        embeds.append({
            "title": f"🏷️ GitHub リリース ({len(gh_items)}件)",
            "description": _truncate("\n\n".join(lines), 2048),
            "color": EMBED_COLOR_GITHUB,
        })

    # Anthropic
    anth_items = by_source.get("anthropic", [])
    if anth_items:
        lines = []
        for item in anth_items[:4]:
            t = (item.get("title_ja") or item["title"])[:70]
            lines.append(f"**[{t}]({item['url']})**")
        embeds.append({
            "title": f"🤖 Anthropic ({len(anth_items)}件)",
            "description": _truncate("\n".join(lines), 2048),
            "color": EMBED_COLOR_ANTHROPIC,
        })

    # AI要約
    if summary:
        embeds.append({
            "title": "💡 AI要約",
            "description": _truncate(summary, 2048),
            "color": EMBED_COLOR_SUMMARY,
        })

    # フッター
    if embeds:
        today = datetime.now(JST).strftime("%Y/%m/%d")
        embeds[-1]["footer"] = {
            "text": f"Daily Tech Digest | {today} | powered by Claude Code"
        }

    return embeds


def post_to_discord(items: list[dict], summary: str):
    """Discord Webhookに投稿"""
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("[Discord] DISCORD_WEBHOOK_URL が設定されていません", file=sys.stderr)
        return

    embeds = build_discord_embeds(items, summary)
    if not embeds:
        return

    today = datetime.now(JST).strftime("%Y/%m/%d")
    payload = {
        "username": "Tech Digest Bot",
        "content": f"🔬 **テックダイジェスト {today}** — {len(items)}件の新着情報",
        "embeds": embeds[:10],
    }

    try:
        resp = requests.post(webhook_url, json=payload, timeout=15)
        if resp.status_code == 204:
            print(f"[Discord] 投稿成功 ({len(items)}件)")
        else:
            print(f"[Discord] HTTP {resp.status_code}: {resp.text[:200]}", file=sys.stderr)
    except Exception as e:
        print(f"[Discord] エラー: {e}", file=sys.stderr)


# ──────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="Daily Tech Digest")
    parser.add_argument("--collect-only", action="store_true",
                        help="収集のみ（Discord投稿しない）")
    parser.add_argument("--auto-summarize", action="store_true",
                        help="claude CLIで自動要約")
    parser.add_argument("--dry-run", action="store_true",
                        help="Discord投稿をスキップ")
    parser.add_argument("--no-translate", action="store_true",
                        help="英語→日本語翻訳をスキップ")
    return parser.parse_args()


FETCH_STEPS = [
    ("日本語テックニュース", fetch_jp_news),
    ("HF Daily Papers", fetch_hf_daily_papers),
    ("Reddit", fetch_reddit),
    ("YouTube", fetch_youtube),
    ("GitHub Releases", fetch_github_releases),
    ("Anthropic News", fetch_anthropic_news),
]


def main():
    args = parse_args()
    state = load_state()

    print(f"[Digest] 開始: {datetime.now(JST).strftime('%Y/%m/%d %H:%M')}")
    if state.get("last_run"):
        print(f"[Digest] 前回実行: {state['last_run']}")

    items: list[dict] = []
    total = len(FETCH_STEPS)
    for i, (label, func) in enumerate(FETCH_STEPS, 1):
        print(f"[{i}/{total}] {label}...")
        items += func(state)

    print(f"\n収集完了: {len(items)}件の新着")

    if not items:
        print("新着情報なし")
        save_state(state)
        return

    # 英語タイトルを日本語に翻訳
    if not args.no_translate and not args.collect_only:
        translate_english_items(items)

    raw_text = format_raw(items)
    print(raw_text)

    if args.collect_only:
        save_state(state)
        return

    summary = ""
    if args.auto_summarize:
        print("\n[Claude CLI] 要約生成中...")
        summary = call_claude_cli(raw_text)
        if summary:
            print(f"[Claude CLI] 要約:\n{summary}")

    if args.dry_run:
        print("\n[dry-run] Discord投稿をスキップ")
        embeds = build_discord_embeds(items, summary)
        print(f"[dry-run] Embed数: {len(embeds)}")
    else:
        post_to_discord(items, summary)

    save_state(state)
    print("\n[Digest] 完了")


if __name__ == "__main__":
    main()
