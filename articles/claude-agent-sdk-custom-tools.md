---
title: "Claude Agent SDKで自律開発エージェントを作る実践ガイド"
emoji: "🤖"
type: "tech"
topics: ["Claude", "AgentSDK", "MCP", "Python", "自動化"]
published: true
published_at: "2026-01-04 21:00"
---

# 結論から言う

**Claude Agent SDK（Python/TypeScript）を使えば、カスタムツール・MCP接続・サブエージェント・Hookを組み合わせて、自律的に動く開発エージェントを構築できる。** コード数十行から始められ、既存のCI/CDやモニタリングに統合可能。

**対象読者:**
- Claude Codeを使っていて、さらに自動化したい人
- AIエージェントの自作に興味がある人
- MCP（Model Context Protocol）を活用したい人

**この記事で得られること:**
- Claude Agent SDKの全体像（Python/TypeScript）
- カスタムツールとMCPサーバーの実装方法
- サブエージェント、Hook、認証の設定
- 実践例：3DGS学習パイプラインのモニタリングエージェント

---

## Claude Agent SDKの全体像

Claude Agent SDKは、Claudeにローカルコンピュータへのアクセスを与えるライブラリだ。テキスト応答だけでなく、ツールを使って環境と対話するエージェントを構築できる。

### 構成要素

```
Claude Agent SDK:
├── ClaudeSDKClient     → エージェントのエントリポイント
├── Custom Tools        → インプロセスMCPサーバーで定義
├── MCP Servers         → 外部ツール接続（DB、Slack、GitHub等）
├── Subagents           → 専門タスクに特化したサブエージェント
├── Hooks               → 特定タイミングで実行される処理
└── Permissions         → ツール単位のアクセス制御
```

### Python / TypeScriptの選択

| 項目 | Python | TypeScript |
|------|--------|------------|
| パッケージ | `claude-agent-sdk` | `@anthropic-ai/claude-agent-sdk` |
| ツール定義 | `@tool`デコレータ | `tool()`関数 + Zodスキーマ |
| MCP接続 | 同一プロセス内 | 同一プロセス内 |
| 型安全性 | 型ヒント | Zod |

---

## カスタムツールの実装

カスタムツールは**インプロセスMCPサーバー**として実装する。別プロセスを起動する必要がなく、パフォーマンスとデプロイメントの両面で優れている。

### Python実装

```python
from claude_agent_sdk import ClaudeSDKClient, tool, create_sdk_mcp_server

# ツール定義
@tool(name="check_gpu_usage", description="GPU使用率とVRAMを取得する")
def check_gpu_usage() -> dict:
    """nvidia-smiの情報をパースして返す"""
    import subprocess
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total",
         "--format=csv,noheader,nounits"],
        capture_output=True, text=True
    )
    lines = result.stdout.strip().split("\n")
    gpus = []
    for i, line in enumerate(lines):
        util, mem_used, mem_total = line.split(", ")
        gpus.append({
            "gpu_id": i,
            "utilization_percent": int(util),
            "vram_used_mb": int(mem_used),
            "vram_total_mb": int(mem_total),
        })
    return {"gpus": gpus}


@tool(name="read_training_log", description="学習ログの最新N行を取得する")
def read_training_log(log_path: str, num_lines: int = 50) -> str:
    """指定されたログファイルの末尾を読む"""
    with open(log_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    return "".join(lines[-num_lines:])


# MCPサーバー作成
server = create_sdk_mcp_server(
    name="training-monitor",
    version="1.0.0",
    tools=[check_gpu_usage, read_training_log],
)

# エージェント起動
client = ClaudeSDKClient()
response = client.query(
    prompt="GPU使用率を確認して、学習が正常に進んでいるか判断して",
    sdk_mcp_servers=[server],
)
print(response.text)
```

### TypeScript実装

