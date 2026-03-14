---
title: "LLMエージェントの記憶を8KBに圧縮する -- 3-path memory architectureの設計と実測"
emoji: "🧠"
type: "tech"
topics: ["LLM", "MachineLearning", "Python", "PyTorch", "AI"]
published: true
---

1,000エージェントを並行動作させるとき、KVキャッシュは31GBになる。各エージェント10Kトークンの会話履歴、fp32、d=256、L=8。現実的なGPU 1枚には載らない。

この問題に対して、固定8KBのリカレント状態で長距離パターンを圧縮し、KVウィンドウと検索インデックスを組み合わせる3パスメモリ層を設計・実装した。

https://github.com/amabito/tri-memory

## 何を作ったか

3つの記憶パスを持つメモリ層。

```
Input
 |-- KV window (直近Wトークン、exact attention)
 |-- Retrieval index (アーカイブされたチャンク、cosine検索)
 |-- TRN state (圧縮パターン、固定サイズ)
 |
 v
3-way gate: [g_kv, g_trn, g_ret] = softmax(W_gate * x)
  out = g_kv * kv_out + g_trn * trn_out + g_ret * ret_out
 |
 v
FFN -> logits
```

**KV window** はTransformerのKVキャッシュそのもの。直近64トークンをexact attentionで保持する。ウィンドウから追い出されたチャンクは2つの経路に分岐する。

**Retrieval index** はhidden stateのcosine類似度で検索する長期記憶。Saliencyスコアが高いチャンクだけが格納される。正確な事実の想起はここが担う。

**TRN state** が今回の設計の核。正弦波オシレーターバンクで系列履歴を固定サイズバッファに圧縮する。トークン100でもトークン10,000でも8KB。

学習済みのsoftmaxゲートが、各トークンごとに3パスの出力を混合する。

## オシレーターバンクの設計

TRNの中身は複素数のリカレント更新。各オシレーターkについて:

```
v_t = (1 - alpha_t) * A_t * exp(j * (omega_t * t + phi_t))
r_t = alpha_t * r_{t-1} + v_t
y_t = Re(r_t * exp(-j * (omega_t * t + phi_t)))
```

4つのパラメータはすべてトークン埋め込みから射影される:

| パラメータ | 意味 | 活性化関数 |
|-----------|------|-----------|
| A (振幅) | どれだけ強く書き込むか | softplus, clamp(max=3.0) |
| omega (周波数) | どのタイムスケールのパターンか | sigmoid * pi + omega_base |
| phi (位相) | パターン内の位置 | tanh * pi |
| alpha (減衰) | どれだけ過去を保持するか | sigmoid |

omega_baseは`torch.linspace(0.05*pi, 0.95*pi, K)`で初期化される。K=256なら256本のオシレーターが異なる周波数帯でパターンを拾う。

この更新は結合的 (associative) なので、GPU上ではO(log n)のparallel prefix scanで計算できる。CPUではO(n)の逐次スキャン。状態サイズはO(K)で、系列長に依存しない。

実装上、alphaとリカレント状態はfp32で保持している。bf16だと0.99が1.0に丸められて減衰ゲートがラッチになる。これはデバッグに2日かかった。

```python
# resonance.py L29 コメントより:
# bf16 cannot represent values close to 1.0 accurately
# (e.g. 0.99 rounds to 1.0), which would cause the
# decay gate to become a latch.
```

## 何ができて、何ができないか

### スループット (CPU, d=256, L=8, K=128)

| 履歴長 | TRN (tps) | TF+KV (tps) | TRN状態 | KVキャッシュ (fp32) |
|--------|-----------|-------------|---------|-------------------|
| 1,000 | 240 | 73.8 | 8 KB | 15.6 MB |
| 5,000 | 244 | 35.9 | 8 KB | 78.1 MB |
| 10,000 | 231 | 15.5 | 8 KB | 156.3 MB |

TRNは系列長に対してフラット。KVキャッシュはO(T)で劣化する。10Kトークンで15倍の差。d=256はトイスケールなので、d=1024+ではこの差は縮まるはず。まだ測っていない。

### 逐語再現は壊滅的にできない

Selective copy accuracy: 8.8% (Transformer: 96.2%)。Needle-in-Haystack: 0.0%。

最初は何かバグがあると思って数回走らせた。バグではなかった。オシレーターはパターンを平均化するので、個別のトークンIDは消える。これは圧縮が動作していることの裏返しで、8KBに収まる理由そのもの。

正確な事実の想起はRetrieval indexの仕事。TRNはパターンの蓄積を担当する。

### Ablation (d=128, L=4, 10シード x 3000ステップ)

