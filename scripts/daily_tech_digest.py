#!/usr/bin/env python3
"""
Daily Tech Digest - 3DGS/CUDA/AI関連の新着情報を収集しDiscordに通知

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
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

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

# arXiv検索クエリ
ARXIV_QUERIES = [
    '"gaussian splatting"',
    '"3D Gaussian"',
    '"radiance field"',
    '"neural rendering"',
    '"gaussian surfels"',
    '"3DGS"',
]
ARXIV_CATEGORIES = ["cs.CV", "cs.GR"]
ARXIV_MAX_RESULTS = 50

# GitHub監視対象リポジトリ
GITHUB_WATCH_REPOS = [
    "nerfstudio-project/gsplat",
    "nerfstudio-project/nerfstudio",
    "graphdeco-inria/gaussian-splatting",
    "nv-tlabs/ppisp",
    "autonomousvision/gaussian-opacity-fields",
    "huggingface/gsplat",
    "pytorch/pytorch",
]

# GitHub Trending検索トピック
GITHUB_TRENDING_TOPICS = [
    "gaussian-splatting",
    "3d-gaussian-splatting",
    "3dgs",
    "nerf",
]

# RSSフィード
RSS_FEEDS = {
    "NVIDIA Developer Blog": "https://developer.nvidia.com/blog/feed",
    "PyTorch Blog": "https://pytorch.org/blog/feed.xml",
}

# RSSキーワードフィルタ（NVIDIAブログ用）
RSS_KEYWORDS = [
    "cuda", "gpu", "gaussian", "3d", "splatting", "nerf",
    "rendering", "blackwell", "rtx", "tensor", "deep learning",
]

# Anthropic News
ANTHROPIC_NEWS_URL = "https://www.anthropic.com/news"

# Discord Embed色
EMBED_COLOR_ARXIV = 0xB31B1B     # arXiv赤
EMBED_COLOR_GITHUB = 0x238636    # GitHub緑
EMBED_COLOR_BLOG = 0x7289DA      # ブログ青
EMBED_COLOR_SUMMARY = 0xF5A623   # 要約オレンジ

# Discord制限
DISCORD_FIELD_VALUE_MAX = 1024
DISCORD_EMBED_TOTAL_MAX = 6000


# ──────────────────────────────────────────────
# State管理
# ──────────────────────────────────────────────

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {
        "last_run": None,
        "arxiv_seen": [],
        "github_releases_seen": [],
        "github_trending_seen": [],
        "rss_seen": [],
        "anthropic_seen": [],
    }


def save_state(state: dict):
    state["last_run"] = datetime.now(JST).isoformat()
    # 各リストの上限を保持（無限増殖防止）
    for key in ["arxiv_seen", "github_releases_seen", "github_trending_seen",
                "rss_seen", "anthropic_seen"]:
        if key in state and len(state[key]) > 500:
            state[key] = state[key][-500:]
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


# ──────────────────────────────────────────────
# arXiv
# ──────────────────────────────────────────────

def fetch_arxiv(state: dict) -> list[dict]:
    """arXiv APIから3DGS/NeRF関連の新着論文を取得"""
    items = []
    seen = set(state.get("arxiv_seen", []))

    cat_query = " OR ".join(f"cat:{c}" for c in ARXIV_CATEGORIES)
    keyword_query = " OR ".join(f'abs:{q}' for q in ARXIV_QUERIES)
    query = f"({cat_query}) AND ({keyword_query})"

    url = "http://export.arxiv.org/api/query"
    params = {
        "search_query": query,
        "start": 0,
        "max_results": ARXIV_MAX_RESULTS,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }

    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)

        cutoff = datetime.now(timezone.utc) - timedelta(days=3)

        for entry in feed.entries:
            arxiv_id = entry.id.split("/abs/")[-1].split("v")[0]
            if arxiv_id in seen:
                continue

            published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            if published < cutoff:
                continue

            authors = ", ".join(a.get("name", "") for a in entry.get("authors", [])[:3])
            if len(entry.get("authors", [])) > 3:
                authors += " et al."

            items.append({
                "source": "arxiv",
                "id": arxiv_id,
                "title": entry.title.replace("\n", " ").strip(),
                "authors": authors,
                "url": f"https://arxiv.org/abs/{arxiv_id}",
                "summary": entry.summary[:300].replace("\n", " ").strip(),
                "date": published.isoformat(),
            })
            seen.add(arxiv_id)

    except Exception as e:
        print(f"[arXiv] エラー: {e}", file=sys.stderr)

    state["arxiv_seen"] = list(seen)
    return items


# ──────────────────────────────────────────────
# GitHub Releases
# ──────────────────────────────────────────────

def _github_headers() -> dict:
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_github_releases(state: dict) -> list[dict]:
    """監視対象リポジトリの新しいリリースを取得"""
    items = []
    seen = set(state.get("github_releases_seen", []))
    headers = _github_headers()
    cutoff = datetime.now(timezone.utc) - timedelta(days=3)

    for repo in GITHUB_WATCH_REPOS:
        try:
            resp = requests.get(
                f"https://api.github.com/repos/{repo}/releases",
                headers=headers,
                params={"per_page": 5},
                timeout=15,
            )
            if resp.status_code == 404:
                continue
            resp.raise_for_status()

            for release in resp.json():
                release_id = f"{repo}/{release['tag_name']}"
                if release_id in seen:
                    continue

                published = datetime.fromisoformat(
                    release["published_at"].replace("Z", "+00:00")
                )
                if published < cutoff:
                    continue

                body = release.get("body", "") or ""
                body_short = body[:200].replace("\n", " ").strip()

                items.append({
                    "source": "github_release",
                    "id": release_id,
                    "title": f"{repo.split('/')[-1]} {release['tag_name']}",
                    "repo": repo,
                    "tag": release["tag_name"],
                    "url": release["html_url"],
                    "summary": body_short,
                    "date": published.isoformat(),
                })
                seen.add(release_id)

            time.sleep(0.5)
        except Exception as e:
            print(f"[GitHub Release] {repo}: {e}", file=sys.stderr)

    state["github_releases_seen"] = list(seen)
    return items


# ──────────────────────────────────────────────
# GitHub Trending (Search API)
# ──────────────────────────────────────────────

def fetch_github_trending(state: dict) -> list[dict]:
    """GitHub Search APIでトレンドリポジトリを検索"""
    items = []
    seen = set(state.get("github_trending_seen", []))
    headers = _github_headers()

    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")

    for topic in GITHUB_TRENDING_TOPICS:
        query = f"topic:{topic} pushed:>{week_ago} stars:>5"
        try:
            resp = requests.get(
                "https://api.github.com/search/repositories",
                headers=headers,
                params={"q": query, "sort": "stars", "order": "desc", "per_page": 10},
                timeout=15,
            )
            resp.raise_for_status()

            for repo in resp.json().get("items", []):
                repo_id = repo["full_name"]
                if repo_id in seen:
                    continue

                items.append({
                    "source": "github_trending",
                    "id": repo_id,
                    "title": repo["full_name"],
                    "url": repo["html_url"],
                    "summary": (repo.get("description") or "")[:200],
                    "stars": repo["stargazers_count"],
                    "date": repo.get("pushed_at", ""),
                })
                seen.add(repo_id)

            time.sleep(1)
        except Exception as e:
            print(f"[GitHub Trending] {topic}: {e}", file=sys.stderr)

    state["github_trending_seen"] = list(seen)
    return items


# ──────────────────────────────────────────────
# RSS Feeds
# ──────────────────────────────────────────────

def fetch_rss_feeds(state: dict) -> list[dict]:
    """NVIDIA/PyTorchブログのRSSフィードを取得"""
    items = []
    seen = set(state.get("rss_seen", []))
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    for name, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:20]:
                entry_id = entry.get("link", entry.get("id", ""))
                if not entry_id or entry_id in seen:
                    continue

                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                    if published < cutoff:
                        continue
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    updated = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
                    if updated < cutoff:
                        continue

                title = entry.get("title", "").strip()
                summary = entry.get("summary", "")[:200].strip()

                # HTMLタグ除去
                title = re.sub(r"<[^>]+>", "", title)
                summary = re.sub(r"<[^>]+>", "", summary).strip()

                # NVIDIAブログはキーワードフィルタ
                if "nvidia" in name.lower():
                    text_lower = (title + " " + summary).lower()
                    if not any(kw in text_lower for kw in RSS_KEYWORDS):
                        continue

                items.append({
                    "source": "rss",
                    "id": entry_id,
                    "feed_name": name,
                    "title": title,
                    "url": entry_id,
                    "summary": summary,
                    "date": entry.get("published", entry.get("updated", "")),
                })
                seen.add(entry_id)

        except Exception as e:
            print(f"[RSS] {name}: {e}", file=sys.stderr)

    state["rss_seen"] = list(seen)
    return items


# ──────────────────────────────────────────────
# Anthropic News
# ──────────────────────────────────────────────

def fetch_anthropic_news(state: dict) -> list[dict]:
    """Anthropicニュースページから新着記事を取得（簡易HTML解析）"""
    items = []
    seen = set(state.get("anthropic_seen", []))

    try:
        resp = requests.get(ANTHROPIC_NEWS_URL, timeout=15, headers={
            "User-Agent": "TechDigestBot/1.0"
        })
        resp.raise_for_status()
        html = resp.text

        # <a href="/news/..." のリンクを抽出
        pattern = r'<a[^>]*href="(/news/[^"]+)"[^>]*>(.*?)</a>'
        matches = re.findall(pattern, html, re.DOTALL)

        for path, title_html in matches[:20]:
            url = f"https://www.anthropic.com{path}"
            if url in seen:
                continue

            # HTMLタグ・HTMLエンティティ除去
            raw_title = re.sub(r"<[^>]+>", "", title_html).strip()
            raw_title = raw_title.replace("&#x27;", "'").replace("&amp;", "&")
            if not raw_title or len(raw_title) < 5:
                continue

            # Anthropicページは日付・カテゴリ・タイトル・説明が混在
            # 複数回パスで除去
            cleaned = raw_title
            _labels = ["Announcements", "Product", "Policy", "Research",
                       "Case Study", "Company"]
            _date_re = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}"
            for _ in range(3):
                cleaned = re.sub(_date_re, "", cleaned).strip()
                for label in _labels:
                    if cleaned.startswith(label):
                        cleaned = cleaned[len(label):].strip()
                    # 末尾にも出現する場合
                    if cleaned.endswith(label):
                        cleaned = cleaned[:-len(label)].strip()

            # 説明文が連結されている場合、最初の文（〜150文字）を取得
            # 大文字から始まる長い文が2つ以上連結している場合を検出
            if len(cleaned) > 100:
                # タイトルの切れ目を推定（小文字/数字の後に大文字 → 連結点）
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
                "summary": "",
                "date": "",
            })
            seen.add(url)

    except Exception as e:
        print(f"[Anthropic] エラー: {e}", file=sys.stderr)

    state["anthropic_seen"] = list(seen)
    return items


# ──────────────────────────────────────────────
# フォーマット
# ──────────────────────────────────────────────

def format_raw(items: list[dict]) -> str:
    """収集結果をテキスト形式で出力"""
    lines = [f"=== テックダイジェスト {datetime.now(JST).strftime('%Y/%m/%d %H:%M')} ===\n"]

    by_source = {}
    for item in items:
        by_source.setdefault(item["source"], []).append(item)

    source_labels = {
        "arxiv": "arXiv 新着論文",
        "github_release": "GitHub リリース",
        "github_trending": "GitHub トレンド",
        "rss": "ブログ・ニュース",
        "anthropic": "Anthropic ニュース",
    }

    for source, label in source_labels.items():
        source_items = by_source.get(source, [])
        if not source_items:
            continue
        lines.append(f"\n--- {label} ({len(source_items)}件) ---\n")
        for item in source_items:
            lines.append(f"  [{item['title']}]")
            lines.append(f"  {item['url']}")
            if item.get("authors"):
                lines.append(f"  著者: {item['authors']}")
            if item.get("stars"):
                lines.append(f"  Stars: {item['stars']}")
            if item.get("summary"):
                lines.append(f"  概要: {item['summary'][:150]}")
            lines.append("")

    lines.append(f"合計: {len(items)}件")
    return "\n".join(lines)


# ──────────────────────────────────────────────
# Claude CLI要約
# ──────────────────────────────────────────────

def call_claude_cli(raw_text: str) -> str:
    """claude CLIで要約を生成"""
    prompt = (
        "以下のテック情報ダイジェストを日本語で簡潔に要約してください。\n"
        "各セクション（arXiv、GitHub、ブログ）ごとに注目ポイントを1-2行で。\n"
        "最後に「今日の注目」として最も重要な1件を選んでください。\n"
        "200文字以内で。\n\n"
        f"{raw_text}"
    )
    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=120,
            encoding="utf-8",
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
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
    today = datetime.now(JST).strftime("%Y/%m/%d")

    by_source = {}
    for item in items:
        by_source.setdefault(item["source"], []).append(item)

    # arXiv
    arxiv_items = by_source.get("arxiv", [])
    if arxiv_items:
        lines = []
        for item in arxiv_items[:8]:
            line = f"**[{item['title'][:80]}]({item['url']})**"
            if item.get("authors"):
                line += f"\n{item['authors']}"
            lines.append(line)
        embeds.append({
            "title": f"📄 arXiv 新着論文 ({len(arxiv_items)}件)",
            "description": _truncate("\n\n".join(lines), 2048),
            "color": EMBED_COLOR_ARXIV,
        })

    # GitHub Releases
    gh_releases = by_source.get("github_release", [])
    if gh_releases:
        lines = []
        for item in gh_releases[:5]:
            line = f"**[{item['title']}]({item['url']})**"
            if item.get("summary"):
                line += f"\n{item['summary'][:100]}"
            lines.append(line)
        embeds.append({
            "title": f"🏷️ GitHub リリース ({len(gh_releases)}件)",
            "description": _truncate("\n\n".join(lines), 2048),
            "color": EMBED_COLOR_GITHUB,
        })

    # GitHub Trending
    gh_trending = by_source.get("github_trending", [])
    if gh_trending:
        lines = []
        for item in gh_trending[:5]:
            stars = f" ⭐{item['stars']}" if item.get("stars") else ""
            line = f"**[{item['title']}]({item['url']})**{stars}"
            if item.get("summary"):
                line += f"\n{item['summary'][:100]}"
            lines.append(line)
        embeds.append({
            "title": f"🔥 GitHub トレンド ({len(gh_trending)}件)",
            "description": _truncate("\n\n".join(lines), 2048),
            "color": EMBED_COLOR_GITHUB,
        })

    # RSS + Anthropic
    blog_items = by_source.get("rss", []) + by_source.get("anthropic", [])
    if blog_items:
        lines = []
        for item in blog_items[:5]:
            prefix = item.get("feed_name", "Anthropic")
            line = f"**[{prefix}: {item['title'][:60]}]({item['url']})**"
            lines.append(line)
        embeds.append({
            "title": f"📰 ブログ・ニュース ({len(blog_items)}件)",
            "description": _truncate("\n\n".join(lines), 2048),
            "color": EMBED_COLOR_BLOG,
        })

    # AI要約
    if summary:
        embeds.append({
            "title": "💡 AI要約",
            "description": _truncate(summary, 2048),
            "color": EMBED_COLOR_SUMMARY,
        })

    # フッター（最後のembedに付与）
    if embeds:
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
        "embeds": embeds[:10],  # Discord上限: 10 embeds
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
    return parser.parse_args()


def main():
    args = parse_args()
    state = load_state()

    print(f"[Digest] 開始: {datetime.now(JST).strftime('%Y/%m/%d %H:%M')}")
    if state.get("last_run"):
        print(f"[Digest] 前回実行: {state['last_run']}")

    # 1. 各ソースから新着を収集
    items: list[dict] = []

    print("[1/5] arXiv...")
    items += fetch_arxiv(state)

    print("[2/5] GitHub Releases...")
    items += fetch_github_releases(state)

    print("[3/5] GitHub Trending...")
    items += fetch_github_trending(state)

    print("[4/5] RSS Feeds...")
    items += fetch_rss_feeds(state)

    print("[5/5] Anthropic News...")
    items += fetch_anthropic_news(state)

    print(f"\n収集完了: {len(items)}件の新着")

    if not items:
        print("新着情報なし")
        save_state(state)
        return

    # 2. テキスト出力
    raw_text = format_raw(items)
    print(raw_text)

    if args.collect_only:
        save_state(state)
        return

    # 3. 要約
    summary = ""
    if args.auto_summarize:
        print("\n[Claude CLI] 要約生成中...")
        summary = call_claude_cli(raw_text)
        if summary:
            print(f"[Claude CLI] 要約:\n{summary}")

    # 4. Discord投稿
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