```typescript
import { ClaudeSDKClient, tool, createSdkMcpServer } from "@anthropic-ai/claude-agent-sdk";
import { z } from "zod";

// ツール定義
const checkGpuUsage = tool({
  name: "check_gpu_usage",
  description: "GPU使用率とVRAMを取得する",
  inputSchema: z.object({}),
  handler: async () => {
    const { execSync } = await import("child_process");
    const output = execSync(
      "nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits"
    ).toString();
    // パース処理...
    return { type: "text", text: JSON.stringify({ gpus: [] }) };
  },
});

// MCPサーバー作成
const server = createSdkMcpServer({
  name: "training-monitor",
  version: "1.0.0",
  tools: [checkGpuUsage],
});
```

### インプロセスMCPサーバーの利点

| 方式 | プロセス管理 | IPC | デプロイ |
|------|-------------|-----|---------|
| 外部MCPサーバー | サブプロセス起動が必要 | stdin/stdout | 複数プロセス |
| **インプロセスSDKサーバー** | **不要（同一プロセス）** | **不要** | **単一プロセス** |

---

## MCP（Model Context Protocol）で外部ツール接続

MCPは、AIモデルと外部ツールを接続する標準プロトコルだ。Anthropicが策定し、オープン仕様として公開されている。

### 外部MCPサーバーの接続

```python
client = ClaudeSDKClient()
response = client.query(
    prompt="最新のGitHub Issueを確認して",
    mcp_servers=[
        {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "env": {"GITHUB_TOKEN": os.environ["GITHUB_TOKEN"]},
        }
    ],
)
```

### 代表的なMCPサーバー

| サーバー | 接続先 | 用途 |
|---------|--------|------|
| server-github | GitHub | Issue、PR、コードレビュー |
| server-slack | Slack | メッセージ送信、チャンネル管理 |
| server-postgres | PostgreSQL | データベースクエリ |
| server-filesystem | ローカルFS | ファイル操作 |
| server-brave-search | Brave Search | Web検索 |

### 内部ツールと外部ツールの併用

```python
response = client.query(
    prompt="GPUの状態を確認し、問題があればSlackに通知して",
    sdk_mcp_servers=[training_monitor_server],  # インプロセス
    mcp_servers=[slack_server_config],           # 外部プロセス
)
```

### MCPツール自動検索

MCPツールが多数ある場合、コンテキストウィンドウの消費を抑えるため、Claude Agent SDKはデフォルトで**MCPツール自動検索**を有効にしている。必要なツールだけが動的にロードされる。

---

## カスタムサブエージェント

サブエージェントは、特定のタスクに特化した専門エージェントだ。メインエージェントが複雑なタスクを検出すると、適切なサブエージェントに委任する。

### Markdown + YAMLフロントマターで定義

`.claude/agents/training-analyst.md`:

```yaml
---
name: training-analyst
description: 3DGS学習のログを分析し、品質改善を提案する
tools: Read, Glob, Grep, Bash
model: sonnet
---

あなたは3D Gaussian Splatting学習の専門家です。

## 分析対象
- PSNR、SSIM、LPIPSの推移
- 損失関数の収束状況
- 密度化（densification）のタイミングと効果
- VRAM使用量の推移

## レポート形式
1. 現在の学習状態（正常/警告/異常）
2. 品質指標のトレンド
3. 改善提案（具体的なハイパーパラメータ変更）
```

### プログラムからの定義

```python
response = client.query(
    prompt="学習ログを分析して改善提案をして",
    agents=[
        {
            "name": "training-analyst",
            "description": "3DGS学習のログ分析と改善提案",
            "tools": ["Read", "Glob", "Grep", "Bash"],
            "model": "sonnet",
            "system_prompt": "あなたは3DGS学習の専門家です...",
        }
    ],
)
```

### サブエージェントの特性

| 特性 | 詳細 |
|------|------|
| 並列実行 | 最大10エージェントが同時実行 |
| コンテキスト分離 | メインエージェントとは独立したコンテキスト |
| ステートレス | 各実行は独立（状態を持たない） |
| ツール制限 | エージェントごとに使用可能なツールを指定 |

