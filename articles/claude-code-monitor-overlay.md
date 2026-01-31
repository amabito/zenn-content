---
title: "Claude Code状態監視：WPFオーバーレイで常時表示するツールを自作"
emoji: "🖥️"
type: "tech"
topics: ["ClaudeCode", "CSharp", "WPF", "dotnet", "開発ツール"]
published: true
published_at: "2026-02-06 07:00"
---

# 結論から言う

**Claude Codeの動作状態（処理中/入力待ち/アイドル）をデスクトップに常時表示するオーバーレイアプリを作った。**

- Claude Codeが入力待ちになったらWindows通知
- 複数インスタンスを同時監視
- CPU/GPU/メモリ/ネットワークも同時表示

**別ウィンドウで作業していても、Claude Codeの状態が一目でわかる。**

---

# なぜ必要か

## 問題：Claude Codeの処理完了に気づかない

Claude Codeに指示を出して、別の作業をしている間に処理が完了しても気づかない。

```
よくあるパターン:
1. Claude Codeに「テスト実行して」と指示
2. ブラウザで調べ物を始める
3. 10分後にターミナルに戻る
4. 「3分前に終わってた...」← 7分のロス
```

**1日に何度も発生すると、累計で数十分のロスになる。**

## 解決：常時表示オーバーレイ

```
画面の端に常時表示:
┌────────────────────────────────┐
│ 🟢 Claude Code [処理中]        │
│    Implementing user auth...   │
│ CPU: 12% | GPU: 45% | RAM: 8G │
└────────────────────────────────┘

→ 「入力待ち」になったら通知が飛ぶ
→ 別作業中でも見逃さない
```

---

# SystemOverlay

## 機能一覧

| 機能 | 説明 |
|------|------|
| Claude Code監視 | 処理中/入力待ち/アイドルの3状態を検出 |
| 複数インスタンス | 複数ターミナルのClaude Codeを同時監視 |
| タイトル取得 | Windows Terminal/PowerShellのタブタイトル表示 |
| 通知 | 入力待ち時にWindows Toast通知 |
| システム監視 | CPU, GPU, Memory, Network I/O, Disk I/O |
| トッププロセス | CPU使用率上位プロセスを表示 |
| カスタマイズ | 文字サイズ、透過度、縁取り、位置 |
| 自動起動 | PC起動時に自動起動（レジストリ） |
| Hook管理 | Claude Code Hookの設定UI |

## 技術スタック

| 項目 | 選択 | 理由 |
|------|------|------|
| フレームワーク | WPF (.NET 8) | Windows向けUI + 低レベルAPI |
| GPU情報 | nvidia-smi | 確実なGPU情報取得 |
| 状態検出 | CPU使用率ベース | プロセス内部APIが不要 |
| 通知 | Windows Toast | OS標準、確実に届く |

---

# Claude Code状態検出のしくみ

## 3つの状態

```
処理中（Working）
  └─ CPU使用率 ≥ 5%

入力待ち（Waiting）
  └─ CPU使用率 ≤ 1% かつ 直前まで処理中だった

アイドル（Idle）
  └─ CPU使用率 ≤ 1% かつ 長時間アクティビティなし
```

## 状態遷移

```
[起動] → Idle
  │
  ├─ CPU ≥ 5% → Working
  │                │
  │                └─ CPU ≤ 1% → Waiting ← 通知！
  │                                │
  │                                └─ 60秒無操作 → Idle
  │
  └─ 終了 → 監視リストから削除
```

**ポイント**: 「WasProcessing」フラグで直前の状態を追跡し、単なるアイドルと入力待ちを区別する。

## タイトル取得

Claude Codeが動いているWindows Terminal/PowerShellのタブタイトルを取得する。

```csharp
// AttachConsole APIで親プロセスのコンソールタイトルを取得
[DllImport("kernel32.dll")]
static extern bool AttachConsole(uint dwProcessId);

[DllImport("kernel32.dll")]
static extern uint GetConsoleTitle(StringBuilder lpConsoleTitle, uint nSize);
```

**結果**: `claude - D:\work\Projects\hyper-rasterizer` のようなタイトルが表示される。

---

# UI設計

## レイアウト

