---
title: "VERONICA: Llama 3.2:3bでリアルタイム監視をゼロコストで動かす"
emoji: "🤖"
type: "tech"
topics: ["llm", "llama", "ollama", "python", "ai"]
published: true
published_at: "2026-02-26 07:00"
---

## TL;DR

- Llama 3.2:3b（2.0GB VRAM）をlocalhost:11434（Ollama）で動かす
- 26.93 req/s、キャッシュ込みで1347 req/sという圧倒的スループット
- 追加コストゼロで98%キャッシュヒット率、16.5msの平均レイテンシを実現
- Polymarket取引ボットで395回のリアルタイム判定に使用中

---

## 背景：「大きなモデルが必要か」という問い

仮想通貨・予測市場の取引ボットを作っていると、1分間に何十回もAIに判断させる場面が出てくる。

最初はClaude（Sonnet）で全部やっていた。品質は高い。でもコストがかさむし、レイテンシも100ms以上ある。高頻度の監視タスクには明らかにオーバースペック。

「リスクゲートのL1〜L6は単純なルールベース。`price > threshold`みたいな判断に最上位モデルを使う必要があるか？」

答えは明らかにNo。

---

## VERONICAとは

私のAIエージェントシステム（J.A.R.V.I.S.）の中で、リアルタイム監視を担当するエージェント。MCUのVERONICA（Iron Man 3）から命名。

```
J.A.R.V.I.S. AIシステム
├── J.A.R.V.I.S. (Sonnet) — オーケストレーション
├── F.R.I.D.A.Y. (Codex CLI) — コード生成
├── Karen (Gemini CLI) — リサーチ
├── VERONICA (Llama 3.2:3b) — リアルタイム監視 ← 本記事
└── E.D.I.T.H. (Opus) — 最終手段（制限付き）
```

---

## セットアップ

### Ollamaのインストールと起動

```bash
# Ollamaをインストール（https://ollama.com）
# Windows/Mac/Linux対応

# モデルをダウンロード
ollama pull llama3.2:3b

# 起動確認
curl -s http://localhost:11434/api/tags | grep llama3.2
```

### VRAMの確認

```
RTX 5090 (32GB VRAM) での確認:
- Llama 3.2:3b: 2.0GB VRAM使用
- 残り30GB: 他の作業に自由に使える
```

小型モデルなので、ゲーミングGPU（8GB以上）でも余裕で動く。

---

## 実装

### Python wrapper

```python
import requests
from functools import lru_cache
from typing import Literal

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3.2:3b"

def _call_veronica(prompt: str, system: str = "") -> str:
    """VERONICAへの基本呼び出し"""
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "options": {
            "temperature": 0.0,  # 決定的な出力
            "num_predict": 10,   # 短い回答で高速化
        }
    }
    response = requests.post(OLLAMA_URL, json=payload, timeout=5.0)
    return response.json()["response"].strip()


def yes_no(question: str, context: str = "") -> bool:
    """Yes/No質問への回答"""
    system = "Answer only YES or NO. Nothing else."
    prompt = f"Context: {context}\n\nQuestion: {question}" if context else question

    result = _call_veronica(prompt, system)
    return result.upper().startswith("YES")


def edge_detection(
    price: float,
    estimated_prob: float,
    market_prob: float,
    threshold: float = 0.08
) -> dict:
    """エッジ検出（fee-aware）"""
    edge = abs(estimated_prob - market_prob)
    direction = "BUY" if estimated_prob > market_prob else "SELL"

    return {
        "has_edge": edge >= threshold,
        "edge": edge,
        "direction": direction,
        "confidence": min(edge / threshold, 1.0)
    }


def sentiment(text: str) -> Literal["positive", "negative", "neutral"]:
    """センチメント分析"""
    system = "Classify as: positive, negative, or neutral. One word only."
    result = _call_veronica(text, system).lower()

    if "positive" in result:
        return "positive"
    elif "negative" in result:
        return "negative"
    return "neutral"


def classify(text: str, categories: list[str]) -> str:
    """テキスト分類"""
    cats = ", ".join(categories)
    system = f"Classify into ONE of: {cats}. Reply with the category name only."
    result = _call_veronica(text, system)

    # 最も近いカテゴリを返す
    result_lower = result.lower()
    for cat in categories:
        if cat.lower() in result_lower:
            return cat
    return categories[0]  # fallback
```

### キャッシュ最適化

同じ質問を繰り返すケースが多い（「BTC価格は閾値を超えているか」など）ので、キャッシュが効果絶大。