---

## Hook：エージェントループの制御点

Hookは、エージェントの特定タイミングで確定的な処理を挿入する仕組みだ。

### Hookのタイミング

| Hook | タイミング | 用途 |
|------|-----------|------|
| Setup | エージェント起動時 | 環境初期化、依存関係チェック |
| PreToolUse | ツール実行前 | 入力検証、安全性チェック |
| PostToolUse | ツール実行後 | 結果の加工、通知 |
| Stop | エージェント終了時 | クリーンアップ、レポート生成 |

### 実装例：タイムアウト延長とログ記録

```python
response = client.query(
    prompt="大規模なデータ処理を実行して",
    hooks={
        "PreToolUse": [
            {
                "matcher": "Bash",
                "command": "echo \"[$(date)] Tool: $TOOL_NAME\" >> /tmp/agent.log",
                "timeout_ms": 600000,  # 10分に延長
            }
        ],
        "PostToolUse": [
            {
                "matcher": "*",
                "command": "echo \"[$(date)] Done: $TOOL_NAME\" >> /tmp/agent.log",
            }
        ],
    },
)
```

### Hookの戻り値による制御

| 終了コード | 動作 |
|-----------|------|
| 0 | 続行 |
| 非0 | ツール実行をブロック（PreToolUse）/ エラーを報告（PostToolUse） |

---

## 認証：3つのプロバイダー

Claude Agent SDKは3つの認証方式に対応している。

| プロバイダー | 設定 | 用途 |
|-------------|------|------|
| Anthropic API | `ANTHROPIC_API_KEY` | 直接利用 |
| Amazon Bedrock | `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` | AWSインフラ統合 |
| Google Vertex AI | `GOOGLE_APPLICATION_CREDENTIALS` | GCPインフラ統合 |

```python
# Anthropic API
client = ClaudeSDKClient(api_key="sk-ant-...")

# Amazon Bedrock
client = ClaudeSDKClient(
    provider="bedrock",
    region="us-east-1",
)

# Google Vertex AI
client = ClaudeSDKClient(
    provider="vertex",
    project="my-project",
    region="us-central1",
)
```

---

## 実践例：3DGS学習パイプラインのモニタリングエージェント

3DGS学習は数時間〜数十時間かかる。その間の異常検知と品質モニタリングを自動化するエージェントを構築する。

### アーキテクチャ

```
[Monitoring Agent]
├── check_gpu_usage      → GPU使用率・VRAM監視
├── read_training_log    → ログの最新行を取得
├── parse_metrics        → PSNR/SSIM/損失を抽出
├── check_disk_space     → チェックポイント保存先の空き容量
└── send_notification    → Slack/Discord通知
```

### 実装