| 構成 | 複合スコア | 備考 |
|------|-----------|------|
| A: KV only | 0.263 | ベースライン |
| B: KV+Recurrent | 0.457 | パターン検出0.678、ただし2/10シードで崩壊 |
| C: KV+Retrieval | 0.369 | 古い事実の想起0.433 |
| **D: Full 3-path** | **0.676** | **パターン0.805、古い事実0.719** |

複合スコアは4つのタスクの平均: パターン検出、古い事実想起、直近想起、系列予測。すべてGo/No-Go形式の合成タスク。

Config Dは10シード全てでmax(A,B,C)を上回った。平均デルタ+0.165。

Config B (KV+Recurrent) は2シードで崩壊した。ゲートがリカレントパスにほぼ全重みを与えて、Retrievalが飢餓状態になった。同じシードでConfig D (Full 3-path) を走らせると崩壊しない。3パス目を省略可能と考えるのをやめたのはこの結果を見たとき。

ablationのスケール(d=128)とスループット計測のスケール(d=256)が異なる点に注意。d=256での完全なablationはまだ走らせていない。

## ゲートのテレメトリ

ゲートの重み配分を記録してみると、タスクによって明確にルーティングが変わる。

パターン検出タスクではリカレントパスが約30%の重みを持つ。逐語再現タスクではほぼゼロ。系列予測タスクではリカレントとRetrievalの間でゲートが振動して収束しない。

1B+パラメータで同じ8KBバジェットのまま、このルーティングが安定するかは不明。

## 実装

PyTorch 2.1+、Python 3.10+。277テスト。

```python
from trimemory import TRNConfig
from trimemory.tri_memory import TriMemoryEngine

cfg = TRNConfig(
    vocab_size=8192, d_model=128, n_oscillators=64,
    n_layers=4, d_ff=512, max_seq_len=1024,
)
model = TriMemoryEngine(
    cfg,
    window_size=64,
    chunk_size=32,
    max_retrieval_chunks=256,
    enable_trn=True,
    enable_retrieval=True,
)

ids = torch.randint(0, cfg.vocab_size, (1, 512))
out = model(ids, labels=ids)
print(f"loss: {out['loss']:.4f}")

mem = model.memory_summary()
print(f"TRN state: {mem['trn_state_bytes']} bytes")
```

エージェント用のストリーミングインターフェースもある:

```python
from trimemory.agent_memory import AgentMemory

mem = AgentMemory(TRNConfig.toy(), device="cpu")
mem.add_tokens([1, 2, 3, 4, 5])
print(f"State: {mem.state_size_bytes()} bytes")
mem.save("turn1.pt")
mem.load("turn1.pt")
```

## 設計判断の背景

**なぜ正弦波か。** 信号処理のFourier基底と同じ発想で、異なる周波数帯のパターンを独立に追跡できる。LSTMのようなゲート付きRNNは状態がブラックボックスになるが、オシレーターは「周波数fのパターンが振幅Aで存在する」という解釈可能な状態を持つ。

**なぜ3パス必要か。** 当初はKV+TRNの2パスで十分だと思っていた。ablationでConfig Bが2シード崩壊したのを見て考えが変わった。Retrievalパスが安定化装置として機能している。ゲートがリカレントに偏りすぎたとき、Retrievalが正確な事実を供給して引き戻す。

**なぜソフトマックスゲートか。** 3パスの出力を混合する方法として、学習可能なソフトマックスゲートを選んだ。attention-based routingも試したが、入力に対して1回の線形射影+softmaxのほうがオーバーヘッドが少なく、ablationスコアも同等だった。

**状態サイズ固定の代償。** 8KBに固定することで、系列が長くなるほど1トークンあたりの情報量は薄まる。1B+パラメータでパターン数が増えたとき、同じ8KBバジェットで足りるかは未検証。おそらくここが最初のボトルネックになる。

## 制限事項

- 全実験がトイスケール (1-100Mパラメータ)。1B+でのスケーリングは未知
- TRNはcontent-addressed retrievalができない。構造的な制約
- PolicyBenchはN=10。検証規模として小さい
- Retrieval indexはプロセス再起動で消える
- ゲートテレメトリは入力分布に依存する。汎化性は未検証
- alphaステータス。本番デプロイの実績なし

## 参考

- [リポジトリ: amabito/tri-memory](https://github.com/amabito/tri-memory) -- Apache-2.0
- [VERONICA-core](https://github.com/amabito/veronica-core) -- ランタイム封じ込め (予算強制、サーキットブレーカー)
- [S4: Structured State Spaces for Sequence Modeling](https://arxiv.org/abs/2111.00396) -- 状態空間モデルの基礎
- [Mamba: Linear-Time Sequence Modeling with Selective State Spaces](https://arxiv.org/abs/2312.00752) -- 選択的状態空間