```python
from functools import lru_cache

@lru_cache(maxsize=1000)
def yes_no_cached(question: str, context: str = "") -> bool:
    return yes_no(question, context)
```

実運用では**98%のキャッシュヒット率**を記録。1347 req/sという数字はほぼキャッシュのおかげ。

---

## ベンチマーク結果

```
Llama 3.2:3b (Ollama localhost:11434)
--------------------------------------
スループット（直接呼び出し）: 26.93 req/s
スループット（キャッシュ込み）: 1347 req/s
VRAM使用量: 2.0 GB
平均レイテンシ: 37ms（直接）/ 0.7ms（キャッシュ）

比較対象:
- Claude Sonnet: ~150ms, コスト有
- GPT-4o mini: ~80ms, コスト有
- VERONICA: 37ms, コストゼロ ← 今回
```

---

## 実際の使用例：Polymarket取引ボット

実際のボットでは以下のように使っている。

```python
# リスクゲートL1-L6: VERONICAで高速処理
def risk_gate_l1_to_l6(signal: Signal) -> bool:
    # L1: 最小エッジ確認
    if signal.edge < MIN_EDGE_THRESHOLD:
        return False

    # L2: 流動性確認（ルールベース、AI不要）
    if signal.liquidity < MIN_LIQUIDITY:
        return False

    # L3: VERONICAでセンチメント確認
    title_sentiment = veronica.sentiment(signal.market_title)
    if title_sentiment == "negative" and signal.direction == "BUY":
        return False

    # L4-L6: その他ルールベースチェック
    # ...

    return True

# リスクゲートL7: J.A.R.V.I.S. (Sonnet) で複雑な判断
def risk_gate_l7(signal: Signal) -> bool:
    # ここだけSonnetを使う（高コストだが品質重視）
    return jarvis.evaluate_complex_signal(signal)
```

### 実績

Polymarket取引ボットの1時間運用データ：

```
総呼び出し回数: 395回
キャッシュヒット: 391回（99.2%）
平均レイテンシ: 16.5ms
追加コスト: ¥0
```

395回の判断をClaude Sonnetで行っていたら...Claude Pro MAXでも使用枠を消費していただろう。

---

## 品質について

「3bパラメータで品質は大丈夫か」という懸念はある。

答えは**タスクによる**。

**VERONICAが得意なこと（精度高）:**
- Yes/No質問（専用プロンプトで100%近い精度）
- シンプルな分類（カテゴリ数が少ない場合）
- ルールベースの判断補助

**VERONICAが苦手なこと（Sonnetに委譲）:**
- 複雑な推論が必要な判断
- 文脈が長い場合
- 微妙なニュアンスの解釈

プロンプトを`"Answer only YES or NO. Nothing else."`のように極力シンプルにすることで、品質問題をかなり軽減できる。

---

## ヘルスチェック統合

```python
def check_veronica_health() -> bool:
    """VERONICA起動確認"""
    try:
        response = requests.get(
            "http://localhost:11434/api/tags",
            timeout=2.0
        )
        tags = response.json()
        models = [m["name"] for m in tags.get("models", [])]
        return any("llama3.2" in m for m in models)
    except Exception:
        return False

# 使用前に確認
if not check_veronica_health():
    print("VERONICA停止中。Sonnetにフォールバックします。")
    # Sonnetで代替処理
```

---

## コスト比較

月間100万回の判断が必要なシステムを仮定：

| モデル | レイテンシ | コスト（月） | スループット |
|--------|-----------|------------|------------|
| Claude Sonnet | ~150ms | 数万円〜 | 制限あり |
| GPT-4o mini | ~80ms | 数千円〜 | 制限あり |
| Llama 3.2:3b | 37ms | ¥0* | 無制限 |

*電気代（RTX 5090の消費電力分）のみ

高頻度・低複雑度のタスクにLlama 3.2:3bを使うことで、コストを大幅に削減しながらレイテンシも改善できる。

---

## まとめ

VERONICAパターンの核心：

**「すべての判断に最上位モデルを使う必要はない」**

タスクの複雑度に応じてモデルを使い分ける。ルールで解ける問題にAIを使わない。AIを使うなら最小コストのモデルで始める。

Llama 3.2:3bは「AIを使うほどでもないがコードに落とすほど複雑」なタスクの絶妙な解決策。ローカル動作・ゼロコスト・十分な精度の三拍子が揃っている。

---

## 関連記事

- [J.A.R.V.I.S. Iron Legion: マルチエージェント並列コーディング実践](#)
- [F.R.I.D.A.Y.: Codex CLIを全コードタスクの第一選択にした理由](#)
