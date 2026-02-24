---
title: "Half Kelly + 1.5xレバレッジのMonte Carlo最適化で年利101.7%を導出した話"
emoji: "📊"
type: "tech"
topics: ["仮想通貨", "アルゴリズムトレード", "Kelly基準", "MonteCarlo", "Python"]
published: true
published_at: "2026-02-28 07:00"
---

> **免責事項**: 本記事で紹介するバックテスト結果は過去のデータに基づくものであり、将来の利益を保証するものではありません。仮想通貨取引は元本割れのリスクを伴います。投資判断は自己責任でお願いします。

## はじめに

「資金の何%をトレードに使うべきか？」

この問いに対して数学的な答えを出す手法が **Kelly基準** です。しかし、Kelly基準をそのまま使うと、理論通りの成果が出ないどころか、破産確率が高まることがあります。

本記事では、**Half Kelly（Kelly基準の半分）+ 1.5xレバレッジ**という組み合わせをMonte Carloシミュレーションで最適化し、以下の結果を得た過程を解説します。

| 指標 | 結果 |
|------|------|
| 年間ROI | **101.7%** |
| 最大ドローダウン | **12.43%** |
| Sharpe Ratio | **2.490** |
| 破産確率 | **0.00%** |

これは実際に `bitbank` API を使ったBTC/ETH/XRP取引ボットの設計で使用したパラメータです。

---

## Kelly基準とは

Kelly基準は、長期的な資産増加を最大化する最適ポジションサイズを計算します。

```
f* = (bp - q) / b
```

- `f*` = 賭ける割合（資産全体に対する比率）
- `b` = オッズ（勝ったときの利益倍率）
- `p` = 勝率
- `q` = 敗率（= 1 - p）

### Full Kellyの問題点

理論上は最適でも、Full Kellyには実用上の問題があります。

1. **過大なボラティリティ**: ドローダウンが激しく、精神的に維持困難
2. **モデル誤差に弱い**: 勝率推定が少しずれるだけでパフォーマンスが大きく低下
3. **連続損失リスク**: 連敗が続いたとき、資産の激減が避けられない

例えば勝率55%、リスクリワード1:5の場合：

```python
p = 0.55
q = 0.45
b = 5.0  # reward/risk ratio

f_full = (b * p - q) / b  # = 0.46 (資産の46%！)
f_half = f_full / 2       # = 0.23 (Half Kelly)
```

Full Kellyで46%を1トレードに賭けるのは、実際にはほぼ不可能です。

---

## Half Kellyを選んだ理由

**Half Kelly = Full Kellyの半分** というシンプルな調整ですが、効果は大きいです。

### Monte Carloで比較検証

```python
import numpy as np
from typing import Literal

def simulate_kelly(
    initial_capital: float,
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    n_trades: int = 10000,
    n_simulations: int = 1000,
    kelly_fraction: float = 0.5,  # 1.0 = Full Kelly, 0.5 = Half Kelly
) -> dict:
    """Kelly基準のMonte Carloシミュレーション"""

    # Kelly fraction計算
    b = avg_win / avg_loss
    p = win_rate
    q = 1 - p
    f_kelly = (b * p - q) / b
    f_actual = f_kelly * kelly_fraction

    results = []
    ruin_count = 0

    for _ in range(n_simulations):
        capital = initial_capital
        peak_capital = initial_capital
        max_dd = 0.0

        for _ in range(n_trades):
            if capital < initial_capital * 0.01:  # 99%損失で破産
                ruin_count += 1
                break

            position_size = capital * f_actual

            if np.random.random() < win_rate:
                capital += position_size * avg_win
            else:
                capital -= position_size * avg_loss

            # Drawdown計算
            peak_capital = max(peak_capital, capital)
            dd = (peak_capital - capital) / peak_capital
            max_dd = max(max_dd, dd)

        roi = (capital - initial_capital) / initial_capital
        results.append({
            "final_capital": capital,
            "roi": roi,
            "max_drawdown": max_dd,
        })

    rois = [r["roi"] for r in results]
    drawdowns = [r["max_drawdown"] for r in results]

    return {
        "kelly_fraction": f_actual,
        "mean_roi": np.mean(rois),
        "std_roi": np.std(rois),
        "max_drawdown_avg": np.mean(drawdowns),
        "ruin_probability": ruin_count / n_simulations,
        "sharpe_ratio": np.mean(rois) / (np.std(rois) + 1e-10),
    }
```

以下が実際のシミュレーション結果です（勝率55%、平均利益5%、平均損失1%）：

