---
title: "本番CUDAカーネルにデバッグatomicAddを残したら18倍遅くなった"
emoji: "💣"
type: "tech"
topics: ["cuda", "gpu", "performance", "debugging", "3dgs"]
published: true
published_at: "2026-02-26 12:00"
---

## 数字が合わない

3DGSのBackwardカーネルを実装して、ベンチマークを取った。

```
Forward: 81 it/s  (競合DGR: 84 it/s → ほぼ同等)
学習全体: 4.3 it/s (競合DGR: 78 it/s → 18倍遅い)
```

Forwardは問題ない。BackwardがあるとCIが崩壊する。

アルゴリズムのバグ？メモリリーク？勾配の計算が正しいことは確認済みだ。では何が……

3日間プロファイリングした結果、原因が判明した。

---

## 犯人: デバッグ用のatomicAdd

Backwardカーネルの中に、開発中に仕込んでいたデバッグコードが残っていた。

```cpp
// カーネル内のデバッグコード（問題箇所）
for (int i = 0; i < num_gaussians; i++) {
    float alpha = compute_alpha(gaussian_params[i]);
    float weight = alpha * T;
    T *= (1.0f - alpha);

    // ↓ このデバッグコードが全て
    atomicAdd(&d_stats->total_weight, weight);          // 1
    atomicAdd(&d_stats->total_alpha, alpha);            // 2
    atomicAdd(&d_stats->pixel_count, 1);                // 3
    atomicAdd(&d_stats->gaussian_count, 1);             // 4
    atomicAdd(&d_stats->transmittance_sum, T);          // 5
    atomicAdd(&d_stats->alpha_weighted_count,           // 6
              weight > 0.001f ? 1 : 0);
    atomicAdd(&d_stats->depth_weighted, weight * depth[i]); // 7
    __threadfence();  // 全atomicAddの完了を待つ
}
```

**ループ1回につき7個のglobal atomicAdd + 1個の__threadfence。**

ピクセルあたり100〜200個のGaussianを処理するカーネルで、これが全ピクセル・全Gaussianの組み合わせに対して実行されていた。

---

## なぜこんなに遅いのか

### global atomicAddの何が問題か

```cpp
atomicAdd(&global_counter, val);  // グローバルメモリへのアトミック操作
```

GPUは数千スレッドが同時に動く。複数スレッドが同じアドレスにatomicAddしようとすると、**シリアライズされる**。

3DGSのBackwardカーネルでは、1080pの解像度で：
- ピクセル数: 1,920 × 1,080 = 2,073,600
- ピクセルあたりGaussian数: 平均 150
- 合計atomicAdd回数: **7 × 2,073,600 × 150 = 約21.7億回**

これが単一のグローバルカウンターに集中する。スレッドが順番待ちをするため、スループットが激減する。

### __threadfenceのさらなる影響

```cpp
__threadfence();  // 全グローバルメモリ書き込みの完了を保証
```

`__threadfence()`は**デバイス全体のメモリ一貫性を保証**する非常に重いバリア操作だ。ループのたびに呼ぶと、全スレッドが同期点で待たされる。

---

## 修正: collect_statsフラグでゲーティング

```cpp
// Kernelパラメータに追加
bool collect_stats;

// カーネル内
for (int i = 0; i < num_gaussians; i++) {
    float alpha = compute_alpha(gaussian_params[i]);
    float weight = alpha * T;
    T *= (1.0f - alpha);

    // フラグでゲーティング
    if (collect_stats) {
        atomicAdd(&d_stats->total_weight, weight);
        atomicAdd(&d_stats->total_alpha, alpha);
        atomicAdd(&d_stats->pixel_count, 1);
        atomicAdd(&d_stats->gaussian_count, 1);
        atomicAdd(&d_stats->transmittance_sum, T);
        atomicAdd(&d_stats->alpha_weighted_count, weight > 0.001f ? 1 : 0);
        atomicAdd(&d_stats->depth_weighted, weight * depth[i]);
        __threadfence();
    }
}
```

