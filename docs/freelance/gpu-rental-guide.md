# RTX 5090でGPU貸出による不労所得を得る実践ガイド（2026年版）

## はじめに

RTX 5090（32GB）をWindows 11で24時間稼働させている場合、アイドル時間を活用してGPU計算能力を貸し出すことで、月数万円〜数十万円の副収入を得られる可能性があります。本ガイドでは、2026年時点で最も実用的なプラットフォームと、具体的なセットアップ方法を解説します。

## プラットフォーム比較表

| プラットフォーム | Windows対応 | セットアップ難易度 | 月間予想収益（RTX 5090） | 最低出金額 | 支払い方法 |
|-----------------|------------|------------------|----------------------|-----------|----------|
| **Salad** | ✅ ネイティブ対応 | ⭐ 最も簡単 | ¥20,000〜¥70,000 | $5 | PayPal, Amazon, その他 |
| **vast.ai** | ❌ Linux/Docker必須 | ⭐⭐⭐ 複雑 | ¥40,000〜¥150,000 | $10 | 暗号通貨 |
| **RunPod** | ⚠️ Community Cloudは要検証 | ⭐⭐ 中程度 | ¥30,000〜¥100,000 | 不明 | 暗号通貨 |
| **io.net** | ⚠️ 詳細情報不足 | ⭐⭐ 中程度 | ¥25,000〜¥80,000 | 暗号通貨 | IOトークン |
| **Clore.ai** | ⚠️ 要確認 | ⭐⭐⭐ 複雑 | ¥30,000〜¥90,000 | 不明 | CLOREトークン |

**注**: 収益は稼働率55〜80%、市場価格変動、電気代を除いた推定値

## 推奨プラットフォーム: **Salad（最もWindows向き）**

### なぜSaladか？

1. **Windowsネイティブ対応** — Docker不要、アプリをインストールするだけ
2. **最も簡単なセットアップ** — 10分以内に稼働開始
3. **自動ジョブマッチング** — 手動でジョブを探す必要なし
4. **安定した需要** — AI推論、レンダリング、科学計算など幅広いジョブ
5. **柔軟な出金方法** — PayPal、Amazonギフトカード、その他多数

### RTX 5090での予想収益

**前提条件:**
- RTX 5090（32GB）
- 稼働率: 55〜70%（アイドル時のみ貸出）
- 時給レート: $0.50〜$1.50/時（市場需要による）
- 電気代: ¥30/kWh、消費電力: 400W（AI負荷時）

**月間収益シミュレーション:**

```
シナリオ1（保守的）: 55%稼働率、$0.50/時
- 月間稼働時間: 720時間 × 55% = 396時間
- 総収益: 396時間 × $0.50 = $198（約¥29,700）
- 電気代: 396時間 × 0.4kW × ¥30 = ¥4,752
- 純利益: 約¥24,948/月

シナリオ2（楽観的）: 70%稼働率、$1.20/時
- 月間稼働時間: 720時間 × 70% = 504時間
- 総収益: 504時間 × $1.20 = $604.80（約¥90,720）
- 電気代: 504時間 × 0.4kW × ¥30 = ¥6,048
- 純利益: 約¥84,672/月
```

**重要**: 収益は市場需要、時期（年末・繁忙期は高単価）、競合状況により大きく変動します。

## Saladセットアップ手順（Windows 11）

### ステップ1: システム要件確認

**最小要件:**
- GPU: 6GB以上のVRAM（RTX 5090は32GBなので余裕でクリア）
- OS: Windows 10/11
- インターネット: 常時接続

**推奨要件（RTX 5090は全て満たす）:**
- GPU: RTX 3090以降
- CPU: 4コア以上
- RAM: 12GB以上

### ステップ2: Saladアプリダウンロード

