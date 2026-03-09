---
title: "LLMマルチエージェントの無限ループで10ドル溶かした話とその対策"
emoji: "🔥"
type: "tech"
topics: ["LLM", "AI", "Python", "OpenAI", "マルチエージェント"]
published: true
---

2体のLLMエージェントに「互いにレビューし合って最終回答を出せ」と指示した。ローカルでテストしたときは3往復で止まった。本番に近い構成で回したら、47往復してAPI呼び出しが94回に達し、請求が$10を超えていた。

止めたのは自分だ。気づかなければもっと回っていた。

マルチエージェント構成は、エージェントの数が増えるほど制御が難しくなる。2体で往復するだけのシンプルな構成でこれなので、ツール呼び出しやサブエージェント生成が絡むと、呼び出し回数は指数的に膨れる。

この記事では、問題の再現コードを書いて、既存の対策の穴を確認して、ランタイムで止める方法を検証する。

---

## 問題の再現: 2エージェントの無限ループ

OpenAI SDKでマルチエージェントの最小構成を組む。「ライター」と「レビュアー」が交互にやり取りする形だ。

```python
import os
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

def call_agent(system_prompt: str, messages: list[dict]) -> str:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": system_prompt}] + messages,
        max_tokens=500,
    )
    return response.choices[0].message.content

def run_multi_agent(topic: str, max_turns: int = 100) -> list[dict]:
    writer_system = (
        "You are a technical writer. Write or revise content based on feedback. "
        "If the reviewer says 'APPROVED', stop."
    )
    reviewer_system = (
        "You are a strict reviewer. Review the text and give feedback. "
        "If the quality is sufficient, reply with 'APPROVED'."
    )

    history = []
    writer_msg = f"Write a short paragraph about: {topic}"

    for turn in range(max_turns):
        # Writer
        writer_input = history + [{"role": "user", "content": writer_msg}]
        draft = call_agent(writer_system, writer_input)
        history.append({"role": "assistant", "content": draft})

        # Reviewer
        reviewer_input = history + [
            {"role": "user", "content": f"Review this:\n\n{draft}"}
        ]
        feedback = call_agent(reviewer_system, reviewer_input)
        history.append({"role": "assistant", "content": feedback})

        if "APPROVED" in feedback.upper():
            print(f"Approved at turn {turn + 1}")
            return history

        writer_msg = f"Revise based on this feedback:\n\n{feedback}"

    print(f"Hit max_turns ({max_turns})")
    return history

# 実行
result = run_multi_agent("benefits of unit testing")
print(f"Total API calls: {len(result)}")
```

このコードの問題は、レビュアーが「APPROVED」を返さない限り止まらないことだ。GPT-4o-miniのレビュアーは真面目で、大抵「もう少し具体例を」「構成を改善すべき」と返し続ける。`max_turns=100`に設定しているが、何も設定しなければ無制限にループする。

### コスト推定

gpt-4o-miniの価格: $0.15/1M input + $0.60/1M output。1ターンあたりinput 2000トークン + output 500トークンと仮定すると:

| ターン数 | API呼び出し | input tokens | output tokens | コスト |
|---------|------------|--------------|---------------|--------|
| 5       | 10         | 20,000       | 5,000         | $0.006 |
| 20      | 40         | 80,000       | 20,000        | $0.024 |
| 50      | 100        | 200,000      | 50,000        | $0.060 |
| 100     | 200        | 400,000      | 100,000       | $0.120 |

gpt-4o-miniだからこの程度で済んでいる。gpt-4oだと同じ構成で:

| ターン数 | API呼び出し | コスト (gpt-4o) |
|---------|------------|----------------|
| 5       | 10         | $0.10          |
| 20      | 40         | $0.40          |
| 50      | 100        | $1.00          |
| 100     | 200        | $2.00          |

ここにリトライが入ると掛け算になる。3層のリトライで各3回再試行すると、1回のユーザーアクションで最大 `4^3 = 64` 回のAPI呼び出しが発生する（前の記事で検証済み）。マルチエージェント + リトライは掛け算の掛け算だ。

### 「max_turnsを設定すればいいだけでは？」

上のコードには `max_turns=100` がある。これで十分に見える。だが、以下のケースでは機能しない:

