---
title: "block_reduce.hに潜んでいた2D blockのバグ: threadIdx.x / 32が常に0だった話"
emoji: "🐛"
type: "tech"
topics: ["cuda", "gpu", "cpp", "debugging", "3dgs"]
published: true
published_at: "2026-02-25 18:00"
---

## 勾配が8倍になっていた

3DGSのBackwardカーネルをデバッグしていたとき、異常に気づいた。

損失関数の勾配値が期待値の約8倍になっている。学習が発散する。

コードを何度見直しても問題が見つからない。数学は正しい。アルゴリズムも正しい。

原因は**block_reduce.hの中に潜んでいた**。

---

## block_reduce.hとは

block_reduce.hは、CUDAブロック内の並列リダクション（reduction）を行うユーティリティだ。

例えば、ブロック内の全スレッドが持つ値の合計を1スレッドで受け取りたいとき、このようなコードを使う。

```cpp
float val = thread_value;  // 各スレッドの値
float sum = block_reduce_sum(val);  // ブロック内の全スレッドの合計
// スレッド0だけが正しい値を持つ
if (threadIdx.x == 0) {
    result = sum;
}
```

内部実装の骨格はこうだ。

```cpp
__device__ float block_reduce_sum(float val) {
    // Step 1: warp内でリダクション
    for (int offset = 16; offset > 0; offset >>= 1) {
        val += __shfl_down_sync(0xffffffff, val, offset);
    }

    // Step 2: 各warpのlane 0が結果をshared memoryに書く
    __shared__ float s_warp_partials[8];  // 最大8 warp
    int warp_id = threadIdx.x / 32;
    int lane_id = threadIdx.x % 32;
    if (lane_id == 0) {
        s_warp_partials[warp_id] = val;
    }
    __syncthreads();

    // Step 3: warp 0がfinal reduction
    float result = 0.0f;
    if (warp_id == 0) {
        result = s_warp_partials[lane_id];
        // ...
    }
    return result;
}
```

---

## バグ: 2Dブロックでの落とし穴

このコードは**1Dブロック**を前提にしている。`threadIdx.x`だけを使ってwarp_idを計算しているからだ。

問題は、私が使っていたカーネルのブロック設定だ。

```cpp
// HyperSplat Backwardカーネルのブロック設定
dim3 block(16, 16, 1);  // 2Dブロック: 16×16=256スレッド
```

16×16の2Dブロックでは、スレッドのレイアウトがこうなる。

```
threadIdx.x は 0〜15 の繰り返し
threadIdx.y は 0〜15

スレッド(0,0)   -> threadIdx.x=0,  threadIdx.y=0
スレッド(15,0)  -> threadIdx.x=15, threadIdx.y=0
スレッド(0,1)   -> threadIdx.x=0,  threadIdx.y=1
スレッド(15,15) -> threadIdx.x=15, threadIdx.y=15
```

このとき、`threadIdx.x / 32`はどの値になるか？

```
threadIdx.x は 0〜15
threadIdx.x / 32 = 0（全スレッドで）
```

**全256スレッドで`warp_id = 0`になる。**

---

## 何が起きていたか

```cpp
int warp_id = threadIdx.x / 32;  // 常に0
int lane_id = threadIdx.x % 32;  // 0〜15の繰り返し
```

`warp_id = 0`なので：

```cpp
if (lane_id == 0) {
    s_warp_partials[0] = val;  // 常にindex 0に書き込む！
    // s_warp_partials[1..7] は未初期化のまま
}
```

実際には16×16=256スレッドを8つのwarpに分けるべきところ、全スレッドがwarp 0のものとして動作した。

さらに悪いことに、最後のfinal reduction：

```cpp
if (threadIdx.x == 0) {  // 2Dブロックでこれは何スレッドにマッチする？
    result = ...;
}
```

1Dブロックなら1スレッド（スレッド0だけ）がマッチする。

だが2Dブロック`dim3(16, 16, 1)`では：
- threadIdx.x == 0 かつ threadIdx.y == 0: スレッド(0,0)
- threadIdx.x == 0 かつ threadIdx.y == 1: スレッド(0,1)
- ...
- threadIdx.x == 0 かつ threadIdx.y == 15: スレッド(0,15)

**16スレッドがマッチする。**これはデータレースだ。

---

## 結果: 勾配が8倍になった理由

勾配のリダクションは256スレッドで1つの値を集約するはずだった。

しかし実際には：

1. `s_warp_partials[1..7]`が未初期化のゴミ値
2. 16スレッドが同じ場所に書き込む（データレース）

