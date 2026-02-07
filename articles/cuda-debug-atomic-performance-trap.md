---
title: "CUDAカーネルのデバッグコードが招く20倍の性能劣化【実測データ付き】"
emoji: "🔥"
type: "tech"
topics: ["CUDA", "GPU", "パフォーマンス", "3DGS"]
published: true
---

## 導入: 18倍の性能差の謎

3D Gaussian Splatting (3DGS)の高速化を目指して、CUDAラスタライザー「HyperRasterizer」を開発していた。Forward passのベンチマークは競合ライブラリ(diff-gaussian-rasterization, 以下DGR)と同等の性能が出ている。81 it/s vs 84 it/s。ほぼ互角だ。

しかし、Backward passを含めた学習全体では、まったく話が違った。

**HyperRasterizer: 4.3 it/s**
**DGR: 78 it/s**

**18倍の性能差**。

何かがおかしい。Forward単体では同等なのに、Backwardを含めた瞬間に崩壊する。メモリリーク？アルゴリズムのバグ？いや、結果は正しい。ただ、恐ろしく遅い。

3日間のプロファイリングと格闘の末、真犯人が判明した。

**デバッグコードだった。**

本番環境に残した、たった数行の診断用コードが、20倍の性能劣化を引き起こしていた。この記事では、実測データとともに、CUDAカーネルにおけるデバッグコードの恐ろしさを解説する。

## 症状: Forward は速いのに Backward は激遅

まず、具体的な計測結果を見てみよう。

### Forward pass単体の性能比較

| 実装 | it/s | 備考 |
|------|------|------|
| HyperRasterizer | 81 | 自作CUDA実装 |
| DGR (diff-gaussian-rasterization) | 84 | 競合ライブラリ |

**ほぼ同等**。Forward kernelの実装は正しく、最適化もうまくいっている。

### Backward passを含めた学習全体の性能比較

| 実装 | it/s | Forward比 |
|------|------|-----------|
| HyperRasterizer | **4.3** | **1/19** |
| DGR | 78 | 1/1.08 |

**HyperRasterizerだけが18倍遅い**。しかも、Forward単体性能から1/19に落ち込んでいる。DGRはForward 84 → 全体78と、ほぼ変わらない。

これは明らかにBackward kernelに致命的な問題がある。

## 調査: Nsight ComputeとCUDAプロファイラ

NVIDIA Nsight Computeでbackward kernelをプロファイリングした結果、以下の異常が検出された。

- **Warp Stall (Memory Throttle): 85%** - ほぼすべてのwarpがメモリ待ちで停止
- **Achieved Occupancy: 12%** - 理論値の1/8しかスレッドが動いていない
- **Global Atomic Throughput: 1,245 GB/s** - 異常に高いatomic操作

特に、**Global Atomic Throughput**の値が異常だった。競合実装では20 GB/s程度なのに、HyperRasterizerは1,245 GB/s。60倍以上のatomic操作が発生している。

ソースコードを精査した結果、backward.cuに大量のデバッグコードが残っていることが判明した。

## 原因1: グローバル `__device__` atomicAddの悪夢

最も深刻だったのが、**統計情報収集用のグローバルatomicAdd**だった。

### 問題のコード

```cuda
// backward.cu (問題のコード)
__device__ uint64_t g_total_pixels_processed = 0;
__device__ uint64_t g_total_gradients_computed = 0;
__device__ uint64_t g_total_gaussians_touched = 0;
// ... さらに4つの統計カウンタ

__global__ void backward_kernel(...) {
    const bool collect_stats = true;  // ← デバッグ用フラグ、常にtrue!

    for (int i = 0; i < BATCH_SIZE; i++) {
        // ... backward計算 ...

        if (collect_stats) {
            atomicAdd(&g_total_pixels_processed, 1);
            atomicAdd(&g_total_gradients_computed, 1);
            atomicAdd(&g_total_gaussians_touched, 1);
            // ... さらに4つのatomicAdd
        }
    }
}
```

### 何が問題なのか？

CUDAのglobal atomicは、**すべてのthread、すべてのblockが同じメモリアドレスに対して排他制御を行う**。

想像してみてほしい。1920x1080の画像をレンダリングする場合：

- Pixel数: 1920 × 1080 = 2,073,600
- 各pixelに平均10個のGaussianが重なる
- 合計: **約2000万回のatomicAdd**
- これが**7つの統計カウンタ**に対して並行実行される

つまり、**約1.4億回のグローバルatomic操作**が、すべてのスレッドで競合する。

### なぜこれほど遅いのか？

グローバルatomicは、以下のステップで処理される：