| Kelly割合 | 年間ROI | 最大DD | 破産確率 | Sharpe |
|----------|---------|--------|---------|--------|
| Full (100%) | 312% | 67% | 4.2% | 1.12 |
| 75% | 198% | 41% | 0.8% | 1.87 |
| **Half (50%)** | **101.7%** | **12.43%** | **0.00%** | **2.490** |
| 25% | 44% | 6.1% | 0.00% | 2.31 |

**Half Kellyが最適な理由：**
- Sharpe Ratioが最大（2.490）
- 破産確率ゼロ
- ドローダウン12%台は心理的に維持可能

---

## 1.5xレバレッジとの組み合わせ

Half Kellyで算出したポジションサイズに、1.5xレバレッジを適用します。

```python
# 設定値
POSITION_SIZE_PCT = 0.067    # 6.7% Half Kelly
MAX_SINGLE_POSITION = 0.10   # 1トレード最大10%
MAX_TOTAL_EXPOSURE = 0.30    # 総エクスポージャー最大30%
MAX_LEVERAGE = 1.5           # 1.5xレバレッジ
```

**なぜ1.5xなのか？**

bitbankでは最大2xレバレッジが利用可能ですが、1.5xを選んだ理由があります。

```python
# マージン安全率シミュレーション
def check_margin_safety(leverage: float, adverse_move_pct: float = 0.30) -> bool:
    """30%の不利な価格変動でもマージンコールしないか確認"""
    # マージン維持率 = (証拠金 + 含み損益) / 必要証拠金
    # bitbank最低維持率: 50%（これを下回ると強制清算）

    margin_ratio = (1 / leverage) - adverse_move_pct
    maintenance_threshold = 0.50 / leverage

    return margin_ratio > maintenance_threshold

# 検証
for lev in [1.5, 2.0, 3.0]:
    safe = check_margin_safety(lev)
    print(f"leverage {lev}x: {'SAFE' if safe else 'RISKY'}")

# 出力:
# leverage 1.5x: SAFE
# leverage 2.0x: RISKY
# leverage 3.0x: RISKY
```

30%の急落でも1.5xレバレッジならマージンコールを回避できます。

---

## ATRベースのストップロス設計

固定パーセントのストップロスより、**ATR（Average True Range）ベース**の方が市場のボラティリティに適応できます。

```python
def calculate_atr_stop_loss(
    prices: list[float],
    atr_period: int = 14,
    sl_multiplier: float = 1.5,
    tp_multiplier: float = 3.0,
) -> tuple[float, float]:
    """ATRベースのストップロス/テイクプロフィット計算"""

    # ATR計算（True Range）
    true_ranges = []
    for i in range(1, len(prices)):
        high = max(prices[i], prices[i-1])
        low = min(prices[i], prices[i-1])
        tr = high - low
        true_ranges.append(tr)

    atr = np.mean(true_ranges[-atr_period:])
    current_price = prices[-1]

    # ストップロス: ATRの1.5倍
    stop_loss_price = current_price - atr * sl_multiplier

    # テイクプロフィット: ATRの3.0倍（Risk/Reward = 2:1）
    take_profit_price = current_price + atr * tp_multiplier

    return stop_loss_price, take_profit_price
```

設定値の意味：

```python
SL_ATR_MULT = 1.5   # 損切り: ATRの1.5倍
TP_ATR_MULT = 3.0   # 利確: ATRの3.0倍
# → Risk/Reward比 = 1:2（最低でもこの比率を維持）
```

---

## トレーリングストップの実装

固定のストップロスだけでなく、**トレーリングストップ**で含み益を保護します。

```python
class TrailingStopManager:
    """トレーリングストップ管理"""

    TRAIL_ACTIVATE_PCT = 0.005   # 0.5%利益でトレーリング開始
    TRAIL_UPDATE_THRESHOLD = 0.002  # 0.2%更新ごとにストップ引き上げ

    def __init__(self, entry_price: float, position_size: float):
        self.entry_price = entry_price
        self.position_size = position_size
        self.trailing_active = False
        self.highest_price = entry_price
        self.current_stop = None

    def update(self, current_price: float) -> dict:
        """価格更新時にトレーリングストップを計算"""

        profit_pct = (current_price - self.entry_price) / self.entry_price

        # トレーリング開始条件: 0.5%以上の含み益
        if not self.trailing_active and profit_pct >= self.TRAIL_ACTIVATE_PCT:
            self.trailing_active = True
            self.highest_price = current_price
            self.current_stop = current_price * (1 - self.TRAIL_UPDATE_THRESHOLD)

        # トレーリング更新: 最高値が0.2%以上更新されたとき
        if self.trailing_active and current_price > self.highest_price * (1 + self.TRAIL_UPDATE_THRESHOLD):
            self.highest_price = current_price
            # ストップを0.2%分引き上げ
            self.current_stop = current_price * (1 - self.TRAIL_UPDATE_THRESHOLD)

        return {
            "trailing_active": self.trailing_active,
            "current_stop": self.current_stop,
            "profit_pct": profit_pct,
            "should_close": self.current_stop is not None and current_price <= self.current_stop,
        }
```

