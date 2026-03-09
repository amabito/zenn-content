---
title: "LLMエージェントの予算暴走を止める: veronica-coreの設計と実装"
emoji: "🛡"
type: "tech"
topics: ["llm", "ai", "python", "agentai", "claude"]
published: false
published_at: "2026-02-25 07:00"
---

AIエージェントが週末に$12,000使っていた——これは実際に起きたインシデントだ。観測系が全部あっても、止められなかった。observabilityとcontainmentは別物だということを、身をもって学んだ。

## なぜLLMコールは普通のAPIと違うのか

普通のAPIを呼ぶとき、コストは事前にわかる。HTTPリクエストを何回叩いても、べき乗で膨らむことはない。

LLMコールは違う。

```python
# 普通のAPI: 決定論的
result = db.query(sql)  # 0.1ms, 0円

# LLMコール: 確率的 + 可変コスト
result = llm.complete(prompt)  # 100ms〜10s, $0.001〜$0.5
```

LLMコールが持つ4つの厄介な性質：

1. **確率的出力**: 同じプロンプトで違う結果が出る。リトライすれば解決するとは限らない
2. **可変トークンコスト**: 出力の長さはモデルが決める。呼び出し側は制御できない
3. **再帰的呼び出し**: エージェントがツールを呼び、ツールがエージェントを呼ぶ。深さは無制限
4. **リトライ増幅**: 失敗率がネストされた呼び出しチェーンで指数的に拡大する

既存のObservability（Langsmith、Datadog等）はこれらを**記録**する。でも止めない。

## veronica-coreの核心: "Observability ≠ Containment"

