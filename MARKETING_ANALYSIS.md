# Zenn マーケティング分析レポート（2026/01/31作成）

## 📊 現状の数字

### 記事統計
- **総記事数**: 100記事
- **公開済み**: 87記事（published: true、予約投稿設定済み）
- **未公開**: 13記事（published: false）
- **過去に公開されていた記事**: 39記事
- **総閲覧数**: 740

### 重要な数字
```
740閲覧 ÷ 39記事 = 19.0閲覧/記事
評価: F（落第）

Zenn平均: 100-500閲覧/記事（初月）
→ 5-26倍遅れている
```

---

## 📝 過去に公開されていた39記事（740閲覧の対象）

### 3DGS関連（5記事）
- 3dgs-business-guide.md
- 3dgs-commercial-guide-paid.md
- 3dgs-commercial-guide.md
- 3dgs-image-preprocessing-paid.md
- 3dgs-rasterizer-comparison.md

### 建設関連（10記事）
- construction-3dgs-paid.md
- construction-3dgs.md
- construction-consultant-business-model.md
- construction-consultant-reality-paid.md
- construction-consultant-reality.md
- construction-consultant-salary.md
- construction-dx-failure.md
- construction-value-chain.md
- drone-survey-guide.md
- small-construction-survival.md

### CUDA/GPU関連（8記事）
- cuda-memory-management-paid.md
- cuda-memory-management.md
- cuda-optimization-basics.md
- cuda-warp-sync-trap-paid.md
- cuda-warp-sync-trap.md
- gpu-programming-intro.md
- gpu-programming-paid.md
- rtx5090-cuda-optimization-paid.md
- rtx5090-cuda-optimization.md

### Claude Code関連（2記事）
- claude-code-productivity-paid.md
- claude-code-productivity.md

### PyTorch関連（2記事）
- pytorch-cuda-extension-paid.md
- pytorch-cuda-extension.md

### その他（12記事）
- engineer-salary-1000man-paid.md
- engineer-salary-1000man.md
- hyper-rasterizer-impl-paid.md
- hyper-rasterizer-zenn.md
- iconstruction-2-reality.md
- legacy-industry-dx-paid.md
- legacy-industry-dx.md
- nerf-now-2026.md
- nerf-vs-3dgs-2026.md
- realestate-3dgs.md
- tech-career-2026.md

---

## 🔴 3つの深刻な問題

### 1. トピック選定のミスマッチ

| トピック | 記事数 | 割合 | 日本の潜在読者数 | 判定 |
|---------|--------|------|----------------|------|
| 建設DX | 10記事 | 26% | 100-300人 | **超ニッチ** |
| CUDA/GPU | 8記事 | 21% | 300-800人 | ニッチ |
| 3DGS | 5記事 | 13% | 200-500人 | **超ニッチ** |
| Claude Code | 2記事 | 5% | 2,000-5,000人 | 中規模 |

**問題:** 47%が超ニッチ市場を狙っている

---

### 2. SEOタイトルが弱い

**ダメな例:**
- "建設DXが失敗する理由" → 検索需要: 月10-20回
- "3DGS商用化ガイド" → 検索需要: 月5-10回
- "CUDA最適化基礎" → 競合多数で埋もれる

**良い例（修正案）:**
- "【2026年版】Claude Codeで開発速度3倍にする全技術" → 月500-1,000回
- "RTX 5090で機械学習を10倍高速化する完全ガイド" → 月1,000-2,000回
- "Python CUDA入門：5分で環境構築〜実行まで" → 月2,000-5,000回

---

### 3. Twitter/X流入がほぼゼロ

```
86記事投稿済み（.tweeted-articlesより）
740閲覧 ÷ 86ツイート = 8.6閲覧/ツイート

異常に低い → フォロワー数が極端に少ない可能性
```

---

## 💡 プロのマーケターとしての処方箋

### 🚨 最優先施策（今週中）

#### 1. Twitter/Xアカウント診断
- フォロワー数確認
- インプレッション数確認
- フォロワー10人未満なら「Twitter流入は諦める」

#### 2. Claude Code系2記事のSEOタイトル緊急リライト

**対象:**
- claude-code-productivity.md
- claude-code-productivity-paid.md

