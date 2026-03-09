---
title: "CUDAの共有メモリが48KBを超えた: std::conditional_tで解決した話"
emoji: "💾"
type: "tech"
topics: ["cuda", "cpp", "gpu", "3dgs", "optimization"]
published: false
published_at: "2026-02-26 18:00"
---

## エラーから始まった

3DGSレンダラーの最適化中、突然ビルドが止まった。

```
ptxas error: Entry function 'hypersplat_forward_cuda_kernel'
uses too much shared data (0xcc20 bytes, 0xc000 max)
```

`0xcc20`は52,256バイト。`0xc000`は49,152バイト（48KB）。

**4,160バイトオーバー**していた。

---

## 何をしたのか

TileLocalBufferという構造体を共有メモリに追加した。タイル内のGaussianをローカルでキャッシュして、グローバルメモリアクセスを削減する最適化だ。

```cpp
struct TileLocalBuffer {
    float3 means2D[MAX_UNIQUE_GAUSSIANS];   // Gaussianの2D座標
    float4 conic_opacity[MAX_UNIQUE_GAUSSIANS];  // 円錐パラメータ
    float3 colors[MAX_UNIQUE_GAUSSIANS];    // RGB
    // ...
};

template<int BATCH_SIZE>
__global__ void hypersplat_forward_cuda_kernel(...) {
    __shared__ TileLocalBuffer tile_buf;  // これを追加
    __shared__ float existing_buf[6144]; // 既存の24KB
    // ...
}
```

`MAX_UNIQUE_GAUSSIANS = 512`のとき、`TileLocalBuffer`は約26KB。

既存の24KBと合わせて**50KB > 48KB**でオーバーした。

---

## 最初に試みた「if文で囲む」は効かない

「BATCH_SIZEが小さいときだけ使おう」と考えた。

```cpp
template<int BATCH_SIZE>
__global__ void kernel(...) {
    if constexpr (BATCH_SIZE <= 256) {
        __shared__ TileLocalBuffer tile_buf;  // ← コンパイル時に確保される
        // ...
    }
    __shared__ float existing_buf[6144];
}
```

**これは機能しない。**

`__shared__`キーワードはコンパイル時にメモリを確保する。`if constexpr`で囲んでも、コンパイラはそのテンプレートインスタンス全体のメモリを確保しようとする。

```bash
# BATCH_SIZE=512でもエラーが出続ける
ptxas error: uses too much shared data (0xcc20 bytes, 0xc000 max)
```

実行時条件での分岐も同様に無効だ。

```cpp
// これも効かない
__shared__ TileLocalBuffer tile_buf;  // 確保される
if (use_tile_local && BATCH_SIZE <= 256) {
    // 使わなくてもメモリは確保済み
}
```

---

## 解決策: `std::conditional_t` でコンパイル時型切り替え

`<type_traits>`の`std::conditional_t`を使う。

```cpp
#include <type_traits>

// サイズ1バイトのプレースホルダー
struct TileLocalPlaceholder {
    char dummy;
};

template<int BATCH_SIZE>
__global__ void hypersplat_forward_cuda_kernel(...) {

    // コンパイル時の判定
    constexpr bool tile_local_available = (BATCH_SIZE <= 256);

    // 型をコンパイル時に切り替え
    using TileLocalType = std::conditional_t<
        tile_local_available,
        TileLocalBuffer,      // BATCH_SIZE <= 256: 実バッファ（26KB）
        TileLocalPlaceholder  // BATCH_SIZE > 256: 1バイト
    >;

    __shared__ TileLocalType tile_buf;       // BATCH_SIZE次第で26KBまたは1B
    __shared__ float existing_buf[6144];     // 常に24KB

    // 実行時ガード（コンパイル時フラグと組み合わせ）
    const bool use_tile_local = tile_local_enabled && tile_local_available;

    // コンパイル時分岐で使用
    if constexpr (tile_local_available) {
        if (use_tile_local) {
            // tile_bufを使った最適化パス
            load_tile_local(tile_buf, ...);
        }
    }
}
```

### メモリ使用量の変化

| BATCH_SIZE | 旧（TileLocalBuffer） | 新（conditional_t） |
|-----------|---------------------|-------------------|
| 128 | 50KB（エラー） | 31KB（OK） |
| 256 | 50KB（エラー） | 31KB（OK） |
| 512 | 50KB（エラー） | 25KB（OK） |

BATCH_SIZE > 256のとき、`TileLocalPlaceholder`（1バイト）に切り替わるため、既存の24KBのみになる。

---

