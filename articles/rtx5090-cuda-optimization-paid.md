---
title: "【有料】RTX 5090 CUDA最適化：実測データとテンプレート化の全技術"
emoji: "🔥"
type: "tech"
topics: ["cuda", "gpu", "rtx5090", "blackwell", "最適化"]
published: true
price: 980
---

# この記事で得られるもの

- RTX 5090での**実測ベンチマークデータ**
- GPU世代別の**テンプレート化実装**（コピペ可）
- **L2キャッシュ活用**の具体的手法
- Warp Reductionが**逆効果だった詳細分析**

**対象読者:** RTX 5090/4090を持っている人、CUDA最適化に興味がある人

---

# 無料記事のおさらい

- RTX 5090はL2キャッシュ96MB、Atomicが超高速
- 古い最適化テクニック（Warp Reduction）が逆効果になることがある
- GPU検出してパラメータを変えることが重要

今回は**実測データと具体的な実装**を解説する。

---

:::message
ここから有料パートです。
:::

# 詳細ベンチマーク

## テスト環境

| 項目 | スペック |
|------|---------|
| GPU | RTX 5090 32GB |
| Driver | 591.74 |
| CUDA | 12.8 |
| OS | Windows 11 |

## Forward Pass（3D Gaussian Splatting）

| Gaussians | 解像度 | FPS | L2 Hit Rate |
|-----------|--------|-----|-------------|
| 100K | 800x600 | 2428 | 89% |
| 100K | 1920x1080 | 2387 | 85% |
| 500K | 1920x1080 | 1628 | 72% |
| 1M | 800x600 | 1153 | 68% |
| 1M | 1920x1080 | 1000 | 61% |

**注目ポイント**: 100K Gaussiansまでは解像度を上げてもFPSがほぼ変わらない。L2キャッシュにデータが載っているため。

## Backward Pass比較

| 手法 | 時間 | 備考 |
|------|------|------|
| 直接Atomic | 61ms | ベースライン |
| Quad Reduction | 52ms | 4x削減、15%改善 |
| Warp Reduction | 400ms | **6.5倍遅い** |
| Block Reduction | 280ms | 4.6倍遅い |

---

# GPU世代別テンプレート化

## runtime_config.h

```cpp
#pragma once
#include <cuda_runtime.h>

struct RuntimeConfig {
    int batch_size;
    bool use_fast_math;
    bool use_templates;
    size_t shared_mem_size;
    size_t l2_cache_size;
};

inline RuntimeConfig get_runtime_config() {
    int device;
    cudaGetDevice(&device);

    int sm_major, sm_minor;
    cudaDeviceGetAttribute(&sm_major, cudaDevAttrComputeCapabilityMajor, device);
    cudaDeviceGetAttribute(&sm_minor, cudaDevAttrComputeCapabilityMinor, device);
    int sm = sm_major * 10 + sm_minor;

    int shared_mem;
    cudaDeviceGetAttribute(&shared_mem, cudaDevAttrMaxSharedMemoryPerBlock, device);

    size_t l2_size;
    cudaDeviceGetAttribute((int*)&l2_size, cudaDevAttrL2CacheSize, device);

    RuntimeConfig config;

    if (sm >= 120) {
        // Blackwell (RTX 5090)
        config.batch_size = 512;
        config.use_fast_math = true;
        config.use_templates = true;
    } else if (sm >= 89) {
        // Ada Lovelace (RTX 4090)
        config.batch_size = 512;
        config.use_fast_math = true;
        config.use_templates = true;
    } else if (sm >= 86) {
        // Ampere (RTX 3090)
        config.batch_size = 256;
        config.use_fast_math = true;
        config.use_templates = true;
    } else if (sm >= 75) {
        // Turing (RTX 2080)
        config.batch_size = 256;
        config.use_fast_math = true;
        config.use_templates = true;
    } else if (sm >= 60) {
        // Pascal (GTX 1080)
        config.batch_size = 128;
        config.use_fast_math = false;
        config.use_templates = true;
    } else {
        // Unknown / Legacy
        config.batch_size = 64;
        config.use_fast_math = false;
        config.use_templates = false;
    }

    config.shared_mem_size = shared_mem;
    config.l2_cache_size = l2_size;

    return config;
}

inline void log_runtime_config() {
    static bool logged = false;
    if (logged) return;
    logged = true;

    auto config = get_runtime_config();

    int device;
    cudaGetDevice(&device);
    cudaDeviceProp prop;
    cudaGetDeviceProperties(&prop, device);

    printf("GPU: %s (SM %d.%d)\n", prop.name, prop.major, prop.minor);
    printf("Config: Batch=%d, FastMath=%s, L2=%zuMB\n",
           config.batch_size,
           config.use_fast_math ? "ON" : "OFF",
           config.l2_cache_size / 1024 / 1024);
}
```

## テンプレート化されたカーネル

