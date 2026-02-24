---
title: "bitbank マルチエージェント取引システムの設計（J.A.R.V.I.S. Iron Legion）"
emoji: "🤖"
type: "tech"
topics: ["仮想通貨", "マルチエージェント", "Claude", "AIエージェント", "bitbank"]
published: true
published_at: "2026-03-01 07:00"
---

> **免責事項**: 本記事で紹介するシステム設計および取引戦略はバックテスト結果に基づくものであり、将来の利益を保証するものではありません。仮想通貨取引は元本割れのリスクを伴います。投資判断は自己責任でお願いします。

## はじめに

「取引ボットを1つのPythonスクリプトで動かす」アプローチには限界があります。

- **スキャン中は取引できない**（シングルスレッドの制約）
- **分析ロジックがクラッシュすると全停止**
- **リスク管理が後回しになる**
- **ログ分析しながら取引できない**

そこで採用したのが、**J.A.R.V.I.S. Iron Legion** パターン——役割に特化した5つのエージェントが並列で動くマルチエージェント取引システムです。

本記事では、bitbank API を使ったBTC/ETH/XRP取引システムをマルチエージェントで設計した実装を解説します。

---

## システム全体像

```
J.A.R.V.I.S. (Orchestrator)
├── Mark-Scanner       価格スキャン（30秒ごと）
├── Mark-Analyzer      エッジ検出（F.R.I.D.A.Y. 連携）
├── Mark-Trader        注文執行（Maker優先）
├── Mark-RiskManager   リスク監視・トレーリングSL
└── Mark-MarginWatcher 証拠金監視（強制決済トリガー）
```

各エージェントは独立したプロセスとして動き、ファイルベースで状態を共有します。

```
data/
├── market/price_data.json     # Scanner → Analyzer
├── signals/signals.json       # Analyzer → Trader
├── orders/orders.json         # Trader → RiskManager
└── risk/margin_status.json    # MarginWatcher → J.A.R.V.I.S.
```

---

## Mark-Scanner: 価格スキャン

**役割**: 30秒ごとにBTC/ETH/XRPの価格データを取得し、`price_data.json` に保存。

```python
import asyncio
import json
import time
from pathlib import Path
from bitbank_client import BitbankClient


class MarkScanner:
    """価格スキャンエージェント — 30秒ごとに3通貨ペアを取得"""

    SCAN_INTERVAL = 30  # 秒
    PAIRS = ["btc_jpy", "eth_jpy", "xrp_jpy"]
    OUTPUT_PATH = Path("data/market/price_data.json")

    def __init__(self, client: BitbankClient):
        self.client = client

    async def scan_once(self) -> dict:
        """全ペアの最新価格を並列取得"""
        tasks = [self._fetch_pair(pair) for pair in self.PAIRS]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        price_data = {}
        for pair, result in zip(self.PAIRS, results):
            if isinstance(result, Exception):
                print(f"[WARN] {pair} fetch failed: {result}")
                continue
            price_data[pair] = result

        return price_data

    async def _fetch_pair(self, pair: str) -> dict:
        ticker = await self.client.get_ticker(pair)
        depth = await self.client.get_depth(pair)
        candlestick = await self.client.get_candlestick(pair, "1min", limit=14)

        return {
            "timestamp": time.time(),
            "pair": pair,
            "last": float(ticker["last"]),
            "best_ask": float(ticker["sell"]),
            "best_bid": float(ticker["buy"]),
            "volume_24h": float(ticker["vol"]),
            "candlestick_1min": candlestick,
            "order_book_depth": depth,
        }

    async def run_forever(self):
        """スキャンループ（無限実行）"""
        while True:
            start = time.time()

            try:
                price_data = await self.scan_once()
                self.OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
                self.OUTPUT_PATH.write_text(json.dumps(price_data, ensure_ascii=False))
                print(f"[Scanner] Scanned {len(price_data)} pairs")
            except Exception as e:
                print(f"[Scanner] ERROR: {e}")

            # 残り時間を待機（スキャンに時間がかかっても30秒間隔を維持）
            elapsed = time.time() - start
            wait = max(0, self.SCAN_INTERVAL - elapsed)
            await asyncio.sleep(wait)
```

**bitbank APIレート制限への対処:**
- Public API: 600リクエスト/5分
- 30秒間隔 × 3ペア = 6リクエスト/30秒 = 60リクエスト/5分（上限の10%）

---