```python
from claude_agent_sdk import ClaudeSDKClient, tool, create_sdk_mcp_server
import json
import re
import os

@tool(name="parse_metrics", description="学習ログからPSNR・SSIM・損失を抽出する")
def parse_metrics(log_path: str) -> dict:
    """最新のメトリクスを正規表現で抽出"""
    with open(log_path, "r") as f:
        content = f.read()

    # 最新のPSNR/SSIM/損失を探す
    psnr_matches = re.findall(r"PSNR:\s*([\d.]+)", content)
    ssim_matches = re.findall(r"SSIM:\s*([\d.]+)", content)
    loss_matches = re.findall(r"loss:\s*([\d.]+)", content)

    return {
        "latest_psnr": float(psnr_matches[-1]) if psnr_matches else None,
        "latest_ssim": float(ssim_matches[-1]) if ssim_matches else None,
        "latest_loss": float(loss_matches[-1]) if loss_matches else None,
        "total_entries": len(psnr_matches),
    }


@tool(name="check_disk_space", description="指定パスのディスク空き容量を確認する")
def check_disk_space(path: str) -> dict:
    """ディスク空き容量をGB単位で返す"""
    import shutil
    usage = shutil.disk_usage(path)
    return {
        "total_gb": round(usage.total / (1024**3), 1),
        "used_gb": round(usage.used / (1024**3), 1),
        "free_gb": round(usage.free / (1024**3), 1),
        "usage_percent": round(usage.used / usage.total * 100, 1),
    }


# MCPサーバー構築
monitor_server = create_sdk_mcp_server(
    name="3dgs-monitor",
    version="1.0.0",
    tools=[check_gpu_usage, read_training_log, parse_metrics, check_disk_space],
)

# 定期実行
def run_monitoring():
    client = ClaudeSDKClient()
    response = client.query(
        prompt="""以下を確認して状態レポートを作成してください:
1. GPU使用率とVRAM（check_gpu_usage）
2. 学習ログの最新50行（read_training_log: D:/work/output/train.log）
3. PSNR/SSIM/損失の推移（parse_metrics: D:/work/output/train.log）
4. ディスク空き容量（check_disk_space: D:/work/output/）

異常がある場合は警告レベルを付けてください。
PSNR < 25dBまたはVRAM > 90%の場合は「要注意」と判断してください。
""",
        sdk_mcp_servers=[monitor_server],
    )
    return response.text

if __name__ == "__main__":
    report = run_monitoring()
    print(report)
```

### 拡張案

- **定期実行**: `schedule`ライブラリやcronで10分ごとに実行
- **異常時通知**: Slack MCPサーバーを追加して自動通知
- **自動対処**: VRAM不足時にバッチサイズを自動調整するツールを追加
- **履歴管理**: レポートをデータベースに保存して傾向分析

---

## まとめ

| 機能 | 概要 |
|------|------|
| **カスタムツール** | `@tool`デコレータでインプロセスMCPサーバーを定義 |
| **MCP接続** | 外部サービス（GitHub、Slack、DB等）と標準プロトコルで接続 |
| **サブエージェント** | Markdown+YAMLで専門エージェントを定義、最大10並列 |
| **Hook** | Setup / PreToolUse / PostToolUse / Stop で確定的処理を挿入 |
| **認証** | Anthropic API / Amazon Bedrock / Google Vertex AI |

Claude Agent SDKは、「AIに指示を出す」段階から「AIが自律的にタスクを遂行する」段階への移行を実現するツールだ。カスタムツールとMCPを組み合わせることで、自分の開発環境に最適化されたエージェントを構築できる。

---

## 関連記事

- [Claude Code MCP入門](https://zenn.dev/amabito/articles/claude-code-mcp-intro) - MCPの基礎
- [Claude Code Hook活用](https://zenn.dev/amabito/articles/claude-code-hooks-automation) - Hookの実践例
- [Claude Codeで開発効率3倍](https://zenn.dev/amabito/articles/claude-code-productivity) - 基本的な使い方
- [Discord x Claude Code Bot](https://zenn.dev/amabito/articles/discord-claude-code-bot) - チーム連携

---

## 参考

- [Claude Agent SDK Python ドキュメント](https://platform.claude.com/docs/en/agent-sdk/python) - 公式リファレンス
- [Claude Agent SDK TypeScript ドキュメント](https://platform.claude.com/docs/en/agent-sdk/typescript) - 公式リファレンス
- [Custom Tools ドキュメント](https://platform.claude.com/docs/en/agent-sdk/custom-tools) - カスタムツールの詳細
- [MCP接続ガイド](https://platform.claude.com/docs/en/agent-sdk/mcp) - MCP統合
- [サブエージェント作成ガイド](https://code.claude.com/docs/en/sub-agents) - サブエージェントの定義方法
- [claude-agent-sdk（PyPI）](https://pypi.org/project/claude-agent-sdk/) - Pythonパッケージ
- [claude-agent-sdk-python（GitHub）](https://github.com/anthropics/claude-agent-sdk-python) - ソースコード

---

ご質問・ご相談はコメント欄へ。
