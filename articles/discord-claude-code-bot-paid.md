---
title: "【有料】Discord × Claude Code Bot 完全実装ガイド"
emoji: "🔧"
type: "tech"
topics: ["Discord", "Claude", "Python", "Bot", "自動化"]
published: true
published_at: "2026-01-10 21:00"
price: 980
---

# この記事について

本記事は「[スマホからClaude Codeを操作する：Discord Bot構築ガイド](https://zenn.dev/amabito/articles/discord-claude-code-bot)」の完全実装版です。

**この記事で得られるもの:**
- 完全なPython Botコード（500行以上）
- 設定ファイルテンプレート
- 起動スクリプト
- トラブルシューティングガイド
- セキュリティチェックリスト

**対象読者:**
- 無料記事を読んで実装したい人
- Python中級者以上
- WSL2/Linux環境がある人

---

# 事前準備

## 必要なもの

| 項目 | 詳細 |
|------|------|
| OS | Windows 11 + WSL2 Ubuntu |
| Python | 3.10以上 |
| Claude Code | インストール済み |
| Discord | 開発者アカウント |

## Discord Developer Portal設定

### 1. Bot作成

```
1. https://discord.com/developers/applications にアクセス
2. "New Application" → 名前: "Claude Code Bot"
3. Bot タブ → "Add Bot"
```

### 2. Bot設定

| 設定項目 | 値 | 理由 |
|---------|---|------|
| PUBLIC BOT | OFF | 自分専用 |
| MESSAGE CONTENT INTENT | **ON** | メッセージ内容取得に必須 |

### 3. Token取得

```
Bot タブ → "Reset Token" → コピー
※1度しか表示されない。必ず控える。
```

### 4. 招待URL生成

```
OAuth2 → URL Generator:
  Scopes: bot
  Permissions:
    ✓ Send Messages
    ✓ Send Messages in Threads
    ✓ Create Public Threads
    ✓ Read Message History
    ✓ Add Reactions
    ✓ Attach Files
```

生成されたURLでBotをサーバーに招待。

### 5. ID取得

```
Discordの開発者モードをON:
  ユーザー設定 → 詳細設定 → 開発者モード

チャンネルID:
  #claude-code を右クリック → "IDをコピー"

ユーザーID:
  自分のアイコンを右クリック → "IDをコピー"
```

---

# 完全実装

## ディレクトリ構成

```
~/claude-discord-bot/
├── discord_claude_bot.py   # メインBot（以下に記載）
├── config.yaml             # 実行設定
├── .env                    # 認証情報
├── .gitignore
├── requirements.txt
├── start_discord_bot.sh    # 起動スクリプト
└── logs/                   # ログディレクトリ
    └── sessions/           # セッション永続化
```

## 依存パッケージ

```txt:requirements.txt
discord.py==2.3.2
python-dotenv==1.0.1
aiofiles==23.2.1
PyYAML==6.0.1
```

## 環境変数

```bash:.env
# Discord Bot
DISCORD_TOKEN=your_bot_token_here

# セキュリティ: カンマ区切りで複数指定可
DISCORD_ALLOWED_USERS=123456789012345678
DISCORD_ALLOWED_CHANNELS=987654321098765432

# Claude Code
CLAUDE_PATH=/home/username/.local/bin/claude
WORKSPACE=/home/username/projects

# タイムアウト設定（秒）
CLAUDE_TIMEOUT=600
MAX_TURNS=15
```

```bash
# パーミッション設定（重要）
chmod 600 .env
```

## 設定ファイル

```yaml:config.yaml
claude:
  default_allowed_tools:
    - "View"
    - "Bash(git status,git log,git diff,ls,cat,head,tail,grep,find,wc,tree)"
  extended_tools:
    write:
      - "Edit"
      - "Write"
    execute:
      - "Bash"

discord:
  max_message_length: 1900
  thread_auto_archive_minutes: 1440
  message_delay_seconds: 0.5
  thread_name_max_length: 40

logging:
  max_log_files: 30
  log_format: "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
```

## メインBot実装

```python:discord_claude_bot.py
#!/usr/bin/env python3
"""
Discord連携 Claude Code Bot

機能:
- /cc <指示> : Claude Codeに指示を送信
- /cc continue : 前回の会話を継続
- /cc reset : セッションをリセット
- /cc cancel : 実行中のタスクをキャンセル
- /cc status : Bot状態確認
- /cc help : ヘルプ表示
"""

import os
import sys
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field, asdict
import json
import re

import discord
from discord.ext import commands
import yaml
from dotenv import load_dotenv

# =============================================================================
# 定数
# =============================================================================

THREAD_NAME_MAX_LENGTH = 40

# =============================================================================
# 設定読み込み
# =============================================================================

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")


def get_required_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise ValueError(f"環境変数 {key} が設定されていません")
    return value


DISCORD_TOKEN = get_required_env("DISCORD_TOKEN")
ALLOWED_USERS = {
    int(uid.strip())
    for uid in os.getenv("DISCORD_ALLOWED_USERS", "").split(",")
    if uid.strip()
}
ALLOWED_CHANNELS = {
    int(cid.strip())
    for cid in os.getenv("DISCORD_ALLOWED_CHANNELS", "").split(",")
    if cid.strip()
}
CLAUDE_PATH = os.getenv("CLAUDE_PATH", "claude")
WORKSPACE = Path(os.getenv("WORKSPACE", Path.home() / "projects"))
CLAUDE_TIMEOUT = int(os.getenv("CLAUDE_TIMEOUT", "600"))
MAX_TURNS = int(os.getenv("MAX_TURNS", "15"))

with open(BASE_DIR / "config.yaml") as f:
    CONFIG = yaml.safe_load(f)

# =============================================================================
# ログ設定
# =============================================================================

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format=CONFIG["logging"]["log_format"],
    handlers=[
        logging.FileHandler(
            LOG_DIR / f"bot_{datetime.now():%Y%m%d}.log",
            encoding="utf-8"
        ),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("claude-bot")

# =============================================================================
# セッション管理
# =============================================================================

@dataclass
class Session:
    """Claude Codeセッション"""
    session_id: str
    thread_id: int
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_activity: str = field(default_factory=lambda: datetime.now().isoformat())
    message_count: int = 0

    def touch(self):
        self.last_activity = datetime.now().isoformat()
        self.message_count += 1


class SessionManager:
    """セッション管理クラス（永続化対応）"""

    def __init__(self):
        self.sessions: dict[int, Session] = {}
        self.sessions_dir = LOG_DIR / "sessions"
        self.sessions_dir.mkdir(exist_ok=True)
        self.sessions_file = self.sessions_dir / "active_sessions.json"
        self._load_sessions()

    def _load_sessions(self):
        """保存されたセッションを復元"""
        if self.sessions_file.exists():
            try:
                with open(self.sessions_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for thread_id_str, session_data in data.items():
                    thread_id = int(thread_id_str)
                    self.sessions[thread_id] = Session(**session_data)
                logger.info(f"Loaded {len(self.sessions)} sessions")
            except Exception as e:
                logger.warning(f"Failed to load sessions: {e}")

    def _save_sessions(self):
        """セッションを永続化"""
        try:
            data = {str(k): asdict(v) for k, v in self.sessions.items()}
            with open(self.sessions_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save sessions: {e}")

    def get_or_create(self, thread_id: int) -> Session:
        if thread_id not in self.sessions:
            session_id = f"discord-{thread_id}-{datetime.now():%Y%m%d%H%M%S}"
            self.sessions[thread_id] = Session(
                session_id=session_id,
                thread_id=thread_id
            )
            logger.info(f"New session created: {session_id}")
            self._save_sessions()
        return self.sessions[thread_id]

    def get(self, thread_id: int) -> Optional[Session]:
        return self.sessions.get(thread_id)

    def clear(self, thread_id: int) -> bool:
        if thread_id in self.sessions:
            session = self.sessions.pop(thread_id)
            logger.info(f"Session cleared: {session.session_id}")
            self._save_sessions()
            return True
        return False

    def save_interaction(self, session: Session, prompt: str, result: str):
        """対話ログを保存"""
        log_file = self.sessions_dir / f"{session.session_id}.jsonl"
        entry = {
            "timestamp": datetime.now().isoformat(),
            "message_count": session.message_count,
            "prompt": prompt,
            "result_length": len(result),
            "result_preview": result[:500] if len(result) > 500 else result
        }
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._save_sessions()

# =============================================================================
# Claude Code実行
# =============================================================================

class ClaudeExecutor:
    """Claude Code CLI実行クラス"""

    def __init__(self):
        self.running_tasks: dict[int, asyncio.Task] = {}
        self.default_tools = ",".join(CONFIG["claude"]["default_allowed_tools"])

    async def execute(
        self,
        prompt: str,
        session_id: str,
        continue_session: bool = False,
        timeout: int = CLAUDE_TIMEOUT
    ) -> tuple[str, bool]:
        """
        Claude Code CLIを実行

        Returns:
            tuple[str, bool]: (出力結果, 成功フラグ)
        """
        cmd = [CLAUDE_PATH]

        if continue_session:
            cmd.extend(["--continue"])

        cmd.extend(["-p", prompt])
        cmd.extend([
            "--max-turns", str(MAX_TURNS),
            "--allowedTools", self.default_tools
        ])

        logger.info(f"Executing Claude: session={session_id}, prompt_len={len(prompt)}")
        logger.debug(f"Command: {' '.join(cmd)}")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(WORKSPACE),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "CLAUDE_SESSION_ID": session_id}
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )

            result = stdout.decode("utf-8", errors="replace")

            if process.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace")
                logger.error(f"Claude error: {error_msg}")
                if error_msg:
                    result += f"\n\n⚠️ **stderr:**\n```\n{error_msg[:500]}\n```"
                return result, False

            return result, True

        except asyncio.TimeoutError:
            logger.warning(f"Timeout: {session_id}")
            return f"⏰ タイムアウト（{timeout}秒）\n\nタスクが時間内に完了しませんでした。", False
        except FileNotFoundError:
            logger.error(f"Claude CLI not found: {CLAUDE_PATH}")
            return f"❌ Claude CLI が見つかりません: `{CLAUDE_PATH}`", False
        except Exception as e:
            logger.exception(f"Execution error: {e}")
            return f"❌ 実行エラー: {str(e)}", False

    def register_task(self, thread_id: int, task: asyncio.Task):
        if thread_id in self.running_tasks:
            self.running_tasks[thread_id].cancel()
        self.running_tasks[thread_id] = task

    def cancel_task(self, thread_id: int) -> bool:
        if thread_id in self.running_tasks:
            self.running_tasks[thread_id].cancel()
            del self.running_tasks[thread_id]
            return True
        return False

    def cleanup_task(self, thread_id: int):
        self.running_tasks.pop(thread_id, None)

# =============================================================================
# メッセージ送信ユーティリティ
# =============================================================================

async def send_long_message(
    channel: discord.abc.Messageable,
    content: str,
    max_length: int = 1900,
    delay: float = 0.5
):
    """長文メッセージを適切に分割して送信"""
    if not content.strip():
        await channel.send("(出力なし)")
        return

    chunks = []
    chunk_lines: list[str] = []
    chunk_length = 0
    in_code_block = False
    code_lang = ""

    lines = content.split("\n")

    for line in lines:
        # コードブロックの開始/終了を検出
        code_match = re.match(r'^```(\w*)', line)
        if code_match:
            if not in_code_block:
                in_code_block = True
                code_lang = code_match.group(1)
            else:
                in_code_block = False
                code_lang = ""

        line_length = len(line) + 1  # +1 for newline

        if chunk_length + line_length > max_length:
            # コードブロック内なら閉じる
            if in_code_block:
                chunk_lines.append("```")

            chunks.append("\n".join(chunk_lines))
            chunk_lines = []
            chunk_length = 0

            # 新しいチャンクでコードブロック再開
            if in_code_block:
                chunk_lines.append(f"```{code_lang}")
                chunk_length = len(f"```{code_lang}") + 1

        chunk_lines.append(line)
        chunk_length += line_length

    # 最後のチャンク
    if chunk_lines:
        chunks.append("\n".join(chunk_lines))

    # 送信（レート制限対策付き）
    for i, chunk in enumerate(chunks):
        if i > 0:
            await asyncio.sleep(delay)
        try:
            await channel.send(chunk)
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = getattr(e, 'retry_after', 5.0)
                logger.warning(f"Rate limited, waiting {retry_after}s")
                await asyncio.sleep(retry_after)
                await channel.send(chunk)
            else:
                raise

# =============================================================================
# Discord Bot
# =============================================================================

class ClaudeBot(commands.Bot):
    """Claude Code Discord Bot"""

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(
            command_prefix="/cc ",
            intents=intents,
            help_command=None
        )

        self.session_manager = SessionManager()
        self.executor = ClaudeExecutor()
        self.start_time = datetime.now()

    async def setup_hook(self):
        """Bot起動時の初期化"""
        logger.info("Bot initializing...")

    async def on_ready(self):
        """Bot準備完了時"""
        logger.info(f"Bot ready: {self.user} (ID: {self.user.id})")
        logger.info(f"Allowed users: {ALLOWED_USERS}")
        logger.info(f"Allowed channels: {ALLOWED_CHANNELS}")

        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name="/cc help"
            )
        )

    async def on_disconnect(self):
        """切断時"""
        logger.warning("Bot disconnected")

    async def on_resumed(self):
        """再接続時"""
        logger.info("Bot resumed")

    # =========================================================================
    # 認証・認可
    # =========================================================================

    def is_authorized(self, message: discord.Message) -> tuple[bool, str]:
        """認証チェック"""
        if message.author.bot:
            return False, ""

        if message.author.id not in ALLOWED_USERS:
            logger.warning(f"Unauthorized user: {message.author} ({message.author.id})")
            return False, "unauthorized_user"

        channel_id = (
            message.channel.parent_id
            if isinstance(message.channel, discord.Thread)
            else message.channel.id
        )

        if channel_id not in ALLOWED_CHANNELS:
            logger.warning(f"Unauthorized channel: {channel_id}")
            return False, "unauthorized_channel"

        return True, ""

    # =========================================================================
    # メッセージハンドリング
    # =========================================================================

    async def on_message(self, message: discord.Message):
        """メッセージ受信時"""
        if not message.content.startswith("/cc"):
            return

        authorized, error = self.is_authorized(message)
        if not authorized:
            if error == "unauthorized_user":
                await message.add_reaction("🚫")
            return

        content = message.content[3:].strip()

        if not content:
            await message.reply(
                "💡 使い方: `/cc <指示>` または `/cc help`",
                mention_author=False
            )
            return

        cmd_lower = content.lower().split()[0]

        if cmd_lower == "help":
            await self.cmd_help(message)
        elif cmd_lower == "status":
            await self.cmd_status(message)
        elif cmd_lower == "reset":
            await self.cmd_reset(message)
        elif cmd_lower == "cancel":
            await self.cmd_cancel(message)
        elif cmd_lower == "continue":
            await self.cmd_continue(message, content[8:].strip())
        else:
            await self.cmd_execute(message, content)

    # =========================================================================
    # コマンド実装
    # =========================================================================

    async def cmd_help(self, message: discord.Message):
        """ヘルプ表示"""
        help_text = """
## Claude Code Bot

### 基本コマンド
- `/cc <指示>` - Claude Codeに指示を送信
- `/cc continue <指示>` - 前回の会話を継続して指示
- `/cc reset` - 会話セッションをリセット
- `/cc cancel` - 実行中のタスクをキャンセル
- `/cc status` - Bot状態を確認
- `/cc help` - このヘルプを表示

### 使用例
```
/cc このプロジェクトの構造を説明して
/cc continue テストも実行して
/cc reset
```

### Tips
- スレッド内では会話が継続します
- 新しいトピックは新規メッセージで開始してください
- 長い処理は `/cc cancel` で中断できます
        """
        await message.reply(help_text, mention_author=False)

    async def cmd_status(self, message: discord.Message):
        """ステータス表示"""
        uptime = datetime.now() - self.start_time
        hours, remainder = divmod(int(uptime.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)

        session = self.session_manager.get(
            message.channel.id if isinstance(message.channel, discord.Thread)
            else 0
        )

        status_text = f"""
**Bot Status**
- Uptime: {hours}h {minutes}m {seconds}s
- Active sessions: {len(self.session_manager.sessions)}
- Running tasks: {len(self.executor.running_tasks)}
- Workspace: `{WORKSPACE}`
- Current session: {session.session_id if session else "None"}
        """
        await message.reply(status_text, mention_author=False)

    async def cmd_reset(self, message: discord.Message):
        """セッションリセット"""
        thread_id = (
            message.channel.id
            if isinstance(message.channel, discord.Thread)
            else 0
        )

        if self.session_manager.clear(thread_id):
            await message.reply("✅ セッションをリセットしました", mention_author=False)
        else:
            await message.reply("ℹ️ アクティブなセッションがありません", mention_author=False)

    async def cmd_cancel(self, message: discord.Message):
        """タスクキャンセル"""
        thread_id = (
            message.channel.id
            if isinstance(message.channel, discord.Thread)
            else 0
        )

        if self.executor.cancel_task(thread_id):
            await message.reply("🛑 タスクをキャンセルしました", mention_author=False)
        else:
            await message.reply("ℹ️ 実行中のタスクがありません", mention_author=False)

    async def cmd_continue(self, message: discord.Message, prompt: str):
        """セッション継続実行"""
        if not prompt:
            await message.reply(
                "💡 使い方: `/cc continue <続きの指示>`",
                mention_author=False
            )
            return

        await self.cmd_execute(message, prompt, continue_session=True)

    async def cmd_execute(
        self,
        message: discord.Message,
        prompt: str,
        continue_session: bool = False
    ):
        """Claude Code実行"""
        if isinstance(message.channel, discord.Thread):
            thread = message.channel
        else:
            thread_name_limit = CONFIG["discord"].get("thread_name_max_length", THREAD_NAME_MAX_LENGTH)
            thread_name = f"Claude: {prompt[:thread_name_limit]}{'...' if len(prompt) > thread_name_limit else ''}"
            try:
                thread = await message.create_thread(
                    name=thread_name,
                    auto_archive_duration=CONFIG["discord"]["thread_auto_archive_minutes"]
                )
            except discord.HTTPException as e:
                logger.error(f"Failed to create thread: {e}")
                await message.reply("❌ スレッド作成に失敗しました", mention_author=False)
                return

        session = self.session_manager.get_or_create(thread.id)
        session.touch()

        status_msg = await thread.send("⏳ 実行中...")

        try:
            task = asyncio.create_task(
                self.executor.execute(
                    prompt=prompt,
                    session_id=session.session_id,
                    continue_session=continue_session
                )
            )
            self.executor.register_task(thread.id, task)

            result, success = await task

            await status_msg.delete()

            if success:
                await send_long_message(
                    thread,
                    result,
                    max_length=CONFIG["discord"]["max_message_length"],
                    delay=CONFIG["discord"]["message_delay_seconds"]
                )
            else:
                await thread.send(result)

            self.session_manager.save_interaction(session, prompt, result)

        except asyncio.CancelledError:
            await status_msg.edit(content="🛑 キャンセルされました")
        except Exception as e:
            logger.exception(f"Command execution error: {e}")
            await status_msg.edit(content=f"❌ エラー: {str(e)[:100]}")
        finally:
            self.executor.cleanup_task(thread.id)

    async def healthcheck(self) -> dict:
        """ヘルスチェック"""
        return {
            "status": "ok",
            "uptime_seconds": int((datetime.now() - self.start_time).total_seconds()),
            "active_sessions": len(self.session_manager.sessions),
            "running_tasks": len(self.executor.running_tasks)
        }

# =============================================================================
# メイン
# =============================================================================

def main():
    """エントリーポイント"""
    bot = ClaudeBot()

    logger.info("Starting bot...")
    try:
        bot.run(DISCORD_TOKEN, log_handler=None)
    except KeyboardInterrupt:
        logger.info("Interrupted")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

## 起動スクリプト

```bash:start_discord_bot.sh
#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

source venv/bin/activate

if pgrep -f "discord_claude_bot.py" > /dev/null; then
    echo "Bot is already running"
    exit 0
fi

echo "Starting Discord Claude Bot..."
python discord_claude_bot.py
```

```bash
chmod +x start_discord_bot.sh
```

## .gitignore

```txt:.gitignore
.env
logs/
venv/
__pycache__/
*.pyc
*.pyo
.DS_Store
```

---

# インストール手順

```bash
# 1. ディレクトリ作成
mkdir -p ~/claude-discord-bot
cd ~/claude-discord-bot

# 2. 上記ファイルをすべて作成

# 3. Python環境
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 4. .env編集
nano .env
# DISCORD_TOKEN, ALLOWED_USERS, ALLOWED_CHANNELS を設定

# 5. 起動
./start_discord_bot.sh
```

---

# トラブルシューティング

## Bot がオンラインにならない

```bash
# Token確認
grep DISCORD_TOKEN .env

# 手動実行でエラー確認
python discord_claude_bot.py
```

## コマンドに反応しない

```bash
# Developer PortalでMESSAGE CONTENT INTENTがONか確認
# ALLOWED_USERS, ALLOWED_CHANNELSの値を確認
grep ALLOWED .env
```

## Claude Codeが実行されない

```bash
# パス確認
which claude
cat .env | grep CLAUDE_PATH

# 直接実行テスト
claude -p "hello" --max-turns 1
```

## 文字化け

```bash
# ロケール確認
locale
# 必要なら設定
export LANG=en_US.UTF-8
```

---

# セキュリティチェックリスト

## 公開前に確認

- [ ] `.env` が `.gitignore` に含まれている
- [ ] `.env` のパーミッションが `600`
- [ ] `ALLOWED_USERS` に自分のIDのみ設定
- [ ] `ALLOWED_CHANNELS` に専用チャンネルのみ設定
- [ ] `PUBLIC BOT` が OFF
- [ ] ログに Token が出力されない
- [ ] ファイル書き込みツールが禁止されている

## 運用時

- [ ] 定期的にログを確認
- [ ] 不審なアクセスがないか監視
- [ ] Token を定期的にローテーション

---

# 拡張アイデア

## 1. Webhook通知

```python
# 長時間タスク完了時にスマホへプッシュ通知
async def send_webhook(message: str):
    async with aiohttp.ClientSession() as session:
        await session.post(WEBHOOK_URL, json={"content": message})
```

## 2. 複数ワークスペース対応

```python
# /cc workspace <name> で切り替え
WORKSPACES = {
    "main": Path("/home/user/projects/main"),
    "side": Path("/home/user/projects/side"),
}
```

## 3. 権限レベル

```python
# ユーザーごとに許可ツールを変更
USER_PERMISSIONS = {
    123456789: ["View", "Bash", "Edit"],  # フルアクセス
    987654321: ["View"],  # 読み取りのみ
}
```

---

# まとめ

この記事では、Discord × Claude Code Botの完全な実装を提供しました。

| 項目 | 内容 |
|------|------|
| コード量 | 約500行 |
| 機能 | 6コマンド + セッション管理 |
| セキュリティ | 4層認証 + 権限最小化 |
| 永続化 | JSON + JSONL |

**不明点があればコメントでお知らせください。**

---

# 関連記事

- [スマホからClaude Codeを操作する（無料版）](https://zenn.dev/amabito/articles/discord-claude-code-bot)
- [Claude Codeで開発効率3倍](https://zenn.dev/amabito/articles/claude-code-productivity)
- [【有料】Claude Code完全活用ガイド](https://zenn.dev/amabito/articles/claude-code-productivity-paid)