## Mark-Analyzer: エッジ検出

**役割**: 価格データから取引機会を検出。**F.R.I.D.A.Y. (Codex CLI)** と連携してAIベースの分析を行う。

```python
import subprocess
import json
from pathlib import Path


class MarkAnalyzer:
    """エッジ検出エージェント — F.R.I.D.A.Y. 連携"""

    EDGE_THRESHOLD = 0.08     # 8%以上のエッジが必要
    MIN_CONFIDENCE = 0.50     # 信頼度50%以上
    MIN_LIQUIDITY = 10_000    # 最低流動性（JPY換算）

    def analyze(self, price_data: dict) -> list[dict]:
        """全ペアのエッジを分析し、取引シグナルを生成"""
        signals = []

        for pair, data in price_data.items():
            edge = self._calculate_edge(pair, data)
            if edge is None:
                continue

            if edge["edge"] >= self.EDGE_THRESHOLD and edge["confidence"] >= self.MIN_CONFIDENCE:
                signals.append({
                    "pair": pair,
                    "direction": edge["direction"],
                    "edge": edge["edge"],
                    "confidence": edge["confidence"],
                    "entry_price": data["best_ask"] if edge["direction"] == "buy" else data["best_bid"],
                    "timestamp": data["timestamp"],
                })

        return signals

    def _calculate_edge(self, pair: str, data: dict) -> dict | None:
        """F.R.I.D.A.Y. を使ってエッジを計算"""

        # 流動性チェック
        if data["volume_24h"] * data["last"] < self.MIN_LIQUIDITY:
            return None

        # ATR計算（ボラティリティ推定）
        candles = data["candlestick_1min"]
        if len(candles) < 14:
            return None

        atr = self._calculate_atr(candles)

        # F.R.I.D.A.Y. に分析を委譲
        prompt = f"""
Analyze trading edge for {pair}:
- Current price: {data['last']}
- Best ask: {data['best_ask']}
- Best bid: {data['best_bid']}
- ATR (14-period): {atr:.4f}
- Volume 24h: {data['volume_24h']}
- Candlestick trend (last 5): {[c['close'] for c in candles[-5:]]}

Return JSON: {{"direction": "buy"|"sell"|"none", "edge": 0.0-1.0, "confidence": 0.0-1.0, "reason": "..."}}
Edge = estimated probability advantage over market implied price.
Return "none" if edge < 8%.
"""
        result = self._call_friday(prompt)
        return result

    def _call_friday(self, prompt: str) -> dict | None:
        """F.R.I.D.A.Y. (Codex CLI) を呼び出す"""
        try:
            proc = subprocess.run(
                ["codex", "exec", "--sandbox", "read-only", "--full-auto", "-"],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if proc.returncode != 0:
                return None

            # JSON抽出
            output = proc.stdout.strip()
            start = output.rfind("{")
            end = output.rfind("}") + 1
            if start < 0 or end <= start:
                return None

            return json.loads(output[start:end])

        except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
            return None

    def _calculate_atr(self, candles: list[dict], period: int = 14) -> float:
        """ATR計算"""
        trs = []
        for i in range(1, len(candles)):
            high = max(float(candles[i]["high"]), float(candles[i-1]["close"]))
            low = min(float(candles[i]["low"]), float(candles[i-1]["close"]))
            trs.append(high - low)

        return sum(trs[-period:]) / min(len(trs), period)
```

**エッジ閾値8%の根拠:**

| コスト要素 | 割合 |
|-----------|------|
| Taker手数料（往復） | 0.24% |
| スリッページ | 0.10% |
| モデル誤差バッファ | 3.00% |
| 最低利益要件 | 4.66% |
| **合計** | **8.00%** |

---

## Mark-Trader: Maker優先注文執行

**役割**: 承認済みシグナルに対してMaker注文を発行し、手数料を最小化する。

