---
title: "【有料】CUDAメモリプールで15%高速化した実装【コピペ可】"
emoji: "🔥"
type: "tech"
topics: ["cuda", "gpu", "メモリ管理", "最適化"]
published: true
published_at: "2026-01-09 12:00"
price: 1480
---

# この記事で得られるもの

**毎フレームのcudaMallocを排除したら15%速くなった。**

- フレームベース**メモリプールの設計思想**
- **grow()処理**の安全な実装方法
- first-frame bugの**根本原因と対策**
- binning推定の**適切なパラメータ設定**

**対象読者:** CUDAでリアルタイム処理を実装している人

---

# 無料記事のおさらい

- cudaMallocはメモリを初期化しない → first-frame bug
- サイズ推定が過大だと73GB問題が発生
- 解決: cudaMemset、控えめな推定、ハードキャップ

今回は**メモリプールの完全実装**を解説する。

---

:::message
ここから有料パートです。
:::

# なぜメモリプールが必要か

## cudaMallocのオーバーヘッド

```cuda
// 毎フレームallocate
void render_frame() {
    float* buffer;
    cudaMalloc(&buffer, size);  // 2-5ms
    // ... rendering ...
    cudaFree(buffer);           // 1-2ms
}
```

毎フレーム3-7msのオーバーヘッド。60FPSなら**16.6ms以内**に収める必要があるのに、メモリ操作だけで半分近く消費する。

## メモリプールのメリット

```
初回: cudaMallocで大きなプールを確保
毎フレーム: プールからポインタを返すだけ（ほぼ0ms）
```

---

# メモリプール実装

## memory_pool.h

```cpp
#pragma once
#include <cuda_runtime.h>
#include <cstdio>
#include <cstdlib>

class FrameMemoryPool {
private:
    char* pool_ptr = nullptr;
    size_t pool_size = 0;
    size_t current_offset = 0;
    bool initialized = false;

    static constexpr size_t ALIGNMENT = 256;  // CUDAのアライメント要件

    size_t align_up(size_t size) {
        return (size + ALIGNMENT - 1) & ~(ALIGNMENT - 1);
    }

public:
    ~FrameMemoryPool() {
        if (pool_ptr) {
            cudaFree(pool_ptr);
        }
    }

    bool init(size_t initial_size) {
        if (initialized) return true;

        cudaError_t err = cudaMalloc(&pool_ptr, initial_size);
        if (err != cudaSuccess) {
            fprintf(stderr, "MemoryPool init failed: %s\n",
                    cudaGetErrorString(err));
            return false;
        }

        // ゼロ初期化（first-frame bug対策）
        cudaMemset(pool_ptr, 0, initial_size);

        pool_size = initial_size;
        initialized = true;

        printf("MemoryPool initialized: %.2f MB\n",
               pool_size / (1024.0 * 1024.0));
        return true;
    }

    void* allocate(size_t size) {
        if (!initialized) {
            fprintf(stderr, "MemoryPool not initialized!\n");
            return nullptr;
        }

        size = align_up(size);

        if (current_offset + size > pool_size) {
            // プールが足りない → grow
            if (!grow(current_offset + size)) {
                return nullptr;
            }
        }

        void* ptr = pool_ptr + current_offset;
        current_offset += size;
        return ptr;
    }

    bool grow(size_t required_size) {
        size_t new_size = pool_size;
        while (new_size < required_size) {
            new_size *= 2;
        }

        // 上限チェック（8GB）
        if (new_size > 8ULL * 1024 * 1024 * 1024) {
            fprintf(stderr, "MemoryPool grow failed: exceeds 8GB limit\n");
            return false;
        }

        printf("MemoryPool growing: %.2f MB -> %.2f MB\n",
               pool_size / (1024.0 * 1024.0),
               new_size / (1024.0 * 1024.0));

        char* new_ptr;
        cudaError_t err = cudaMalloc(&new_ptr, new_size);
        if (err != cudaSuccess) {
            fprintf(stderr, "MemoryPool grow failed: %s\n",
                    cudaGetErrorString(err));
            return false;
        }

        // ゼロ初期化
        cudaMemset(new_ptr, 0, new_size);

        // 古いデータをコピー（必要な場合）
        if (pool_ptr && current_offset > 0) {
            cudaMemcpy(new_ptr, pool_ptr, current_offset,
                       cudaMemcpyDeviceToDevice);
        }

        // 古いプールを解放
        if (pool_ptr) {
            cudaFree(pool_ptr);
        }

        pool_ptr = new_ptr;
        pool_size = new_size;
        return true;
    }

    void reset() {
        current_offset = 0;
        // 注意: メモリ内容はリセットしない（パフォーマンスのため）
    }

    size_t get_used() const { return current_offset; }
    size_t get_capacity() const { return pool_size; }
};

// グローバルインスタンス
inline FrameMemoryPool& get_memory_pool() {
    static FrameMemoryPool pool;
    return pool;
}
```