1. スレッドAがメモリアドレスXに対してatomicAddを要求
2. **グローバルメモリがロックされる**
3. 現在の値を読み取る
4. 加算する
5. 書き戻す
6. ロック解放
7. 次のスレッドBが待機解除される → ステップ1に戻る

**すべてのスレッドが順番待ちで直列化される**。並列性がゼロになる。

さらに悪いことに、これがpixel-Gaussian pairごとに7回発生する。Backwardの処理時間の大部分が、統計カウンタの更新待ちで消費されていた。

### 修正

```cuda
// 修正後
__global__ void backward_kernel(...) {
    const bool collect_stats = false;  // ← デフォルトでOFF

    // デバッグ時のみ環境変数で有効化
    if (collect_stats) {  // 通常は通らない
        // ...
    }
}
```

**結果: 4.3 it/s → 23 it/s (5.3倍高速化)**

## 原因2: `__threadfence()`による全スレッド同期

2つ目の問題は、**`__threadfence()`の誤用**だった。

### 問題のコード

```cuda
__global__ void backward_kernel(...) {
    for (int batch = 0; batch < num_batches; batch++) {
        // ... backward計算 ...

        __threadfence();  // ← 全スレッド同期！

        if (threadIdx.x == 0) {
            // 統計情報の集計
        }
    }
}
```

### `__threadfence()`とは？

`__threadfence()`は、**グローバルメモリへの書き込みを、すべてのスレッドから見えるようにする**命令だ。

具体的には：

- このスレッドの以前のすべての書き込みが、グローバルメモリに到達することを保証
- **すべてのスレッドが待機**し、メモリアクセスが完了するまでブロックされる

通常、これは必要ない。CUDAの同期には`__syncthreads()`(block内)や、kernel終了時の暗黙的同期で十分だ。

### なぜこれがボトルネックになるのか？

HyperRasterizerのbackward kernelは、以下のように動作する：

- Batch数: 典型的に20-50
- **各batchの終わりに`__threadfence()`を実行**

つまり、kernel実行中に20-50回、**全スレッドがメモリアクセス完了を待機**する。

これは、高速道路で50回も全車両停止させるようなものだ。スループットが激減する。

### 修正

```cuda
// 修正後: __threadfence()を削除
__global__ void backward_kernel(...) {
    for (int batch = 0; batch < num_batches; batch++) {
        // ... backward計算 ...

        // __threadfence();  ← 削除！

        // Kernel終了時の暗黙的同期で十分
    }
}
```

**追加効果: 23 it/s → 38 it/s (1.65倍高速化)**

## 原因3: Thread 0による1.5M要素のスキャン

3つ目の問題は、**診断用の全pixel走査**だった。

### 問題のコード

```cuda
__global__ void backward_kernel(...) {
    // ... backward計算 ...

    // DIAGNOSTIC B: 勾配が正しく計算されているか確認
    if (threadIdx.x == 0 && blockIdx.x == 0) {
        for (int y = 0; y < H; y++) {
            for (int x = 0; x < W; x++) {
                for (int c = 0; c < 3; c++) {
                    float grad = d_output[y * W * 3 + x * 3 + c];
                    if (!isfinite(grad)) {
                        printf("Invalid gradient at (%d, %d, %d): %f\n",
                               y, x, c, grad);
                    }
                }
            }
        }
    }

    __syncthreads();  // すべてのスレッドが待機
}
```

### 計算量

1920×1080の画像の場合：

- W × H × 3 = 1920 × 1080 × 3 = **6,220,800要素**
- これを**たった1つのスレッド**がスキャン
- 他の**数千～数万のスレッド**は`__syncthreads()`で待機

つまり、GPU全体が、1スレッドの620万回のメモリアクセス完了を待っている。

### なぜこんなコードが残っていたのか？

開発初期、勾配計算にNaN/Infが発生するバグがあった。その診断のために追加したコードだ。バグ修正後も、「念のため」と思って残していた。

これが20倍の性能劣化の一因になるとは、思いもしなかった。

### 修正

```cuda
// 修正後: 診断コードを完全削除
__global__ void backward_kernel(...) {
    // ... backward計算 ...

    // DIAGNOSTIC B削除！
}
```

**追加効果: 38 it/s → 52 it/s (1.37倍高速化)**

## 原因4: Shared memoryのデバッグatomic

4つ目の問題は、**shared memory上のデバッグカウンタ**だった。

### 問題のコード

```cuda
__global__ void backward_kernel(...) {
    __shared__ uint32_t s_debug_pixels_processed;
    __shared__ uint32_t s_debug_grad_computed;

    if (threadIdx.x == 0) {
        s_debug_pixels_processed = 0;
        s_debug_grad_computed = 0;
    }
    __syncthreads();

    for (int i = 0; i < BATCH_SIZE; i++) {
        // ... backward計算 ...

        atomicAdd(&s_debug_pixels_processed, 1);
        atomicAdd(&s_debug_grad_computed, 1);
    }

    __syncthreads();

    if (threadIdx.x == 0) {
        // グローバルカウンタに集約
        atomicAdd(&g_total_pixels_processed, s_debug_pixels_processed);
        atomicAdd(&g_total_gradients_computed, s_debug_grad_computed);
    }
}
```