「8倍」になったのは偶然の一致だった。実際には不定動作で、時にはクラッシュし、時には異常値が出ていた。

---

## 修正: linear_idを先に計算する

```cpp
__device__ float block_reduce_sum(float val) {
    // 修正: 2Dブロックに対応したlinear_id
    const int linear_id = threadIdx.x + threadIdx.y * blockDim.x;
    const int warp_id = linear_id / 32;
    const int lane_id = linear_id % 32;

    // Step 1: warp内リダクション
    for (int offset = 16; offset > 0; offset >>= 1) {
        val += __shfl_down_sync(0xffffffff, val, offset);
    }

    // Step 2: lane 0が書き込む
    __shared__ float s_warp_partials[8];
    if (lane_id == 0) {
        s_warp_partials[warp_id] = val;
    }
    __syncthreads();

    // Step 3: linear_id == 0のスレッドだけが集計（1スレッドだけ）
    float result = 0.0f;
    if (linear_id == 0) {
        for (int i = 0; i < (blockDim.x * blockDim.y * blockDim.z + 31) / 32; i++) {
            result += s_warp_partials[i];
        }
    }
    return result;
}
```

修正のポイントは2つ：

1. `warp_id`と`lane_id`の計算に`linear_id`を使う
2. 最後の書き込みに`threadIdx.x == 0`ではなく`linear_id == 0`を使う

---

## 修正後の動作確認

2Dブロック`dim3(16, 16, 1)`での`linear_id`の分布：

```
スレッド(0,0): linear_id=0,   warp_id=0, lane_id=0
スレッド(1,0): linear_id=1,   warp_id=0, lane_id=1
...
スレッド(15,0): linear_id=15, warp_id=0, lane_id=15
スレッド(0,1): linear_id=16,  warp_id=0, lane_id=16
...
スレッド(15,1): linear_id=31, warp_id=0, lane_id=31
スレッド(0,2): linear_id=32,  warp_id=1, lane_id=0  ← warp 1に切り替わる
...
スレッド(15,7): linear_id=127, warp_id=3, lane_id=31
スレッド(0,8): linear_id=128,  warp_id=4, lane_id=0
...
スレッド(15,15): linear_id=255, warp_id=7, lane_id=31
```

8つのwarpに正しく分散する。`linear_id == 0`はスレッド(0,0)の1つだけにマッチする。

コミット`7679dcc`で修正した。勾配値が正常になり、学習が収束した。

---

## 一般化: 3Dブロックでも対応

3Dブロック`dim3(x, y, z)`の場合：

```cpp
const int linear_id = threadIdx.x
                    + threadIdx.y * blockDim.x
                    + threadIdx.z * blockDim.x * blockDim.y;
```

---

## このバグが潜みやすい理由

このバグは**1Dブロックで動いていたコードを2Dブロックのカーネルにそのまま使ったとき**に発生する。

block_reduce.hのようなユーティリティは、最初から1Dブロック向けに書かれることが多い。内部で`threadIdx.x`しか見ていないため、2Dブロックで使うと静かに壊れる。

クラッシュしないのがさらに厄介だ。間違った値を返しながら動き続ける。

---

## チェックリスト

block_reduceをコピーしたり、既存のユーティリティを別カーネルで使うとき：

- [ ] そのユーティリティは1Dブロックを前提にしていないか？
- [ ] `warp_id`の計算に`threadIdx.x / 32`を使っていないか？
- [ ] 最後の書き込みに`threadIdx.x == 0`を使っていないか？
- [ ] `linear_id`を明示的に計算しているか？

**絶対に使ってはいけないパターン：**

```cpp
// 2DブロックでのNG
int warp_id = threadIdx.x / 32;    // 常に0になる可能性
int lane_id = threadIdx.x % 32;    // 不正な値
if (threadIdx.x == 0) { ... }      // 複数スレッドにマッチする可能性

// OK
int linear_id = threadIdx.x + threadIdx.y * blockDim.x;
int warp_id = linear_id / 32;
int lane_id = linear_id % 32;
if (linear_id == 0) { ... }
```

---

## まとめ

- 2Dブロック`dim3(16,16,1)`で`threadIdx.x / 32`は常に`0`
- 全256スレッドが「自分はwarp 0」と誤認識
- `s_warp_partials[1..7]`がゴミ値のまま
- `threadIdx.x == 0`が16スレッドにマッチしてデータレース
- 結果: 勾配が8倍になり学習が発散

**鉄則: 2D/3Dブロックでwarp_idが必要なときは、必ず`linear_id`を先に計算する。**