## 使い方

```cpp
// 初期化（プログラム開始時に1回）
get_memory_pool().init(512 * 1024 * 1024);  // 512MB

// フレーム開始時
get_memory_pool().reset();

// 各処理でallocate
float* buffer1 = (float*)get_memory_pool().allocate(size1);
float* buffer2 = (float*)get_memory_pool().allocate(size2);
// ... rendering ...

// フレーム終了時（何もしない、resetは次フレーム開始時）
```

---

# grow()の罠

## 問題: 既存ポインタの無効化

```cpp
void* ptr1 = pool.allocate(100);  // ptr1 = pool + 0
void* ptr2 = pool.allocate(100);  // ptr2 = pool + 100

// ここでgrow()が呼ばれると...
void* ptr3 = pool.allocate(huge_size);  // grow発生

// ptr1, ptr2 は無効になる！
// 古いpoolは解放され、新しいアドレスに移動
```

## 解決策1: フレーム境界でのみgrow

```cpp
void frame_start() {
    auto& pool = get_memory_pool();
    pool.reset();

    // 前フレームの使用量を記録
    static size_t last_used = 0;

    // 必要に応じて事前grow
    if (last_used > pool.get_capacity() * 0.8) {
        pool.grow(last_used * 1.5);
    }

    last_used = pool.get_used();
}
```

## 解決策2: 環境変数でメモリプールを無効化

開発中は無効化できると便利。

```cpp
bool use_memory_pool() {
    static int use = -1;
    if (use < 0) {
        const char* env = getenv("DISABLE_MEMORY_POOL");
        use = (env && strcmp(env, "1") == 0) ? 0 : 1;
    }
    return use == 1;
}

void* allocate_buffer(size_t size) {
    if (use_memory_pool()) {
        return get_memory_pool().allocate(size);
    } else {
        void* ptr;
        cudaMalloc(&ptr, size);
        cudaMemset(ptr, 0, size);
        return ptr;
    }
}
```

---

# binning推定の詳細

## パラメータの決め方

```cpp
struct BinningEstimator {
    // 推定パラメータ
    float tile_coverage_ratio = 0.05f;  // 各Gaussianが影響するタイルの割合
    int max_tiles_per_gaussian = 256;    // タイル数の上限
    size_t hard_cap = 4ULL * 1024 * 1024 * 1024;  // 4GB

    size_t estimate(int num_gaussians, int num_tiles) {
        // 基本推定
        size_t avg_tiles = (size_t)(num_tiles * tile_coverage_ratio);
        avg_tiles = std::min(avg_tiles, (size_t)max_tiles_per_gaussian);

        // binningに必要なメモリ
        size_t keys_size = num_gaussians * avg_tiles * sizeof(uint64_t);
        size_t values_size = num_gaussians * avg_tiles * sizeof(uint32_t);
        size_t ranges_size = num_tiles * sizeof(int2);

        size_t total = keys_size + values_size + ranges_size;

        // ハードキャップ適用
        return std::min(total, hard_cap);
    }
};
```

## 実測値に基づく調整

```cpp
void calibrate_estimator(BinningEstimator& est,
                         int num_gaussians, int num_tiles,
                         size_t actual_used) {
    // 実際の使用量から逆算
    float actual_ratio = (float)actual_used /
                         (num_gaussians * num_tiles * sizeof(uint64_t));

    // 移動平均で更新
    est.tile_coverage_ratio = est.tile_coverage_ratio * 0.9f +
                              actual_ratio * 1.2f * 0.1f;  // 20%マージン

    printf("Binning calibration: ratio=%.4f\n", est.tile_coverage_ratio);
}
```

---

# デバッグツール

## メモリ使用量トラッカー

```cpp
class MemoryTracker {
    struct Allocation {
        void* ptr;
        size_t size;
        const char* name;
    };
    std::vector<Allocation> allocations;

public:
    void* track_alloc(size_t size, const char* name) {
        void* ptr;
        cudaMalloc(&ptr, size);
        allocations.push_back({ptr, size, name});
        return ptr;
    }

    void print_report() {
        size_t total = 0;
        printf("=== Memory Report ===\n");
        for (const auto& a : allocations) {
            printf("  %s: %.2f MB\n", a.name, a.size / 1e6);
            total += a.size;
        }
        printf("Total: %.2f MB\n", total / 1e6);
    }
};
```

---

# まとめ

| 問題 | 解決策 |
|------|--------|
| cudaMallocオーバーヘッド | フレームベースメモリプール |
| first-frame bug | init/growでcudaMemset |
| 73GB問題 | 控えめな推定 + ハードキャップ |
| grow時のポインタ無効化 | フレーム境界でのみgrow |

**教訓: CUDAメモリ管理は罠だらけ。初期化とサイズ推定に注意。**