### 何が問題なのか？

Shared memory atomicは、global atomicよりは速い。しかし、**block内のすべてのスレッドが競合**する。

典型的なblock構成：

- Threads per block: 256
- 各スレッドがBATCH_SIZE(典型的に32)回のatomicAddを実行
- 合計: 256 × 32 = **8,192回のatomic競合**

これが**block数×8,192回**発生する。

さらに、`__syncthreads()`が2回追加されている。Block内同期のオーバーヘッドも無視できない。

### 修正

```cuda
// 修正後: デバッグカウンタ削除
__global__ void backward_kernel(...) {
    // __shared__ uint32_t s_debug_pixels_processed;  ← 削除
    // __shared__ uint32_t s_debug_grad_computed;     ← 削除

    for (int i = 0; i < BATCH_SIZE; i++) {
        // ... backward計算 ...

        // atomicAdd削除！
    }

    // __syncthreads();  ← 不要な同期も削除
}
```

**追加効果: 52 it/s → 61 it/s (1.17倍高速化)**

## 原因5: `__launch_bounds__`の誤設定

5つ目の問題は、**launch bounds制約**だった。

### 問題のコード

```cuda
__global__ void __launch_bounds__(256, 2)
backward_kernel(...) {
    // ...
}
```

### `__launch_bounds__(maxThreadsPerBlock, minBlocksPerMultiprocessor)`とは？

これは、コンパイラに対する「ヒント」だ：

- `256`: 1 blockあたり最大256スレッド
- `2`: 1 SM(Streaming Multiprocessor)あたり最小2 block

コンパイラは、この制約を満たすようにレジスタ使用量を調整する。

### 何が問題なのか？

`minBlocksPerMultiprocessor = 2`は、**レジスタ使用量を厳しく制限**する。

RTX 5090の場合：

- レジスタ/SM: 65,536
- `minBlocks = 2`を保証するには: 65536 / 2 / 256 = **128レジスタ/スレッド**まで

Backward kernelは複雑な計算を行うため、自然にコンパイルすると150-200レジスタ/スレッド使う。これを128に制限すると、**レジスタスピル**(ローカルメモリへの退避)が発生する。

ローカルメモリはL1キャッシュ経由でアクセスされるが、レジスタよりはるかに遅い。

### なぜこの値が設定されていたのか？

Forward kernelからコピペしたテンプレートをそのまま使っていた。Forward kernelは軽量なので`(256, 2)`で問題なかったが、Backward kernelには不適切だった。

### 修正

```cuda
// 修正後: launch_boundsを削除（コンパイラに任せる）
__global__ void
backward_kernel(...) {
    // ...
}
```

コンパイラが自動的に最適なoccupancyを選択する。

**追加効果: 61 it/s → 74 it/s (1.21倍高速化)**

## 原因6: `std::getenv()`のホットパス呼び出し

最後の問題は、**環境変数取得のオーバーヘッド**だった。

### 問題のコード

```cuda
// backward.cu
void launch_backward(...) {
    // 毎回getenv()を呼ぶ！
    bool debug_mode = std::getenv("HYPER_DEBUG") != nullptr;

    backward_kernel<<<...>>>(...);
}
```

### 何が問題なのか？

`std::getenv()`は、**システムコール**だ。以下の処理が発生する：

1. 環境変数リストの線形探索
2. 文字列比較
3. カーネルモードへのコンテキストスイッチ(OS依存)

学習ループは1 iterationあたり数ms～数十msで回る。その中で、毎回getenv()を呼ぶのは無駄だ。

### 修正

```cpp
// 修正後: 初回のみ取得してキャッシュ
static bool g_debug_mode_cached = false;
static bool g_debug_mode = false;

void launch_backward(...) {
    if (!g_debug_mode_cached) {
        g_debug_mode = std::getenv("HYPER_DEBUG") != nullptr;
        g_debug_mode_cached = true;
    }

    backward_kernel<<<...>>>(...);
}
```

**追加効果: 74 it/s → 86 it/s (1.16倍高速化)**

## 修正結果: 20倍高速化の達成

すべての修正を適用した結果、以下の性能改善を達成した。

### Before / After

| 項目 | Before | After | 改善率 |
|------|--------|-------|--------|
| **Backward it/s** | **4.3** | **86** | **20倍** |
| Forward it/s | 81 | 81 | 変化なし |
| 全体 it/s (Forward+Backward) | 4.3 | 86 | 20倍 |