```
┌─ SystemOverlay ──────────────────────┐
│                                      │
│ 🟢 Claude [1] 処理中                 │
│    hyper-rasterizer                  │
│ 🟡 Claude [2] 入力待ち              │
│    3dgs-unified                      │
│                                      │
│ ───────────────────────────────────  │
│ CPU: 12.3%  GPU: 45.2%  Temp: 62°C  │
│ RAM: 16.2/64.0 GB                    │
│ Net ↓ 1.2MB/s  ↑ 0.3MB/s           │
│ Disk: R 50MB/s  W 12MB/s            │
│                                      │
│ Top: claude(12%) chrome(8%) code(5%) │
└──────────────────────────────────────┘
```

## カスタマイズオプション

| 設定 | デフォルト | 範囲 |
|------|-----------|------|
| 文字サイズ | 12pt | 8-24pt |
| 背景透過度 | 70% | 0-100% |
| 文字縁取り | ON | ON/OFF |
| 常に最前面 | ON | ON/OFF |
| 表示位置 | 右上 | 四隅 |
| 更新間隔 | 2秒 | 1-10秒 |

---

# Hook管理UI

## Claude Code Hooksとは

Claude Codeにはフック機能があり、特定のイベントでシェルコマンドを実行できる。

```json
// ~/.claude/settings.local.json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hook": "echo 'Bash tool used'"
      }
    ]
  }
}
```

## SystemOverlayのHook管理UI

GUIでHookを追加・編集・削除できる。

```
┌─ Hook設定 ──────────────────────────┐
│                                      │
│ [+ 追加] [保存] [リロード]           │
│                                      │
│ ┌─ PreToolUse ─────────────────────┐ │
│ │ Matcher: Bash                    │ │
│ │ Command: echo "tool used"        │ │
│ │ [編集] [削除]                    │ │
│ └──────────────────────────────────┘ │
│                                      │
│ ┌─ PostToolUse ────────────────────┐ │
│ │ Matcher: Write                   │ │
│ │ Command: git add -A              │ │
│ │ [編集] [削除]                    │ │
│ └──────────────────────────────────┘ │
└──────────────────────────────────────┘
```

**直接JSONを編集する必要がなくなる。**

---

# インストール

## ビルド済みバイナリ

```bash
# ZIPをダウンロードして展開
# SystemOverlay.exeを実行
```

## ソースからビルド

```bash
# .NET 8 SDK が必要
dotnet build --configuration Release
```

## 自動起動設定

アプリ内の設定で「自動起動」をONにすると、レジストリに登録される。

```
HKCU\Software\Microsoft\Windows\CurrentVersion\Run
  SystemOverlay = "C:\...\SystemOverlay.exe"
```

---

# 開発で工夫した点

## nvidia-smiの効率的な呼び出し

GPUの温度・使用率はnvidia-smiで取得するが、毎秒呼び出すとオーバーヘッドが大きい。

```
対策:
├── 2秒間隔で呼び出し（1秒ではなく）
├── プロセスプールで再利用
└── CSV出力で高速パース
```

```bash
nvidia-smi --query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total --format=csv,noheader,nounits
```

## WPFの透過ウィンドウ

```xml
<Window
    AllowsTransparency="True"
    WindowStyle="None"
    Background="Transparent"
    Topmost="True">
```

**半透明の背景 + 文字の縁取り**で、どんな背景でも読める。

---

# まとめ

| 項目 | 内容 |
|------|------|
| 名前 | SystemOverlay |
| 機能 | Claude Code状態監視 + システムモニター |
| 技術 | WPF / .NET 8 |
| 対応OS | Windows 11 |
| 通知 | 入力待ち時にToast通知 |

**Claude Codeのマルチタスク運用には必須。**

---

# 関連記事

## Claude Codeシリーズ
- [Claude Codeで開発効率3倍](https://zenn.dev/amabito/articles/claude-code-productivity) - 基本活用
- [Claude Code MCP入門](https://zenn.dev/amabito/articles/claude-code-mcp-intro) - MCPプロトコル
- [Claude Code Hookで自動化](https://zenn.dev/amabito/articles/claude-code-hooks-automation) - Hook活用法
- [スマホからClaude Code操作](https://zenn.dev/amabito/articles/discord-claude-code-bot) - Discord Bot

## 3DGSシリーズ
- [HyperRasterizer完全解説](https://zenn.dev/amabito/articles/hyper-rasterizer-zenn) - 4169FPS達成
