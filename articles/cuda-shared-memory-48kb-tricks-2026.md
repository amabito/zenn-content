---
title: "CUDA共有メモリ48KB制限を突破する3つのテクニック【実装例付き】"
emoji: "🧠"
type: "tech"
topics: ["CUDA", "GPU", "パフォーマンス最適化", "共有メモリ"]
published: true
---

## TL;DR

CUDA共有メモリは48KB制限があり、**`__shared__`はコンパイル時に確保される**ため、`if`文で囲んでも節約できない。解決策は`std::conditional_t`でコンパイル時型切り替え、動的共有メモリ、またはマルチパス戦略。

## 突然のビルドエラー

```bash
ptxas error: Entry function 'renderCUDA' uses too much shared data (0xcc20 bytes, 0xc000 max)
```

**0xcc20 = 52,256バイト、0xc000 = 49,152バイト（48KB）**

「あれ？パフォーマンス改善のためにバッファを追加しただけなのに…」

## 罠1：`if`文で囲んでも共有メモリは確保される

### ❌ 動かないコード

```cpp
template<int BATCH_SIZE>
__global__ void kernel(...) {
    __shared__ float base_buffer[1024];  // 4KB

    // 「BATCH_SIZE が小さい時だけ使う」つもり
    if (BATCH_SIZE <= 256) {
        __shared__ float large_buffer[6144];  // 24KB
        // ... 処理 ...
    }
}
```

**実際の共有メモリ使用量: 4KB + 24KB = 28KB（常に確保される）**

### なぜ？

`__shared__`はC++の**ストレージ指定子**であり、**コンパイル時**にメモリレイアウトが決定される。`if`文は実行時の条件分岐なので、メモリ確保には影響しない。

これは以下と同じ：

```cpp
void function(bool use_feature) {
    int x = 10;  // 常にスタックに確保

    if (use_feature) {
        int large_array[10000];  // 常にスタックに確保（ifに関係なく）
    }
}
```

## CUDA共有メモリの基礎知識

### 48KB制限の理由

| GPU世代 | 共有メモリ/Block | レジスタ/Block |
|---------|-----------------|---------------|
| Kepler (2012) | 48KB | 64K |
| Maxwell (2014) | 48KB | 64K |
| Pascal (2016) | 48KB | 64K |
| Volta (2017) | 96KB* | 64K |
| Ampere (2020) | 164KB* | 64K |
| Blackwell (2024) | 228KB* | 64K |

*設定可能だが、デフォルトは48KB/Blockの制約。L1キャッシュとのトレードオフ。

### 共有メモリの確認方法

```bash
nvcc --ptxas-options=-v kernel.cu
```

出力例：
```
ptxas info: Used 45 registers, 24576 bytes smem, 352 bytes cmem[0]
```

**24576バイト = 24KB**

## テクニック1：`std::conditional_t`でコンパイル時型切り替え

### ✅ 正しいコード

```cpp
#include <type_traits>

// プレースホルダ型（ダミー）
struct Placeholder { char dummy; };

// 実際のバッファ型
struct LargeBuffer {
    float data[6144];  // 24KB
};

template<int BATCH_SIZE>
__global__ void kernel(...) {
    __shared__ float base_buffer[1024];  // 4KB

    // コンパイル時条件判定
    constexpr bool use_large_buffer = (BATCH_SIZE <= 256);

    // 型をコンパイル時に切り替え
    using BufferType = std::conditional_t<use_large_buffer,
                                          LargeBuffer,      // true時
                                          Placeholder>;     // false時

    __shared__ BufferType buffer;

    // 実行時ガード（型安全性のため）
    if constexpr (use_large_buffer) {
        // buffer.data を使った処理
    }
}
```

### 確保される共有メモリ量

```cpp
// BATCH_SIZE=128 でインスタンス化
kernel<128><<<...>>>();
// → BufferType = LargeBuffer
// → 共有メモリ: 4KB + 24KB = 28KB ✅

// BATCH_SIZE=512 でインスタンス化
kernel<512><<<...>>>();
// → BufferType = Placeholder
// → 共有メモリ: 4KB + 1byte = 4KB ✅
```