1. [Salad公式サイト](https://salad.com/) にアクセス
2. "Download Golden Chef"または"Download Salad"をクリック
3. インストーラー（Windows版）をダウンロード
4. インストーラーを実行し、画面の指示に従う

### ステップ3: アカウント作成と初期設定

1. Saladアプリを起動
2. アカウント作成（メールアドレス + パスワード）
3. GPU自動検出を確認（RTX 5090が認識されていること）
4. 支払い方法を設定（後で変更可能）

### ステップ4: 稼働スケジュール設定

**重要**: 開発作業中はGPUを貸し出さない設定にする

**方法1: Saladアプリ内スケジューリング**
- アプリ設定から「稼働時間」を指定
- 例: 平日 0:00〜8:00、土日 0:00〜10:00

**方法2: Windowsタスクスケジューラで自動化**

```powershell
# Saladを指定時刻に起動・停止するスクリプト例
# タスクスケジューラで毎日0:00に実行
Start-Process "C:\Program Files\Salad\Salad.exe"

# 毎日8:00に実行（Salad停止）
Stop-Process -Name "Salad" -Force
```

**方法3: 手動ON/OFF**
- 寝る前にSaladを起動
- 朝起きたら停止

### ステップ5: 稼働開始

1. Saladアプリで"Start Earning"をクリック
2. 自動的にジョブが割り当てられる
3. リアルタイムで収益がカウントされる

### ステップ6: 収益確認と出金

- **最低出金額**: $5（約¥750）
- **出金方法**:
  - PayPal（即時、手数料低）
  - Amazonギフトカード
  - その他ギフトカード多数
- **出金頻度**: 好きなタイミング（最低額を超えれば）

## アイドル時間のみ稼働させる方法

### 自動化スクリプト（PowerShell）

```powershell
# salad-auto-control.ps1
# タスクスケジューラで定期実行（例: 5分おき）

param(
    [int]$IdleMinutes = 30  # 30分アイドルで開始
)

# ユーザーアクティビティチェック
Add-Type @'
using System;
using System.Runtime.InteropServices;

public class UserActivity {
    [DllImport("user32.dll")]
    public static extern bool GetLastInputInfo(ref LASTINPUTINFO plii);

    public struct LASTINPUTINFO {
        public uint cbSize;
        public uint dwTime;
    }

    public static uint GetIdleTime() {
        LASTINPUTINFO lastInputInfo = new LASTINPUTINFO();
        lastInputInfo.cbSize = (uint)Marshal.SizeOf(lastInputInfo);
        GetLastInputInfo(ref lastInputInfo);
        return ((uint)Environment.TickCount - lastInputInfo.dwTime);
    }
}
'@

$idleTimeMs = [UserActivity]::GetIdleTime()
$idleTimeMins = $idleTimeMs / 60000

# CUDA使用中かチェック（開発中のプロセスがないか）
$cudaProcesses = Get-Process | Where-Object {
    $_.ProcessName -match "python|pytorch|cuda|nvcc"
}

# 判定ロジック
if ($idleTimeMins -gt $IdleMinutes -and $cudaProcesses.Count -eq 0) {
    # アイドル状態 → Salad起動
    $salad = Get-Process -Name "Salad" -ErrorAction SilentlyContinue
    if (-not $salad) {
        Start-Process "C:\Program Files\Salad\Salad.exe"
        Write-Host "Salad started (Idle: $idleTimeMins min)"
    }
} else {
    # アクティブまたは開発中 → Salad停止
    Stop-Process -Name "Salad" -Force -ErrorAction SilentlyContinue
    Write-Host "Salad stopped (Active or Dev mode)"
}
```

**タスクスケジューラ設定:**
1. タスクスケジューラを開く
2. 「基本タスクの作成」
3. トリガー: 5分おきに繰り返し実行
4. 操作: `powershell.exe -File "C:\Scripts\salad-auto-control.ps1"`

## リスクと考慮事項

### ハードウェアリスク

**GPU寿命への影響:**
- ✅ AI推論は安定負荷（マイニングよりGPU寿命に優しい）
- ⚠️ 24時間稼働でファン・サーマルペーストの劣化は早まる
- 💡 対策: 定期的な清掃、温度監視（80℃以下推奨）

**消費電力:**
- RTX 5090: 最大575W（TGP）
- AI負荷時平均: 350〜450W
- 月間電気代（400W、60%稼働）: 約¥5,000〜¥8,000

### セキュリティリスク

**Saladの場合:**
- ✅ サンドボックス化されたコンテナで実行（ユーザーデータにアクセス不可）
- ✅ ホワイトリスト制ジョブ（悪意あるコードは排除）
- ⚠️ ネットワークトラフィック増加（ファイアウォール監視推奨）

**推奨対策:**
1. Salad専用Windows Sandboxで実行（完全隔離）
2. 重要データは別ドライブに保管
3. ネットワーク監視ツールで異常トラフィック検知

### 収益性リスク

**変動要因:**
- 市場需要（年末・AI開発ピーク時は高収益）
- 競合増加（RTX 5090保有者が増えると単価低下）
- 為替レート（ドル建て収益）
- プラットフォーム手数料変更

**対策:**
- 複数プラットフォーム併用（リスク分散）
- 収益ログを記録し、採算ライン確認
- 電気代が収益を上回る場合は一時停止

## 収支シミュレーション（3ヶ月）

```
前提:
- RTX 5090（¥450,000購入）
- Salad平均時給: $0.80
- 稼働率: 60%（月432時間）
- 電気代: ¥30/kWh、400W消費
- 為替レート: ¥150/$

月次収支:
収益: 432時間 × $0.80 × ¥150 = ¥51,840
電気代: 432時間 × 0.4kW × ¥30 = ¥5,184
純利益: ¥46,656/月

3ヶ月後累計:
純利益: ¥46,656 × 3 = ¥139,968

投資回収期間:
¥450,000 ÷ ¥46,656 = 約9.6ヶ月
```

**注**: これは楽観的シナリオ。実際は市場変動・トラブル等で変動。

## よくある質問（FAQ）

### Q1: 開発作業とGPU貸出は同時にできる？

**A**: できません。GPUは排他的に使用されるため、Claude Code等のCUDA処理と並行稼働は不可。必ずアイドル時間のみに限定してください。

### Q2: Vast.aiやRunPodの方が収益高い？

**A**: はい、時給は高いですが、Windows対応が困難（DockerやLinux必須）。セットアップの手間と技術的難易度を考えると、Windowsユーザーには**Saladが最適**です。

### Q3: マイニングとどちらが稼げる？

**A**: 2026年時点ではAI貸出が有利。RTX 5090のマイニング収益は1日約$0.30（電気代後）に対し、Salad等のAI貸出は1日$10〜$30（稼働率60%想定）。

### Q4: 税金は？

**A**: 雑所得として確定申告が必要（年間20万円超の場合）。PayPal等の記録を保管してください。

### Q5: GPUが壊れたら？

**A**: メーカー保証の対象外になる可能性があります（商用利用とみなされる場合）。自己責任での運用となります。

## まとめ

**RTX 5090をWindows 11で不労所得化する最善策:**

1. **Salad一択**（Windows対応、最も簡単）
2. **アイドル時間のみ稼働**（PowerShell自動化推奨）
3. **月間¥20,000〜¥70,000の副収入を目標**
4. **電気代・GPU寿命を考慮し、採算ラインを常に確認**

**次のステップ:**
1. [Salad公式サイト](https://salad.com/)でアカウント作成
2. アプリダウンロード・インストール
3. 1週間テスト稼働して収益確認
4. 採算が取れれば本格稼働

---

## 参考リンク

### Salad
- [Salad公式サイト](https://salad.com/)
- [SaladCloud RTX 5090発表](https://blog.salad.com/rtx5090/)
- [Salad GPU価格](https://salad.com/pricing)
- [SaladでGPU貸出する方法](https://community.salad.com/sell-gpu-power/)

### その他プラットフォーム
- [vast.ai RTX 5090価格](https://vast.ai/pricing/gpu/RTX-5090)
- [vast.ai ホスティング概要](https://docs.vast.ai/documentation/host/hosting-overview)
- [RunPod RTX 5090](https://www.runpod.io/gpu-models/rtx-5090)
- [io.net 分散GPU](https://io.net/about-us)
- [Clore.ai マーケットプレイス](https://clore.ai/marketplace)

### 収益性・比較
- [GPU不労所得2025: RTX 4090ガイド](https://shareai.now/blog/insights/gpu-passive-income-rtx-4090-2025/)
- [NiceHash収益計算](https://www.nicehash.com/profitability-calculator/nvidia-rtx-5090)
- [RTX 5090レンタル価格比較](https://www.techradar.com/pro/security/you-can-now-rent-a-usd3000-nvidia-rtx-5090-gpu-from-just-usd0-25-hour-when-you-need-it-for-as-long-as-you-need-it)

---

**最終更新**: 2026年2月8日
**対象環境**: Windows 11, RTX 5090 32GB