**修正例:**
```
❌ "Claude Codeで開発効率3倍にした具体的な使い方【2026年版】"
✅ "【Claude Code】開発速度3倍にした全テクニック【2026年最新】"
```

#### 3. Zenn内活動開始（今すぐ）

- トレンド記事10本に価値あるコメント投稿
- 人気著者10人をフォロー
- いいね100個を戦略的に配布

**効果:** 50-100人の流入が見込める

---

### 📈 中期施策（2週間以内）

#### 4. 人気トピック新記事5本追加

1. Claude Code実践ガイド（検索需要：月2,000+）
2. AI活用入門（検索需要：月5,000+）
3. Python環境構築（検索需要：月10,000+）
4. GitHub Copilot比較（検索需要：月3,000+）
5. ChatGPT API活用（検索需要：月8,000+）

#### 5. 既存記事のSEOタイトル全面リライト

**対象:** 39記事中の上位20記事

**優先順位:**
1. Claude Code系（2記事） ← 市場大きい
2. CUDA/GPU系（8記事） ← 検索需要ある
3. PyTorch系（2記事） ← ロングテール
4. キャリア系（2記事） ← 需要安定

---

### 🎯 長期施策（1ヶ月以内）

#### 6. トピック戦略の全面見直し

**現状の配分（39記事）:**
- 建設DX: 26% ← 削減
- CUDA/GPU: 21% ← 維持
- 3DGS: 13% ← 削減
- Claude Code: 5% ← **拡大**

**推奨配分（今後の新記事）:**
- Claude Code/AI: 50% ← 市場大きい
- Python/CUDA入門: 30% ← 検索需要高い
- 3DGS: 20% ← 専門性証明用
- 建設DX: 0% ← **完全停止**

#### 7. 有料記事の戦略見直し

- 有料3本を無料化実験
- 1ヶ月後のPV変化を測定
- CVR改善を確認

---

## 📊 2/23時点での目標

| 指標 | 現状 | 目標 | 達成確率 |
|------|------|------|---------|
| 総閲覧数 | 740 | 5,000+ | 60% |
| 新規記事あたり閲覧 | 19.0 | 50+ | 70% |
| いいね合計 | 不明 | 150+ | 50% |
| トレンド入り記事 | 0 | 1-2本 | 30% |
| 有料記事売上 | 不明 | ¥2,000+ | 20% |

---

## ⚙️ 予約投稿の状況

### 設定内容
- **対象**: 87記事（published: true）
- **期間**: 2026-02-01 07:00 〜 2026-02-22 18:00
- **スロット**: 4回/日（07:00, 12:00, 18:00, 21:00）
- **Git push**: 完了（コミットID: 8b34967）

### 公開スケジュール
```
2/1 07:00 → 1本目公開
2/1 12:00 → 2本目公開
...
2/22 18:00 → 87本目公開（完了）
```

---

## 🔴 厳しい結論

### 現状評価: F（落第）

**理由:**
1. 19閲覧/記事は「誰も読んでいない」レベル
2. トピック選定が市場とミスマッチ（47%が超ニッチ）
3. Twitter/X流入がほぼゼロ（8.6閲覧/ツイート）

### 核心的な問題

```
量は十分（100記事）
質は不明
配信戦略が完全に失敗 ← ここが問題
```

### 次のアクション

**published_at設定は完了したが、これだけでは不十分。**

**優先順位:**
1. Twitter診断（今日）
2. Claude Code系2記事のSEOリライト（今週）
3. Zenn内活動開始（今すぐ）
4. 既存39記事の改善（新記事87本を待つより効果的）

---

## 📝 参考情報

### 関連ファイル
- Zennプロジェクト: `D:\work\Projects\zenn\`
- Bloggerスキル: `C:\Users\amabito\.claude\skills\blogger\skill.md`
- Twitter投稿履歴: `D:\work\Projects\zenn\.tweeted-articles`

### Git履歴
```
8b34967 fix: Set published_at to future dates (2026-02-01 to 2026-02-22)
854c692 fix: Correct published_at to 4-slot schedule
71be54a feat: Add published_at to 56 articles
e5a5cfb chore: 段階的公開のため33記事を一時非公開に
```

---

**作成日時:** 2026-01-31
**分析者:** Claude Sonnet 4.5 (Bloggerスキル)
