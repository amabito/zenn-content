# Zenn / ビジネス戦略

## Zenn

| 項目 | 内容 |
|------|------|
| リポジトリ | https://github.com/amabito/zenn-content |
| プロフィール | https://zenn.dev/amabito |
| 収益確認 | https://zenn.dev/dashboard/earnings |
| 記事総数 | **68本**（無料52 + 有料16） |

**Skill**: `/zenn-article` `/blogger`

### 有料記事一覧（16本）

| シリーズ | 無料記事 | 有料記事 | 価格 |
|---------|---------|---------|------|
| HyperRasterizer | 完全解説 | 実装ガイド | 980 |
| 3DGS商用化 | ライセンス問題 | 自作ガイド | 1,980 |
| 3DGS画像前処理 | - | 完全ガイド | 1,480 |
| 建設x3DGS | 入門 | 実践ガイド | 1,480 |
| 建設コンサルDX | 現場の本音 | 実践ガイド | 1,480 |
| 不動産x3DGS | 内見7割削減 | 事業拡大マニュアル | 1,480 |
| 製造業x3DGS | 工場ライン3D化 | 導入ロードマップ | 1,480 |
| RTX 5090最適化 | 5つの新常識 | ベンチマーク+SM120 | 1,480 |
| CUDAメモリ管理 | 罠と対策 | メモリプール | 1,480 |
| CUDA warp同期 | warp同期の罠 | 完全ガイド | 980 |
| PyTorch CUDA拡張 | Windowsビルド | 互換性ガイド | 500 |
| GPU入門 | CPUより100倍速い | 高速化実践ガイド | 1,480 |
| Claude Code | 開発効率3倍 | プロンプト集+自動化 | 980 |
| Discord Bot | 構築ガイド | 完全実装ガイド | 980 |
| 年収1000万 | エンジニア1年目の話 | スキルマップ+転職術 | 980 |
| レガシー業界DX | 5つの原則 | 失敗パターン17選 | 1,480 |

### 予約投稿スケジュール（2026/01/26設定）

| 日時 | 記事 | 種類 |
|------|------|------|
| 1/27 (火) 7:00 | 不動産x3DGS事業拡大マニュアル | 有料 |
| 1/27 (火) 12:00 | 製造業x3DGS導入ロードマップ | 有料 |
| 1/28 (水) 7:00 | 自動運転x3DGS | 無料 |
| 1/28 (水) 12:00 | エンタメx3DGS | 無料 |
| 1/29 (木) 7:00 | 保険x3DGS | 無料 |
| 1/29 (木) 12:00 | 文化財x3DGS | 無料 |
| 2/02 (月) 7:00 | 物流x3DGS | 無料 |
| 2/02 (月) 12:00 | 教育x3DGS | 無料 |

### 記事ファイル
```
articles\     # Zenn記事（GitHub連携済み）
```

---

## Qiita

| 項目 | 内容 |
|------|------|
| リポジトリ | https://github.com/amabito/qiita-articles |
| 記事ソース | `D:\work\Projects\qiita-content\public\` |

投稿済み: 3DGSラスタライザ (https://qiita.com/amabito/items/83d096645bcab82fe56a)
未投稿(レートリミット): `cuda-tips-intro.md`, `construction-3dgs-intro.md`, `construction-dx-consultant.md`

---

## GitHub Sponsors

| ティア | 価格 | 内容 |
|--------|------|------|
| Supporter | $5/月 | 感謝 + Discord access |
| Backer | $10/月 | 上記 + 優先サポート |
| Sponsor | $25/月 | 上記 + 技術相談（月1回） |

ダッシュボード: https://github.com/sponsors/amabito/dashboard

---

## Replicate

| 項目 | 内容 |
|------|------|
| モデルURL | https://replicate.com/amabito/hypersplat |
| 収益モデル | 50% revenue share |

残タスク: predict.py接続、サンプル画像追加、テスト実行

---

## ビジネス戦略

### 戦略の核心
```
記事 = 集客チャネル（認知・信頼構築）
本命収益 = コンサル / 受託 / SaaS
```

### 資産

| 資産 | 状態 | 商用利用 |
|------|------|----------|
| HyperRasterizer | 4169 FPS (DGR 1.45x) | Apache 2.0 |
| HyperViewer | WebGPU 3DGSビューア | Apache 2.0 |
| HyperSplat | 学習フレームワーク完成 | 独自実装 |
| IGS | CLI + Desktop GUI | 独自実装 |

### 収益チャネル

| チャネル | 月額目標 | 状態 |
|---------|---------|------|
| Zenn有料記事 | 20,000-50,000 | 構築中 |
| GitHub Sponsors | $50-200 | 認知待ち |
| Replicate | 未定 | predict.py未完 |
| コンサル/受託 | 300,000+ | Phase 2 |
| SaaS | 500,000+ | Phase 3 |

### Phase 1: 知名度構築 (1-3ヶ月目) → 進行中
### Phase 2: PoC・案件獲得（4-6ヶ月目）
### Phase 3: SaaS化（7-12ヶ月目）

### 導線フロー
```
Qiita（ティーザー）→ Zenn（無料）→ Zenn（有料）
                                     ↓
                              GitHub Star → コンサル/受託案件
```

### 収益予測

| 時期 | 月間PV | CVR | 月額見込み |
|------|--------|-----|-----------|
| 短期（1-3ヶ月） | 200-500 | 0.5% | 2,000-5,000 |
| 中期（6-12ヶ月） | 1,000-2,000 | 1% | 11,000-22,000 |
| 長期（1年以降） | 2,000-5,000 | 1.5% | 30,000-50,000 |