本番では`collect_stats = false`を渡すだけで、atomicAddのオーバーヘッドが完全になくなる。

---

## 修正後のベンチマーク

```
修正前（collect_stats = true のまま）:
  Forward: 81 it/s
  学習全体: 4.3 it/s  ← 18倍遅い

修正後（collect_stats = false）:
  Forward: 81 it/s
  学習全体: 76 it/s   ← DGR(78)と同等水準
```

**18倍のスローダウンが解消した。**

---

## より良い実装: コンパイル時ゲーティング

実行時フラグより、コンパイル時定数の方が望ましい。

```cpp
#ifdef CUDA_DEBUG_STATS
    atomicAdd(&d_stats->total_weight, weight);
    // ...
    __threadfence();
#endif
```

あるいはテンプレートパラメータ：

```cpp
template<bool COLLECT_STATS>
__global__ void backward_kernel(...) {
    for (int i = 0; i < num_gaussians; i++) {
        // ...
        if constexpr (COLLECT_STATS) {
            atomicAdd(&d_stats->total_weight, weight);
            // ...
            __threadfence();
        }
    }
}

// 呼び出し側
backward_kernel<false><<<grid, block>>>(...);  // 本番
backward_kernel<true><<<grid, block>>>(...);   // デバッグ時のみ
```

`if constexpr`を使うと、`COLLECT_STATS = false`のとき`atomicAdd`のコードがコンパイル時に**完全除去**される。分岐コストすらない。

---

## global atomicAddの性能コスト

参考として、各操作のスループット（RTX 5090, sm_120）：

| 操作 | スループット |
|------|------------|
| 通常のグローバルメモリ読み書き | 高い（L2キャッシュ経由） |
| global atomicAdd（非競合） | 中程度 |
| global atomicAdd（高競合） | **極めて低い** |
| __threadfence() | **ブロッキング** |

競合するatomicAddは、実質的にシリアル実行になる。**1000スレッドが同じアドレスに同時にatomicAddすると、1000スレッドが順番待ちをする。**

---

## 他の落とし穴: printf

`atomicAdd`と同様に危険なのが`printf`だ。

```cpp
// NG: カーネル内のprintf
__global__ void kernel(...) {
    float val = compute(input[idx]);
    printf("idx=%d, val=%f\n", idx, val);  // 全スレッドが出力しようとする
}
```

CUDAの`printf`は内部バッファに書き込み、ホストで出力される。このバッファへのアクセスもシリアライズされる。

数百万スレッドが`printf`を呼ぶと**数百倍〜数千倍遅くなる**。

必ずゲーティングする：

```cpp
if (idx == 0) {
    printf("sample: val=%f\n", val);  // 1スレッドだけ
}
```

---

## デバッグコード管理の原則

1. **カーネル内に生のatomicAddを書かない**。デバッグ目的なら必ずフラグで囲む

2. **`if constexpr`やマクロで完全除去できるようにする**。フラグが`false`でも分岐コストが残る可能性がある

3. **ベンチマークはデバッグコードを全て無効にした状態で取る**。「本番と同じ設定でのベンチマーク」が意味を持つ

4. **プロファイラを信じる**。nsight systemsやnvprof/ncu で`atomicAdd`の競合を数値として確認できる

```bash
# NVIDIAのCUDAプロファイラ
ncu --metrics l1tex__t_bytes_pipe_lsu_mem_global_op_atom.sum \
    ./my_program

# 出力: アトミック操作のメモリトラフィック量が見える
```

---

## まとめ

- 本番CUDAカーネルに7個のglobal atomicAdd + __threadfence()を残した
- ループ内で毎回実行されて18倍のスローダウン
- `collect_stats = false`でゲーティングして解決
- より良い実装は`if constexpr (COLLECT_STATS)`でコンパイル時除去

**デバッグ用のatomicAddは、本番コードに絶対に残してはいけない。**

global atomicAddは便利だが、高競合時のコストは壊滅的だ。ベンチマークが遅いとき、まず「デバッグコードを全部消したか？」を確認すること。