```cuda
template<int BATCH_SIZE, bool USE_FAST_MATH>
__global__ void process_kernel(float* data, int N) {
    __shared__ float shared_data[BATCH_SIZE];

    int tid = threadIdx.x;
    int gid = blockIdx.x * BATCH_SIZE + tid;

    if (gid < N) {
        float val = data[gid];

        // Fast Mathの条件分岐はコンパイル時に解決
        if constexpr (USE_FAST_MATH) {
            val = __expf(val);
        } else {
            val = expf(val);
        }

        shared_data[tid] = val;
    }

    __syncthreads();

    // ... 処理 ...
}

// ディスパッチャー
void process(float* data, int N) {
    auto config = get_runtime_config();

    dim3 block(config.batch_size);
    dim3 grid((N + config.batch_size - 1) / config.batch_size);

    if (config.batch_size == 512 && config.use_fast_math) {
        process_kernel<512, true><<<grid, block>>>(data, N);
    } else if (config.batch_size == 256 && config.use_fast_math) {
        process_kernel<256, true><<<grid, block>>>(data, N);
    } else if (config.batch_size == 128) {
        process_kernel<128, false><<<grid, block>>>(data, N);
    } else {
        // 動的フォールバック
        process_kernel_dynamic<<<grid, block>>>(data, N, config);
    }
}
```

---

# Warp Reductionが遅かった理由

## 実装

```cuda
__device__ float warp_reduce_sum(float val) {
    for (int offset = 16; offset > 0; offset /= 2) {
        val += __shfl_down_sync(0xFFFFFFFF, val, offset);
    }
    return val;
}

__global__ void backward_with_warp_reduction(...) {
    float local_grad = compute_gradient();

    // Warp内で集約
    float warp_sum = warp_reduce_sum(local_grad);

    // Lane 0だけがAtomic
    if ((threadIdx.x & 31) == 0) {
        atomicAdd(&global_grad, warp_sum);
    }
}
```

## なぜ遅いのか

**理論**: Atomic操作が32分の1になる → 速くなるはず

**現実（RTX 5090）**:

1. **shuffle命令のレイテンシ**
   - `__shfl_down_sync` × 5回 = 数十サイクル
   - この間、他の処理が止まる

2. **L2キャッシュの効率**
   - RTX 5090のL2は96MB、Atomicアドレスがほぼ全てキャッシュに載る
   - 直接Atomicでもキャッシュヒットする

3. **Atomicユニットの強化**
   - Blackwell世代はAtomicユニットが大幅強化
   - 競合があっても高スループット

## 結論

```
Warp Reduction: shuffle 5回 + sync = 高コスト
直接Atomic: L2キャッシュヒット + 強力なAtomicユニット = 低コスト
```

**RTX 5090では、Warp Reductionのオーバーヘッド > Atomicの競合コスト**

---

# L2キャッシュ活用の実践

## データ配置の最適化

```cpp
// NG: 構造体の配列（AoS）
struct Gaussian {
    float3 position;    // 12 bytes
    float4 rotation;    // 16 bytes
    float3 scale;       // 12 bytes
    float opacity;      // 4 bytes
    float sh_coeffs[48]; // 192 bytes
};
Gaussian* gaussians;  // アクセスがバラバラ

// OK: 配列の構造体（SoA）
struct GaussianData {
    float3* positions;   // 連続
    float4* rotations;   // 連続
    float3* scales;      // 連続
    float* opacities;    // 連続
    float* sh_coeffs;    // 連続
};
```

SoAにすると、同じ属性へのアクセスが連続になり、L2キャッシュ効率が上がる。

## キャッシュサイズを意識した分割

```cpp
void process_large_data(float* data, size_t total_size) {
    auto config = get_runtime_config();
    size_t l2_size = config.l2_cache_size;

    // L2キャッシュに収まるチャンクに分割
    size_t chunk_size = l2_size / sizeof(float) * 0.8;  // 80%使用

    for (size_t offset = 0; offset < total_size; offset += chunk_size) {
        size_t current_chunk = min(chunk_size, total_size - offset);
        process_chunk(data + offset, current_chunk);
        // 次のチャンク処理前にL2が入れ替わる
    }
}
```

---

# まとめ

RTX 5090での最適化で学んだこと:

| 項目 | 学び |
|------|------|
| Warp Reduction | 逆効果。L2キャッシュとAtomicが強い |
| Quad Reduction | 効果あり。4スレッド集約は有効 |
| テンプレート化 | 必須。GPU世代別に最適化 |
| L2キャッシュ | 96MBを意識したデータ配置 |
| Fast Math | 積極的に使う。精度低下は実用上問題なし |

**最重要**: 理論を信じず、必ず実測する。

---

# 参考

- [CUDA C++ Programming Guide](https://docs.nvidia.com/cuda/cuda-c-programming-guide/)
- [NVIDIA Blackwell Architecture Whitepaper](https://www.nvidia.com/en-us/data-center/technologies/blackwell-architecture/)