```python
class MarkTrader:
    """注文執行エージェント — Maker優先戦略"""

    MAKER_TIMEOUT = 45    # 45秒待機
    MAKER_OFFSET = 0.0005  # 市場価格から0.05%オフセット

    async def execute_signal(self, signal: dict, balance: float) -> dict | None:
        """シグナルに従い注文を執行"""

        pair = signal["pair"]
        direction = signal["direction"]

        # ポジションサイズ計算（Half Kelly + 1.5xレバレッジ）
        position_value = balance * 0.067 * 1.5
        amount = self._calculate_amount(pair, position_value, signal["entry_price"])

        if amount is None:
            print(f"[Trader] {pair}: amount below minimum, skip")
            return None

        # Step 1: Maker注文（手数料0%）
        maker_price = self._calculate_maker_price(pair, direction, signal["entry_price"])

        order = await self._place_order(
            pair=pair,
            side=direction,
            amount=amount,
            price=maker_price,
            order_type="limit",
        )

        print(f"[Trader] Maker order placed: {pair} {direction} {amount} @ {maker_price}")

        # 45秒待機
        filled = await self._wait_for_fill(order["order_id"], timeout=self.MAKER_TIMEOUT)

        if filled:
            print(f"[Trader] Maker order filled: {order['order_id']}")
            return order

        # Step 2: Makerがタイムアウト → Takerにフォールバック
        await self._cancel_order(order["order_id"])
        print(f"[Trader] Maker timeout, switching to Taker")

        taker_order = await self._place_order(
            pair=pair,
            side=direction,
            amount=amount,
            price=None,  # 成行注文
            order_type="market",
        )

        print(f"[Trader] Taker order placed: {taker_order['order_id']}")
        return taker_order

    def _calculate_maker_price(
        self,
        pair: str,
        direction: str,
        market_price: float,
    ) -> float:
        """Maker注文価格（わずかに有利な価格を指定）"""
        if direction == "buy":
            # 市場価格より0.05%安く買い指値
            return market_price * (1 - self.MAKER_OFFSET)
        else:
            # 市場価格より0.05%高く売り指値
            return market_price * (1 + self.MAKER_OFFSET)

    def _calculate_amount(
        self,
        pair: str,
        position_value: float,
        price: float,
    ) -> float | None:
        """注文量を計算（最小注文量チェック付き）"""
        MIN_AMOUNTS = {
            "btc_jpy": 0.0001,
            "eth_jpy": 0.0001,
            "xrp_jpy": 10.0,
        }
        RECOMMENDED = {
            "btc_jpy": 0.00015,
            "eth_jpy": 0.005,
            "xrp_jpy": 20.0,
        }

        amount = position_value / price

        min_amount = MIN_AMOUNTS.get(pair, 0)
        if amount < min_amount:
            return None

        # 推奨最小量との比較
        recommended = RECOMMENDED.get(pair, 0)
        return max(amount, recommended)
```

**Maker優先の効果:**

| 注文タイプ | 手数料 | 年間コスト（1日10トレード想定） |
|-----------|--------|-------------------------------|
| Taker（成行） | 0.12% | 約43万円（年間） |
| Maker（指値） | 0.00% | 0円 |

45秒の待機コストと引き換えに、手数料を完全に削減できます。

---

## Mark-RiskManager: リスク管理

**役割**: 全ポジションのリスクを監視し、トレーリングストップを管理する。

```python
class MarkRiskManager:
    """リスク管理エージェント"""

    STOP_LOSS_PCT = 0.01       # 1%固定ストップ
    TAKE_PROFIT_PCT = 0.05     # 5%テイクプロフィット
    SL_ATR_MULT = 1.5          # ATRベースSL
    TP_ATR_MULT = 3.0          # ATRベースTP
    TRAIL_ACTIVATE = 0.005     # トレーリング開始: +0.5%
    TRAIL_UPDATE = 0.002       # トレーリング更新: +0.2%

    def check_positions(
        self,
        positions: list[dict],
        current_prices: dict,
    ) -> list[dict]:
        """全ポジションをチェックし、決済シグナルを返す"""

        close_signals = []

        for pos in positions:
            pair = pos["pair"]
            current_price = current_prices.get(pair, {}).get("last")
            if current_price is None:
                continue

            entry_price = pos["entry_price"]
            direction = pos["direction"]

            # PnL計算
            if direction == "buy":
                pnl_pct = (current_price - entry_price) / entry_price
            else:
                pnl_pct = (entry_price - current_price) / entry_price

            # ストップロスチェック
            if pnl_pct <= -self.STOP_LOSS_PCT:
                close_signals.append({
                    "position_id": pos["id"],
                    "reason": "stop_loss",
                    "pnl_pct": pnl_pct,
                })
                continue

            # テイクプロフィットチェック
            if pnl_pct >= self.TAKE_PROFIT_PCT:
                close_signals.append({
                    "position_id": pos["id"],
                    "reason": "take_profit",
                    "pnl_pct": pnl_pct,
                })
                continue

            # トレーリングストップチェック
            trailing_result = self._check_trailing_stop(pos, current_price, pnl_pct)
            if trailing_result["should_close"]:
                close_signals.append({
                    "position_id": pos["id"],
                    "reason": "trailing_stop",
                    "pnl_pct": pnl_pct,
                })

        return close_signals

    def _check_trailing_stop(
        self,
        pos: dict,
        current_price: float,
        pnl_pct: float,
    ) -> dict:
        """トレーリングストップ判定"""

        # トレーリング未開始 & 利益0.5%未満
        if not pos.get("trailing_active") and pnl_pct < self.TRAIL_ACTIVATE:
            return {"should_close": False}

        # トレーリング開始
        if not pos.get("trailing_active") and pnl_pct >= self.TRAIL_ACTIVATE:
            pos["trailing_active"] = True
            pos["trailing_stop_price"] = current_price * (1 - self.TRAIL_UPDATE)
            return {"should_close": False}

        # 最高値更新
        direction = pos["direction"]
        if direction == "buy":
            if current_price > pos.get("peak_price", current_price):
                pos["peak_price"] = current_price
                pos["trailing_stop_price"] = current_price * (1 - self.TRAIL_UPDATE)

            # ストップに達したか
            return {"should_close": current_price <= pos["trailing_stop_price"]}

        return {"should_close": False}
```