### 競合ライブラリとの比較

| 実装 | it/s | 備考 |
|------|------|------|
| HyperRasterizer (修正後) | **86** | 自作CUDA実装 |
| DGR (diff-gaussian-rasterization) | 78 | 競合ライブラリ |

**HyperRasterizerが10%高速**になった。デバッグコードを削除しただけで、競合を上回る性能を達成した。

### 修正の内訳

各修正の寄与度：

| 修正内容 | 改善率 | 累積it/s |
|----------|--------|----------|
| 初期状態 | - | 4.3 |
| 1. Global atomicAdd削除 | 5.3倍 | 23 |
| 2. `__threadfence()`削除 | 1.65倍 | 38 |
| 3. DIAGNOSTIC B削除 | 1.37倍 | 52 |
| 4. Shared memory atomic削除 | 1.17倍 | 61 |
| 5. `__launch_bounds__`修正 | 1.21倍 | 74 |
| 6. `std::getenv()`キャッシュ | 1.16倍 | 86 |

最大の効果は**Global atomicAddの削除**(5.3倍)だったが、他の5つの修正も積み重なって、最終的に20倍の高速化を実現した。

## 教訓: CUDAデバッグコードのチェックリスト

この経験から得られた教訓を、チェックリストにまとめた。

### デバッグコードを残してはいけない場所

- [ ] **Global `__device__` atomic操作** - すべてのスレッドが直列化される
- [ ] **`__threadfence()`** - 全スレッドがメモリアクセス完了を待機
- [ ] **Thread 0のみの大規模処理** - 他のスレッドが待機し続ける
- [ ] **Shared memory atomic** - Block内で競合が発生
- [ ] **毎iteration実行されるprintf** - カーネル実行を大幅に遅延
- [ ] **ホットパスのgetenv()** - システムコールのオーバーヘッド

### デバッグコードを残すなら

もしデバッグコードを残す必要がある場合、以下のガイドラインに従う：

```cuda
// 1. デフォルトでOFF、環境変数で明示的に有効化
#ifdef HYPER_DEBUG_MODE
    if (threadIdx.x == 0 && blockIdx.x == 0) {
        printf("Debug info: %d\n", value);
    }
#endif

// 2. プリプロセッサで完全に除去
#ifdef HYPER_COLLECT_STATS
    atomicAdd(&g_stats_counter, 1);
#endif

// 3. Constexprで最適化可能に
constexpr bool DEBUG_MODE = false;
if constexpr (DEBUG_MODE) {
    // コンパイル時に削除される
}
```

### コンパイルフラグ管理

```bash
# 本番ビルド（デバッグコードなし）
nvcc -O3 backward.cu

# デバッグビルド（デバッグコード有効）
nvcc -O3 -DHYPER_DEBUG_MODE -DHYPER_COLLECT_STATS backward.cu
```

本番とデバッグで明確に分離する。

### プロファイリングの重要性

今回の問題は、**Nsight Compute**のプロファイリングで初めて発覚した。

以下の指標が異常値を示したら、デバッグコードを疑うべき：

- **Warp Stall (Memory Throttle) > 50%** → Atomic競合またはメモリ待機
- **Achieved Occupancy < 30%** → レジスタスピルまたは同期オーバーヘッド
- **Global Atomic Throughput が異常に高い** → 不要なatomic操作

定期的にプロファイリングを行い、パフォーマンス異常を早期発見する。

## まとめ

CUDAカーネルのデバッグコードは、**本番環境に残してはいけない**。

特に以下の3つは、致命的な性能劣化を引き起こす：

1. **Global atomic操作** - すべてのスレッドが直列化
2. **`__threadfence()`** - 全スレッドがメモリ待機
3. **Thread 0の大規模処理** - 並列性の完全喪失

HyperRasterizerでは、これらのデバッグコードが20倍の性能劣化を引き起こしていた。削除した結果、競合ライブラリを上回る性能を達成した。

**教訓: デバッグコードは本番から除去せよ。プロファイリングを怠るな。**

## 参考

- [NVIDIA CUDA C++ Programming Guide - Atomic Functions](https://docs.nvidia.com/cuda/cuda-c-programming-guide/index.html#atomic-functions)
- [NVIDIA CUDA C++ Best Practices Guide - Memory Fence Functions](https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/index.html#memory-fence-functions)
- [NVIDIA Nsight Compute - Profiling Guide](https://docs.nvidia.com/nsight-compute/ProfilingGuide/index.html)
- [HyperRasterizer GitHub Repository](https://github.com/amabito/hyper-rasterizer)

---

この記事が、CUDA開発で同じ罠にハマる人を減らす助けになれば幸いです。