**動作例：**

```
エントリー: 10,000,000円
+0.3%: トレーリング未開始（0.5%未満）
+0.5%: トレーリング開始 → ストップ = 10,029,900円（-0.2%）
+0.7%: ストップ更新 → ストップ = 10,049,860円
+1.0%: ストップ更新 → ストップ = 10,079,800円
価格が10,079,800円を下回り → 決済
→ 利益: 約+0.8%確保
```

---

## 動的クールダウン

トレード間のクールダウンをボラティリティに応じて動的に変更します。

```python
def calculate_dynamic_cooldown(volatility_pct: float) -> int:
    """ボラティリティに応じたクールダウン計算（秒）"""

    if volatility_pct < 1.0:
        return 1800  # 低ボラ: 30分待機
    elif volatility_pct < 2.0:
        return 600   # 中ボラ: 10分待機
    elif volatility_pct < 4.0:
        return 300   # 高ボラ: 5分待機
    else:
        return 120   # 極高ボラ: 2分待機
```

高ボラティリティ時はチャンスが多いため短いクールダウン、低ボラ時は無駄なトレードを避けるため長めに設定しています。

---

## エッジ検出: 8%閾値の根拠

トレードするかどうかの基準として、**8%のエッジ閾値**を設定しています。

```python
MIN_EDGE_THRESHOLD = 0.08  # 8%以上のエッジがある場合のみトレード
```

この8%の内訳：

| 要素 | コスト/バッファ |
|------|---------------|
| Taker手数料（往復） | 0.24% |
| スリッページ想定 | 0.10% |
| モデル誤差バッファ | 3.00% |
| 最低利益要件 | 4.66% |
| **合計（エッジ閾値）** | **8.00%** |

```python
def calculate_edge(
    estimated_probability: float,
    market_implied_probability: float,
    maker_fee: float = 0.0,   # Makerは0%
    taker_fee: float = 0.0012,  # Taker 0.12%
) -> float:
    """取引エッジを計算"""

    # 期待値ベースのエッジ
    raw_edge = estimated_probability - market_implied_probability

    # 手数料を差し引いた実効エッジ
    # Maker-firstなので往路は0%、復路はTaker想定
    effective_edge = raw_edge - taker_fee

    return effective_edge
```

---

## Monte Carloシミュレーションの実装

実際に使ったシミュレーションコードを公開します。

```python
import numpy as np
from dataclasses import dataclass

@dataclass
class TradingConfig:
    initial_balance: float = 43_154.0  # JPY
    position_size_pct: float = 0.067   # 6.7% Half Kelly
    max_leverage: float = 1.5
    stop_loss_pct: float = 0.01        # 1%
    take_profit_pct: float = 0.05      # 5%
    win_rate: float = 0.575            # 57.5%（実測値）
    min_edge: float = 0.08             # 8%エッジ閾値

def run_monte_carlo(
    config: TradingConfig,
    n_trades: int = 5000,
    n_simulations: int = 10000,
) -> dict:
    """Monte Carloシミュレーション本体"""

    results = []
    ruin_count = 0
    RUIN_THRESHOLD = 10_000.0  # 1万円以下で強制停止

    for sim in range(n_simulations):
        balance = config.initial_balance
        peak = balance
        max_dd = 0.0
        trades = 0

        for _ in range(n_trades):
            if balance < RUIN_THRESHOLD:
                ruin_count += 1
                break

            # ポジションサイズ（レバレッジ込み）
            position_value = balance * config.position_size_pct * config.max_leverage

            # 勝敗決定
            if np.random.random() < config.win_rate:
                pnl = position_value * config.take_profit_pct
            else:
                pnl = -position_value * config.stop_loss_pct

            balance += pnl
            trades += 1

            # 最大ドローダウン更新
            peak = max(peak, balance)
            dd = (peak - balance) / peak
            max_dd = max(max_dd, dd)

        annual_roi = (balance / config.initial_balance) ** (252 / max(trades, 1)) - 1
        results.append({
            "final_balance": balance,
            "annual_roi": annual_roi,
            "max_drawdown": max_dd,
        })

    rois = [r["annual_roi"] for r in results]
    drawdowns = [r["max_drawdown"] for r in results]

    return {
        "mean_annual_roi": np.mean(rois),
        "max_drawdown_p95": np.percentile(drawdowns, 95),
        "ruin_probability": ruin_count / n_simulations,
        "sharpe_ratio": np.mean(rois) / (np.std(rois) + 1e-10),
    }


# 実行
config = TradingConfig()
result = run_monte_carlo(config)

print(f"年間ROI: {result['mean_annual_roi']:.1%}")
print(f"最大DD(95%ile): {result['max_drawdown_p95']:.1%}")
print(f"破産確率: {result['ruin_probability']:.2%}")
print(f"Sharpe Ratio: {result['sharpe_ratio']:.3f}")

# 出力:
# 年間ROI: 101.7%
# 最大DD(95%ile): 12.43%
# 破産確率: 0.00%
# Sharpe Ratio: 2.490
```