### 実例：TileLocalBuffer

実際のプロジェクト（HyperRasterizer Phase 11）で遭遇した問題：

```cpp
struct TileLocalBuffer {
    int gaussian_ids[512];    // 2KB
    float depths[512];        // 2KB
    float2 coords[512];       // 4KB
    // ... その他フィールド
    // 合計: 26KB
};

__global__ void renderCUDA(...) {
    __shared__ float base_data[6144];  // 24KB（既存）
    __shared__ TileLocalBuffer tile_buffer;  // 26KB（新規追加）

    // 合計: 50KB > 48KB 💀
}
```

**修正：**

```cpp
constexpr int MAX_UNIQUE_GAUSSIANS = 512;

template<int BATCH_SIZE>
struct TileLocalBufferImpl {
    // BATCH_SIZE <= 256 なら 128、それ以外なら 32
    static constexpr int capacity = (BATCH_SIZE <= 256) ? 128 : 32;

    int gaussian_ids[capacity];
    float depths[capacity];
    // ... 他フィールドも同様
};

template<int BATCH_SIZE>
__global__ void renderCUDA(...) {
    __shared__ float base_data[6144];  // 24KB

    constexpr bool tile_local_available = (BATCH_SIZE <= 256);

    using TileLocalType = std::conditional_t<
        tile_local_available,
        TileLocalBufferImpl<BATCH_SIZE>,  // 128要素 = 7KB
        Placeholder                        // 1byte
    >;

    __shared__ TileLocalType tile_buffer;

    if constexpr (tile_local_available) {
        // 安全に使用
    }
}
```

**結果：**
- BATCH_SIZE=128: 24KB + 7KB = 31KB ✅
- BATCH_SIZE=512: 24KB + 1byte = 24KB ✅

## テクニック2：動的共有メモリ

### extern __shared__の使い方

```cpp
template<int BATCH_SIZE>
__global__ void kernel(...) {
    // 動的共有メモリ（サイズはカーネル起動時に指定）
    extern __shared__ char shared_mem[];

    // 手動でレイアウト
    float* base_buffer = (float*)shared_mem;
    float* large_buffer = (float*)(shared_mem + 4096);  // 4KB後
}
```

カーネル起動：

```cpp
int smem_size = (BATCH_SIZE <= 256) ? 28 * 1024 : 4 * 1024;  // 実行時決定
kernel<BATCH_SIZE><<<blocks, threads, smem_size>>>(...);
```

### メリット・デメリット

| 項目 | 静的 (`__shared__`) | 動的 (`extern __shared__`) |
|------|-------------------|---------------------------|
| 型安全性 | ✅ 高い | ❌ キャスト必要 |
| コンパイル時最適化 | ✅ 可能 | ❌ 制限あり |
| 柔軟性 | ❌ テンプレート必要 | ✅ 実行時サイズ変更可 |
| バンクコンフリクト回避 | ✅ コンパイラ最適化 | ⚠️ 手動調整必要 |

### 使い分け

- **静的**: パフォーマンス重視、テンプレート可能
- **動的**: 実行時にサイズ決定が必要、柔軟性重視

## テクニック3：マルチパス戦略

### 概念

1つのカーネルで全て処理せず、複数のカーネルに分割：

```cpp
// ❌ 単一カーネル（共有メモリ大）
__global__ void bigKernel() {
    __shared__ float buffer1[6144];  // 24KB
    __shared__ float buffer2[6144];  // 24KB
    __shared__ int indices[2048];    // 8KB
    // 合計: 56KB 💀

    // Pass 1処理
    // Pass 2処理
}

// ✅ 分割（共有メモリ小）
__global__ void pass1Kernel() {
    __shared__ float buffer1[6144];  // 24KB
    __shared__ int indices[2048];    // 8KB
    // 合計: 32KB ✅
}

__global__ void pass2Kernel() {
    __shared__ float buffer2[6144];  // 24KB
    // 合計: 24KB ✅
}
```

### いつ使うか？