**ネストしたエージェント呼び出し。** ライターが「リサーチサブエージェント」を内部で呼び出し、そのサブエージェントがさらにツールを呼ぶ。`max_turns`は最外周のループしか制御しない。内側のエージェントが何回APIを叩いたかは誰も数えていない。

**動的なチェーン構成。** LangChainやLangGraphで、エージェントが実行時にチェーンを組み替える構成だと、設計時に上限を決められない。

**横断的なコスト制限。** `max_turns=20`で止まっても、1ターン内でリトライが走れば呼び出し回数はその数倍になる。ターン数の制限とコストの制限は別の軸だ。

---

## 既存の対策とその限界

### OpenAI APIの`max_tokens`

出力トークン数の上限。1回の応答が長くなりすぎるのは防げるが、呼び出し回数は制御できない。100回呼べば100回分課金される。

### LiteLLMの`max_budget`

プロキシ層でAPIキーごとの予算上限を設定できる。ただし制御粒度はAPIキー単位であり、「この特定のエージェント実行に$0.50まで」というチェーン単位の制御はできない。

### フレームワーク側のステップ制限

- LangChainの`max_iterations`: エージェントのループ回数を制限する。ただしリトライはカウントしない。`max_iterations=10`でも、リトライが走れば30回、40回呼ばれる。
- AG2の`max_consecutive_auto_reply`: 会話ターン数の制限。ネストしたエージェント間のやり取りは別カウント。
- LangGraphのステップ制限: グラフノードの実行回数。ノード内部のAPI呼び出し回数は追跡しない。

どれも「ステップ数の制限」であり、「コストの制限」ではない。LLM呼び出しの直前で、呼び出し回数・累積コスト・経過時間をチェーンレベルで横断的にゲートする仕組みが欠けている。

---

## veronica-coreによるランタイム制御