---

## Mark-MarginWatcher: 証拠金監視

**役割**: 証拠金維持率を常時監視し、強制決済を実行する最重要エージェント。

```python
class MarkMarginWatcher:
    """証拠金監視エージェント — 最高優先度"""

    MIN_MAINTENANCE_RATIO = 0.60   # 60%を下回ったら強制決済
    WARN_RATIO = 0.75              # 75%でワーニング
    CHECK_INTERVAL = 30            # 30秒ごとにチェック

    async def run_forever(self, client: BitbankClient):
        """監視ループ（永続実行）"""
        while True:
            try:
                status = await self._check_margin(client)
                self._write_status(status)

                if status["margin_ratio"] < self.MIN_MAINTENANCE_RATIO:
                    print(f"[MarginWatcher] CRITICAL: ratio={status['margin_ratio']:.1%}")
                    await self._emergency_close_all(client)

                elif status["margin_ratio"] < self.WARN_RATIO:
                    print(f"[MarginWatcher] WARNING: ratio={status['margin_ratio']:.1%}")

            except Exception as e:
                print(f"[MarginWatcher] ERROR: {e}")

            await asyncio.sleep(self.CHECK_INTERVAL)

    async def _check_margin(self, client: BitbankClient) -> dict:
        """証拠金状況を取得"""
        margin_info = await client.get_margin_info()

        equity = float(margin_info["equity"])              # 純資産
        used_margin = float(margin_info["used_margin"])    # 使用中証拠金
        unrealized_pnl = float(margin_info["unrealized_pnl"])

        if used_margin == 0:
            margin_ratio = 1.0
        else:
            margin_ratio = equity / used_margin

        return {
            "margin_ratio": margin_ratio,
            "equity": equity,
            "used_margin": used_margin,
            "unrealized_pnl": unrealized_pnl,
            "timestamp": time.time(),
        }

    async def _emergency_close_all(self, client: BitbankClient):
        """緊急全決済（Taker注文で即座に執行）"""
        positions = await client.get_active_positions()

        for pos in positions:
            try:
                # 反対方向の成行注文で即決済
                close_side = "sell" if pos["side"] == "buy" else "buy"
                await client.place_order(
                    pair=pos["pair"],
                    side=close_side,
                    amount=pos["amount"],
                    order_type="market",
                )
                print(f"[MarginWatcher] Emergency closed: {pos['pair']} {pos['amount']}")
            except Exception as e:
                print(f"[MarginWatcher] FAILED to close {pos['pair']}: {e}")
```

**なぜ60%を閾値にするのか:**

```
bitbank清算ライン: 証拠金維持率 50%
安全バッファ:     +10% (価格変動への余裕)
監視閾値:         60%
```

50%で清算される前に、60%で自分から決済することで、最悪の強制清算を回避します。

---

## J.A.R.V.I.S. Orchestrator: 全体調整