- 処理が自然に分割できる場合
- カーネル起動オーバーヘッドが許容できる場合
- グローバルメモリ帯域幅に余裕がある場合

### トレードオフ

```
共有メモリ削減 vs カーネル起動オーバーヘッド
```

典型的なオーバーヘッド：
- カーネル起動: ~5-10μs
- 共有メモリバンクコンフリクト回避: ~数百ns/アクセス

**経験則**: カーネル内ループ回数 > 1000 ならマルチパス検討価値あり。

## 実践：共有メモリ予算計算

### ステップ1：現在の使用量を確認

```bash
nvcc --ptxas-options=-v,-warn-on-spills kernel.cu 2>&1 | grep smem
```

出力：
```
ptxas info: Used 24576 bytes smem
```

### ステップ2：追加したいバッファのサイズ計算

```cpp
struct NewBuffer {
    float data[512];       // 2KB
    int indices[256];      // 1KB
    float2 coords[256];    // 2KB
};
// 合計: 5KB
```

### ステップ3：バジェット確認

```
現在: 24KB
追加: 5KB
合計: 29KB < 48KB ✅
```

**ただし、コンパイラオーバーヘッドで+10-20%見込むべき**：

```
安全な予算: 48KB * 0.8 = 38KB
現在: 24KB
残り: 14KB
追加可能: 5KB ✅（余裕あり）
```

## クイックリファレンステーブル

| 構造体サイズ | BATCH_SIZE=128 | BATCH_SIZE=256 | BATCH_SIZE=512 | 推奨手法 |
|-------------|----------------|----------------|----------------|---------|
| < 8KB       | ✅             | ✅             | ✅             | 静的確保 |
| 8-16KB      | ✅             | ✅             | ❌             | `conditional_t` |
| 16-24KB     | ✅             | ⚠️             | ❌             | `conditional_t` |
| 24-40KB     | ⚠️             | ❌             | ❌             | 動的 or マルチパス |
| > 40KB      | ❌             | ❌             | ❌             | 再設計必要 |

## デバッグコマンド集

### 1. 共有メモリ使用量確認

```bash
nvcc --ptxas-options=-v kernel.cu 2>&1 | grep "bytes smem"
```

### 2. レジスタ使用量も確認

```bash
nvcc --ptxas-options=-v kernel.cu 2>&1 | grep "Used"
```

出力：
```
ptxas info: Used 45 registers, 24576 bytes smem, 352 bytes cmem[0]
```

### 3. 占有率計算

```bash
# CUDA Occupancy Calculator（GUIツール）
/usr/local/cuda/tools/CUDA_Occupancy_Calculator.xls

# コマンドライン
cuda-occupancy-calculator \
  --registers 45 \
  --shared-memory 24576 \
  --threads-per-block 256
```

### 4. Nsight Computeで実測

```bash
ncu --set full --kernel-name "renderCUDA" ./app
```

確認項目：
- `smem_per_block`: 実際の共有メモリ使用量
- `occupancy`: 占有率（低いとパフォーマンス低下）

## まとめ

1. **`__shared__`はコンパイル時確保、`if`では制御できない**
2. **`std::conditional_t`でコンパイル時型切り替えが最適**
3. **動的共有メモリは柔軟だが型安全性が低い**
4. **マルチパス戦略はトレードオフに注意**
5. **予算計算時は80%ルール（オーバーヘッド考慮）**
6. **`nvcc --ptxas-options=-v`で必ず検証**

## 参考資料

- [CUDA C++ Programming Guide - Shared Memory](https://docs.nvidia.com/cuda/cuda-c-programming-guide/index.html#shared-memory)
- [CUDA C++ Best Practices Guide - Shared Memory](https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/index.html#shared-memory)
- [Nsight Compute - Memory Analysis](https://docs.nvidia.com/nsight-compute/)

---

この記事は実際のプロジェクト（HyperRasterizer Phase 11、2026-01-30）で遭遇した問題の解決策に基づいています。TileLocalBufferの追加で50KB超過エラーが発生し、`std::conditional_t`で26KB→7KBに削減して解決しました。