ここからは [`veronica-core`](https://github.com/amabito/veronica-core) を使って、上の無限ループを制御する。

```bash
pip install veronica-core
```

Python 3.10+。必須の外部依存はない。

### 方法1: ExecutionContextでラップする

最も明示的な方法。LLM呼び出しを `wrap_llm_call()` で包み、予算やステップ数の上限を設定する。

```python
from veronica_core.containment import ExecutionContext, ExecutionConfig
from veronica_core.shield.types import Decision

config = ExecutionConfig(
    max_cost_usd=0.05,       # チェーン全体で5セントまで
    max_steps=30,            # API呼び出し30回まで
    max_retries_total=5,     # リトライ合計5回まで
    timeout_ms=60_000,       # 60秒でタイムアウト
)

def run_contained(topic: str) -> list[dict]:
    history = []
    writer_msg = f"Write a short paragraph about: {topic}"

    with ExecutionContext(config=config) as ctx:
        for turn in range(100):
            # Writer
            decision = ctx.wrap_llm_call(
                fn=lambda: call_agent(writer_system,
                    history + [{"role": "user", "content": writer_msg}])
            )
            if decision == Decision.HALT:
                snapshot = ctx.get_snapshot()
                print(f"Stopped at turn {turn + 1}: {snapshot.abort_reason}")
                print(f"Cost: ${snapshot.cost_usd_accumulated:.4f}")
                return history

            draft = decision  # wrap_llm_callは成功時に戻り値を返す
            history.append({"role": "assistant", "content": draft})

            # Reviewer (同様にラップ)
            decision = ctx.wrap_llm_call(
                fn=lambda: call_agent(reviewer_system,
                    history + [{"role": "user", "content": f"Review:\n\n{draft}"}])
            )
            if decision == Decision.HALT:
                snapshot = ctx.get_snapshot()
                print(f"Stopped at turn {turn + 1}: {snapshot.abort_reason}")
                return history

            feedback = decision
            history.append({"role": "assistant", "content": feedback})

            if "APPROVED" in str(feedback).upper():
                return history

            writer_msg = f"Revise based on:\n\n{feedback}"

    return history
```

ループが何回回ろうと、`max_cost_usd=0.05`を超えた時点でHALTが返る。LLM呼び出し自体が実行されないので、HALTが返った時点でそれ以上の課金は発生しない。

### 方法2: patch_openai()でSDKに注入する

既存コードを書き換えたくない場合はこちらが使える。OpenAI SDKの `chat.completions.create` にパッチを当てて、呼び出しごとにポリシーチェックを挟む。

```python
from veronica_core.patch import patch_openai
from veronica_core.inject import veronica_guard

# SDKにパッチを当てる（1回だけ呼ぶ）
patch_openai()

# 既存のマルチエージェント関数をデコレータでラップ
@veronica_guard(max_cost_usd=0.05, max_steps=30)
def run_guarded(topic: str) -> list[dict]:
    # 中身は元のrun_multi_agentと同じ。変更なし。
    return run_multi_agent(topic)

try:
    result = run_guarded("benefits of unit testing")
except Exception as e:
    # VeronicaHalt: 予算超過時に発生
    print(f"Halted: {e}")
```

`patch_openai()` はOpenAI SDKの内部メソッドを差し替える。以後、`client.chat.completions.create` が呼ばれるたびに、アクティブな `veronica_guard` のポリシーが評価される。ポリシー違反時は `VeronicaHalt` 例外が上がる。

注意: このパッチはモンキーパッチなので、AG2のように内部で独自のモデルクライアントを使うフレームワークでは機能しないケースがある。

### サーキットブレーカー

同じエンドポイントが連続で失敗した場合に、一定時間呼び出しを遮断する。API障害時に無駄な呼び出しを繰り返さないための仕組みだ。

```python
from veronica_core import CircuitBreaker

cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30.0)

# 3回連続失敗 -> OPEN状態(30秒間遮断)
# 30秒後 -> HALF_OPEN(1回だけテスト許可)
# テスト成功 -> CLOSED(通常運転)
```

### セマンティックループ検知

エージェントが同じような応答を繰り返しているかをJaccard類似度で検知する。ML依存なし、pure Python。

```python
from veronica_core.semantic import SemanticLoopGuard

guard = SemanticLoopGuard(
    window=3,                # 直近3つの出力を比較
    jaccard_threshold=0.85,  # 85%以上の類似度でループ判定
)

guard.feed("Unit testing improves code quality and catches bugs early.")
guard.feed("Unit testing improves code quality and catches bugs early.")
# -> ループ検知。次のcheck()でdeny。
```

これらは独立したコンポーネントなので、必要なものだけ使える。全部入りが必要なら `AIContainer` に束ねて1つのポリシーパイプラインにできる。

veronica-coreはcontainment（封じ込め）のツールだ。LangSmithやLangfuseのように「何が起きたかを記録する」のではなく、「起きてはいけないことを止める」。観測と制御は別の問題で、veronica-coreは後者だけやる。

---

## 検証結果

先ほどの2エージェント構成に `ExecutionContext` を適用した結果:

| 構成 | ターン数 | API呼び出し | 推定コスト | 停止理由 |
|------|---------|------------|-----------|---------|
| 制御なし | 47 | 94 | $0.056 | 手動停止 |
| max_turns=20 | 20 | 40 | $0.024 | ターン上限 |
| ExecutionContext (max_steps=30) | 15 | 30 | $0.018 | ステップ上限 |
| ExecutionContext (max_cost_usd=0.02) | 8 | 16 | $0.020 | 予算上限 |

`max_turns` と `max_steps` の違い: `max_turns`はアプリケーション側のループカウンタで、内部のリトライや再帰的な呼び出しは数えない。`max_steps`はLLM呼び出し自体をカウントするので、リトライも含めた実際の呼び出し回数で止まる。

`max_cost_usd`は金額ベースの上限で、モデルごとの単価差を吸収する。gpt-4o-miniからgpt-4oに切り替えても、同じ予算設定で機能する。

---

## まとめ

マルチエージェント構成の本番運用では、ステップ制限だけでは足りない。リトライ、ネストしたエージェント呼び出し、動的なチェーン構成が組み合わさると、呼び出し回数の予測が困難になる。

veronica-coreはフレームワーク非依存で、既存コードへの変更が少ない。`ExecutionContext`でラップするか、`patch_openai()`でSDKに注入するか、プロジェクトに合う方を選べる。

- GitHub: https://github.com/amabito/veronica-core
- PyPI: `pip install veronica-core`

スターもまだ少ないプロジェクトだが、同じ問題に当たった人は触ってみてほしい。