[veronica-core](https://github.com/amabito/veronica-core)を作った動機はシンプルだ。

> 「LLMコールの前に制約を評価して、問題が起きる前に止めたい」

アーキテクチャは以下：

```
App → Orchestrator → [VERONICA] → LLM Provider
```

VERONICAはOrchestrationとLLM Providerの間に割り込む。各コールの前に登録済みフックを評価し、ALLOW / DEGRADE / HALTを返す。

## 5つのContainment Layer

### Layer 1: Cost Bounding（コスト上限）

最も基本的な層。累積トークン使用量と呼び出し回数に上限を設ける。

```python
config = ExecutionConfig(
    max_cost_usd=1.00,    # $1以上使ったら止める
    max_steps=50,         # 50ステップで強制終了
    max_retries_total=10  # 合計リトライ10回まで
)

with ExecutionContext(config=config) as ctx:
    while not done:
        decision = ctx.wrap_llm_call(
            fn=lambda: llm.complete(prompt),
            options=WrapOptions(operation_name="step_n")
        )
        if decision.name == "HALT":
            break  # 上限到達、安全に終了

        result = decision.result
        # ... 処理 ...
```

ここで重要なのは**DEGRADE**シグナルの存在だ。HALTの手前でDEGRADEが発火し、グレースフルデグラデーションの機会を与える。いきなり死なない。

### Layer 2: Amplification Control（増幅制御）

分散システムがよくハマるパターン：コンポーネントが失敗 → リトライ → さらに負荷 → さらに失敗。指数バックオフでも、ネストされたチェーンでは指数が指数になる。

`BudgetWindowHook`はスライディングウィンドウで呼び出し回数を追跡し、上流のリトライロジックを無視して強制停止できる。

```python
# これが何段階にネストされていても
agent_a()
  → agent_b()      # リトライ3回
    → agent_c()    # リトライ3回
      → llm_call() # BudgetWindowが全体を見ている

# BudgetWindowHookが「もう十分」と判断したら止まる
```

### Layer 3: Recursive Containment（再帰制御）

エンティティごとの連続失敗回数を追跡し、閾値を超えたらCOOLDOWN状態に遷移させる。

```python
state_machine = VeronicaStateMachine(
    cooldown_after_failures=3,
    cooldown_duration_seconds=60
)
```

3回連続で失敗したエンティティは60秒クールダウン。他のエンティティは影響を受けない。これが「失敗ドメインの分離」だ。

### Layer 4: Stall Isolation（ストール検出）

応答はしているが使えない——というケースへの対応。レイテンシ、エラー率、応答品質を検査して劣化コンポーネントを検出する。

`MinimalResponsePolicy`はシステムメッセージを注入して出力の簡潔さを強制できる。無限に長いレスポンスを生成し続けるLLMを抑制する。

### Layer 5: Failure Domain Isolation（失敗ドメイン分離）

全てのHALT/DEGRADE決定はSafetyEventとして記録される。

```python
@dataclass
class SafetyEvent:
    event_type: str        # COST_EXCEEDED, RETRY_STORM, etc.
    decision: str          # HALT / DEGRADE / ALLOW
    context_hash: str      # SHA-256（生プロンプトは保存しない）
    timestamp: datetime
    metadata: dict
```

生プロンプトをログに残すのはセキュリティリスクがある（APIキー、個人情報、機密データを含む可能性）。SHA-256ハッシュで同一コンテキストの追跡は可能にしつつ、内容は秘匿する。

## 高レベルAPI: デコレーターとSDKパッチ

毎回`ExecutionContext`を書くのは面倒だ。v0.9.3から追加したデコレーターAPIが便利：

```python
from veronica_core import veronica_guard

@veronica_guard(max_cost_usd=1.0, max_steps=20)
def call_llm(prompt: str) -> str:
    return anthropic_client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    ).content[0].text
```

これだけでコスト上限が適用される。既存コードの変更は最小限だ。

v0.9.4のSDKパッチはさらに過激で、一行で全コールに適用する：

```python
from veronica_core import patch_anthropic

# この一行以降の全Anthropic APIコールに予算制約が適用される
patch_anthropic(max_cost_usd=10.0, max_steps=200)

# 既存コードは変更不要
client = anthropic.Anthropic()
response = client.messages.create(...)  # 自動的に監視される
```

## 設計上の選択とトレードオフ

### 階層型予算 vs 都度宣言

最初に考えたのは「都度宣言型」だった：

```python
# 都度宣言型
call_llm(prompt, budget=Budget(usd=0.1))
call_llm(prompt, budget=Budget(usd=0.2))
```

問題は、動的なコールグラフでは「合計がいくらになるか」が事前にわからないことだ。

採用したのは「階層型」：

```python
# 階層型: 親のceilingが子の合計に適用される
with ExecutionContext(max_cost_usd=1.0) as ctx:
    # この中での全コールの合計が$1.0以下に制約される
    result_a = ctx.wrap_llm_call(fn=step_a, ...)
    result_b = ctx.wrap_llm_call(fn=step_b, ...)
    result_c = ctx.wrap_llm_call(fn=step_c, ...)
```

親contextのceilingが子のspendに自動的にロールアップされる。これで重複計上なしに階層的な予算管理ができる。

### ブロッキング vs Fire-and-Forget

`wrap_llm_call`はブロッキングだ。コールの前に評価して、HALT判定なら実行しない。

非同期版も検討したが、「call前に止める」という原則にはブロッキングが合っている。非同期にするとcontainmentが「できれば止める」になってしまう。

```python
# ブロッキング（採用）
decision = ctx.wrap_llm_call(fn=llm_call)
# → HALTならllm_callは実行されていない

# Fire-and-forget（不採用）
ctx.wrap_llm_call_async(fn=llm_call)
# → ウィンドウが重複したときの保証が難しい
```

### 未解決問題: 動的コールグラフの重複除去

HN（Hacker News）でdas-bikash-devからこういう指摘をもらった：

> 「trace ID + async cost spans + deduplication challenge」という別アプローチもある。トレースベースで全コストをキャプチャしてから事後的に重複除去する方法だ。

この指摘は正しくて、veronica-coreにはまだ未解決の問題がある：動的に生成されるコールグラフでの重複計上問題だ。

```
context_a ($1.00 ceiling)
  └── context_b ($0.50 ceiling)
        └── llm_call ($0.30)  ← これはa, b両方にカウントされるべきか？
```

現在の実装は「各contextが独立して追跡」している。重複計上を避けるには呼び出し元contextを特定する必要があり、これがdas-bikash-devの言うdeduplication challengeだ。

階層型アプローチの利点は「事前宣言でdeduplicationを回避できること」——つまり、動的グラフが出現する前に階層構造を定義しておく。これで重複の問題自体を発生させない設計になっている。ただし、実行前に階層が決まらないケースには対応できていない。

## アトミックなディスク書き込み

SafetyEventの永続化で重要な実装がある。kill -9で強制終了されても、書き込み中のファイルが壊れないようにしたかった。

採用したのはtmp→renameパターン：

```python
import os
import tempfile
import json

def persist_safety_event(event: SafetyEvent, path: str) -> None:
    """tmp→renameでアトミック書き込み"""
    dir_path = os.path.dirname(path)

    # 同じファイルシステム上の一時ファイルに書く
    with tempfile.NamedTemporaryFile(
        mode='w',
        dir=dir_path,
        delete=False,
        suffix='.tmp'
    ) as f:
        json.dump(event.to_dict(), f)
        f.flush()
        os.fsync(f.fileno())  # カーネルバッファをディスクにフラッシュ
        tmp_path = f.name

    # renameはPOSIXではアトミック操作
    os.replace(tmp_path, path)
```

Linuxでは`rename(2)`システムコールはアトミックだ。tmpに書いてからrenameするため、kill -9が途中に挟まっても：
- tmp書き込み中 → tmpが残る（pathは古い状態のまま）
- rename前 → tmpが残る（pathは古い状態のまま）
- rename後 → 新しいデータが確定

pathが壊れた状態になることはない。

## 実際に使ってみた効果

自分のLLMエージェントシステム（J.A.R.V.I.S.チームモード）に組み込んでから：

- 予期しないAPIコスト爆発が0件になった
- リトライストームによる連鎖障害がなくなった
- 「どのステップで何のコールが何回発生したか」が追跡できるようになった

特に効果があったのが長時間のチームモード実行だ。複数のエージェントが並列で動くと、リトライが重なって指数的に増幅するケースがあった。BudgetWindowHookが全体を見ていることで、個別エージェントのリトライロジックを変えずにシステム全体の予算を制御できた。

## インストールと最小サンプル

```bash
pip install veronica-core
```

```python
from veronica_core import ExecutionContext, ExecutionConfig, WrapOptions

# 設定: $0.50上限、最大30ステップ
config = ExecutionConfig(
    max_cost_usd=0.50,
    max_steps=30,
    max_retries_total=5
)

def my_llm_call(prompt: str) -> str:
    # 実際のLLMコール
    import anthropic
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text

results = []
with ExecutionContext(config=config) as ctx:
    for step, prompt in enumerate(prompts):
        decision = ctx.wrap_llm_call(
            fn=lambda p=prompt: my_llm_call(p),
            options=WrapOptions(operation_name=f"step_{step}")
        )

        if decision.name == "HALT":
            print(f"Budget exceeded at step {step}")
            break
        elif decision.name == "DEGRADE":
            print(f"Approaching limit at step {step}, degrading")
            # 軽量モデルに切り替える等の対応

        results.append(decision.result)

# 実行グラフの確認
snapshot = ctx.get_graph_snapshot()
print(f"Total cost: ${snapshot['total_cost_usd']:.4f}")
print(f"Total steps: {snapshot['total_steps']}")
```

## セキュリティモデルの正直な話

veronica-coreはプロセス境界でポリシーを強制する。OSレベルのcontainmentではない。

できること：
- ハードなコスト上限
- 増幅制御
- 再帰深度の制限
- フェイルクローズ（未知のアクションはデフォルトDENY）

できないこと：
- 許可されたバイナリが生成したサブプロセスの制御
- syscallの制限
- レスポンス内容の検査

つまり「LLMコールが暴走しない」ことは保証するが、「LLMが有害なコードを生成したらそれを実行するサブプロセスを止める」ことはできない。その層には別のツールが必要だ。

## まとめ

LLMエージェントの予算管理は「Observabilityがあれば大丈夫」という認識が多い。でも実際は、記録するだけでは止まらない。

veronica-coreが提供するのは：

1. **コールの前に評価する**——発生してから記録ではなく、起きる前に止める
2. **5層のcontainment**——単純な上限だけでなく、増幅・再帰・ストール・ドメイン分離まで
3. **グレースフルデグラデーション**——いきなりKillではなくDEGRADEで段階的に対応
4. **ゼロ依存**——外部サービス不要でローカル実行

まだv0.10.5で未解決問題もある（動的コールグラフのdeduplication）。でも「予算暴走を止める」という核心的なユースケースには、今すでに使える状態だ。

コードは[GitHub](https://github.com/amabito/veronica-core)にある。issueやPRは歓迎している。