## MAX_UNIQUE_GAUSSIANSのチューニング

`std::conditional_t`に加えて、バッファサイズ自体も削減した。

```cpp
// 変更前: 512 → 26KB
static constexpr int MAX_UNIQUE_GAUSSIANS = 512;

// 変更後: 128 → 7KB
static constexpr int MAX_UNIQUE_GAUSSIANS = 128;
```

これで共有メモリ使用量の内訳は：
- `TileLocalBuffer`: 26KB → **7KB**（128 Gaussians）
- `existing_buf`: 24KB（変更なし）
- 合計: 50KB → **31KB**（48KB以内に収まる）

128 Gaussiansで十分な理由：実際のタイルあたりの平均Gaussian数が100〜200程度であり、512は過剰設計だった。

---

## 共有メモリ使用量の確認方法

ビルド時に`--ptxas-options=-v`を追加すると、各カーネルの使用量が見える。

```bash
nvcc --ptxas-options=-v -arch=sm_120 kernel.cu
```

出力例：

```
ptxas info: Compiling entry function 'hypersplat_forward_cuda_kernel' for 'sm_120'
ptxas info: Used 64 registers, 31744 bytes smem, 0 bytes lmem, 480 bytes cmem[0]
```

`31744 bytes smem` = 31KB。OK。

---

## 設計指針: 共有メモリ予算表

```
総計48KB = 49,152バイト

安全目標: 40KB以下（余裕8KB）

計算式:
  sizeof(buffer_a) × array_size_a
+ sizeof(buffer_b) × array_size_b
+ ...
= 合計
```

実際の制限はGPUアーキテクチャによって異なる：

| アーキテクチャ | 最大共有メモリ |
|-------------|-------------|
| sm_80 (A100) | 164KB（動的確保の場合） |
| sm_86 (RTX 3090) | 100KB（動的確保の場合） |
| sm_89 (RTX 4090) | 100KB |
| sm_120 (RTX 5090) | 100KB |

ただし、`__shared__`を使った静的確保の場合は**48KB**が上限。動的共有メモリ（`extern __shared__`）を使うと上限を引き上げられる場合がある。

今回は静的確保にこだわった（コードがシンプルで済むため）。

---

## 学んだこと

### 1. `__shared__`はコンパイル時確保

`if`文で囲んでもメモリは確保される。コンパイル時に確定していなければならない。

### 2. `std::conditional_t`でテンプレートパラメータに応じて型を切り替える

`if constexpr`と組み合わせることで、型とロジックを一致させられる。

### 3. バッファサイズの見直しが先

`std::conditional_t`は強力だが、そもそも「本当にこのサイズが必要か？」を先に確認する。今回は512→128で問題なかった。

---

## コード全体

```cpp
#include <type_traits>

static constexpr int MAX_UNIQUE_GAUSSIANS = 128;

struct TileLocalBuffer {
    float2 means2D[MAX_UNIQUE_GAUSSIANS];
    float4 conic_opacity[MAX_UNIQUE_GAUSSIANS];
    float3 colors[MAX_UNIQUE_GAUSSIANS];
};

struct TileLocalPlaceholder {
    char dummy;
};

template<int BATCH_SIZE>
__global__ void hypersplat_forward_cuda_kernel(
    bool tile_local_enabled,
    /* ... */)
{
    constexpr bool tile_local_available = (BATCH_SIZE <= 256);

    using TileLocalType = std::conditional_t<
        tile_local_available,
        TileLocalBuffer,
        TileLocalPlaceholder
    >;

    __shared__ TileLocalType tile_buf;
    __shared__ float existing_buf[6144];  // 24KB

    const bool use_tile_local = tile_local_enabled && tile_local_available;

    if constexpr (tile_local_available) {
        if (use_tile_local) {
            // タイルローカルキャッシュを使った高速パス
            const int num_gaussians = load_tile_gaussians(tile_buf);
            render_with_tile_local(tile_buf, num_gaussians);
            return;
        }
    }

    // フォールバック: グローバルメモリから直接読み込み
    render_from_global_memory();
}
```

---

## おわりに

`ptxas error: uses too much shared data`は、CUDAカーネルを本気で最適化し始めると必ずぶつかるエラーだ。

解決の流れは：

1. `--ptxas-options=-v`で現在の使用量を確認
2. バッファサイズが適切か見直す（過剰設計が多い）
3. `std::conditional_t`で条件付き確保に切り替える
4. `if constexpr`と実行時ガードを組み合わせる

48KBという制限は厳しいが、設計を工夫すれば乗り越えられる。