```python
import asyncio
from pathlib import Path


class JARVISOrchestrator:
    """全エージェントを統括するオーケストレーター"""

    EMERGENCY_HALT_CONDITIONS = {
        "min_balance": 10_000,         # 1万円以下で停止
        "daily_loss_max": 0.15,        # 日次15%損失で停止
        "consecutive_losses_max": 10,   # 連続10連敗で一時停止
    }

    async def run(self):
        """全エージェントを並列起動"""
        print("[J.A.R.V.I.S.] Starting Iron Legion...")

        # 各エージェントを並列実行
        tasks = [
            asyncio.create_task(self.scanner.run_forever(), name="Scanner"),
            asyncio.create_task(self.analyzer.run_forever(), name="Analyzer"),
            asyncio.create_task(self.trader.run_forever(), name="Trader"),
            asyncio.create_task(self.risk_manager.run_forever(), name="RiskManager"),
            asyncio.create_task(self.margin_watcher.run_forever(self.client), name="MarginWatcher"),
        ]

        # いずれかが失敗した場合の処理
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)

        for task in done:
            if task.exception():
                print(f"[J.A.R.V.I.S.] Agent failed: {task.get_name()}: {task.exception()}")

        # 残タスクをキャンセル
        for task in pending:
            task.cancel()
```

---

## 動的クールダウン

ボラティリティに応じてトレード頻度を調整します。

```python
def calculate_cooldown(volatility_pct: float) -> int:
    """ボラティリティ → クールダウン秒数"""
    if volatility_pct < 1.0:
        return 1800   # 低ボラ: 30分
    elif volatility_pct < 2.0:
        return 600    # 中ボラ: 10分
    elif volatility_pct < 4.0:
        return 300    # 高ボラ: 5分
    else:
        return 120    # 極高ボラ: 2分
```

高ボラ時はチャンスが多く、頻繁にスキャンしても意味があります。低ボラ時は無駄なエントリーを減らすため長い待機を設定します。

---

## マルチエージェントの実際のメリット

シングルスクリプトと比較した実際の改善効果：

| 問題 | シングルスクリプト | マルチエージェント |
|------|-------------------|-------------------|
| スキャン中の取引 | 不可（逐次処理） | 可能（並列） |
| エージェント障害 | 全停止 | 影響範囲を局所化 |
| 証拠金監視 | 取引後のみ | 常時30秒ごと |
| デバッグ | 全ログが混在 | エージェント別に分離 |
| スケールアップ | コード全体の変更 | 対象エージェントのみ |

**最大の利点は障害分離です。** Analyzerがクラッシュしても、MarginWatcherは動き続けます。ポジションを持っている状態で監視が止まるのは致命的なので、この分離は非常に重要です。

---

## 緊急停止条件

```python
HALT_CONDITIONS = [
    ("残高 < 1万円", lambda s: s.balance < 10_000),
    ("日次損失 > 15%", lambda s: s.daily_loss > 0.15),
    ("週次損失 > 25%", lambda s: s.weekly_loss > 0.25),
    ("証拠金維持率 < 60%", lambda s: s.margin_ratio < 0.60),
    ("連続10連敗", lambda s: s.consecutive_losses >= 10),
    ("APIエラー率 > 50%", lambda s: s.api_error_rate > 0.50),
]
```

いずれかの条件が満たされると、全エージェントに停止シグナルを送り、全ポジションを決済してから終了します。

---

## まとめ

J.A.R.V.I.S. Iron Legion パターンの要点：

1. **役割分離**: Scanner/Analyzer/Trader/RiskManager/MarginWatcher の5役割
2. **障害分離**: 1つのエージェントがクラッシュしても他は動き続ける
3. **Maker優先**: 手数料0%のMaker注文を45秒待機、タイムアウト後にTakerへ
4. **証拠金常時監視**: 30秒ごとにチェック、60%未満で緊急決済
5. **動的クールダウン**: ボラティリティに応じて120〜1800秒に自動調整

シングルスクリプトで「動くボット」を作るのは簡単ですが、「止まらないボット」を作るにはマルチエージェントアーキテクチャが不可欠でした。

特に、**MarginWatcherを独立したエージェントにした判断**は正しかったと思います。マージンコールは突発的に発生し、他のエージェントが何をしていても即座に対応する必要があるからです。

---

## 関連記事

- [Half Kelly + 1.5xレバレッジのMonte Carlo最適化](/articles/half-kelly-monte-carlo-crypto-optimization)
- [VERONICA: Llama 3.2:3bでリアルタイム監視をゼロコストで動かす](/articles/veronica-llama-realtime-monitoring)