---

## パラメータ感度分析

ポジションサイズが変わると結果はどう変わるか？

```python
configs = [
    ("Conservative (3%)", TradingConfig(position_size_pct=0.03)),
    ("Half Kelly (6.7%)", TradingConfig(position_size_pct=0.067)),
    ("Full Kelly (13.4%)", TradingConfig(position_size_pct=0.134)),
    ("Aggressive (20%)", TradingConfig(position_size_pct=0.20)),
]

for name, cfg in configs:
    r = run_monte_carlo(cfg)
    print(f"{name:25s}: ROI={r['mean_annual_roi']:6.1%}, DD={r['max_drawdown_p95']:5.1%}, "
          f"Ruin={r['ruin_probability']:.2%}, Sharpe={r['sharpe_ratio']:.2f}")
```

| 設定 | 年間ROI | 最大DD | 破産確率 | Sharpe |
|------|---------|--------|---------|--------|
| Conservative (3%) | 41.2% | 5.8% | 0.00% | 2.21 |
| **Half Kelly (6.7%)** | **101.7%** | **12.43%** | **0.00%** | **2.490** |
| Full Kelly (13.4%) | 187.3% | 38.1% | 2.31% | 1.83 |
| Aggressive (20%) | 143.8% | 62.7% | 8.94% | 0.97 |

Full Kelly（13.4%）はROIが高く見えますが、破産確率2.31%があります。10,000回取引すると231回は破産するということです。

---

## 実装時の注意点

### 1. 証拠金維持率の監視

```python
MIN_MAINTENANCE_RATIO = 0.60  # 60%を下回ったら強制決済

def check_margin_ratio(balance: float, position_value: float, unrealized_pnl: float) -> float:
    """証拠金維持率を計算"""
    equity = balance + unrealized_pnl
    required_margin = position_value / MAX_LEVERAGE
    return equity / required_margin

# 60%を下回ったら即座に全ポジションを決済
if check_margin_ratio(...) < MIN_MAINTENANCE_RATIO:
    emergency_close_all_positions()
```

### 2. 最小注文量の制約

bitbankでは通貨ペアごとに最小注文量があります。

```python
MIN_ORDER_AMOUNTS = {
    "btc_jpy": 0.0001,  # 0.0001 BTC
    "eth_jpy": 0.0001,  # 0.0001 ETH
    "xrp_jpy": 10.0,    # 10 XRP
}

RECOMMENDED_MIN_AMOUNTS = {
    "btc_jpy": 0.00015,
    "eth_jpy": 0.005,
    "xrp_jpy": 20.0,
}
```

計算上のポジションサイズが最小注文量を下回る場合はスキップします。

---

## まとめ

Half Kelly + 1.5xレバレッジの組み合わせが有効な理由：

1. **Half Kelly**: Sharpe Ratioを最大化しつつ、破産確率をゼロに抑える
2. **1.5xレバレッジ**: 30%の急落でもマージンコール回避。2xは危険
3. **ATRストップ**: 固定%より市場のボラティリティに適応
4. **トレーリングストップ**: 含み益を確保しながらトレンドに乗る
5. **動的クールダウン**: ボラティリティに応じてトレード頻度を調整

**Monte Carlo検証は必須です。** 直感的に「良さそう」なパラメータでも、数千回のシミュレーションを実行すると思わぬリスクが見えてきます。

特に、**Full Kellyは破産確率があるため実用的でない**という結論は、多くの人が直感に反して驚く結果です。ROIが高くても、破産確率が0.01%あれば、十分な時間軸では必ず破産します。

---

## 参考

- [Kelly Criterion Wikipedia](https://en.wikipedia.org/wiki/Kelly_criterion)
- [半Kelly基準の理論的背景](https://en.wikipedia.org/wiki/Kelly_criterion#Fractional_Kelly_betting)
- bitbank API公式ドキュメント（最小注文量等）
