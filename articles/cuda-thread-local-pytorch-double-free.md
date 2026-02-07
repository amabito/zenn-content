---
title: "PyTorch autograd × thread_local = double free：CUDA開発者が踏む最悪の罠"
emoji: "💀"
type: "tech"
topics: ["CUDA", "PyTorch", "デバッグ", "GPU"]
published: false
---

## TL;DR

PyTorchのカスタムCUDA拡張で`static thread_local`を使ってポインタキャッシュを実装すると、**forward/backwardが異なるスレッドで実行される**ため、double freeが発生する。解決策は所有権フラグをデータ構造自体に持たせること。

## 症状：2回目のiterationでcudaFreeが失敗する

以下のような謎のエラーに遭遇した：

```python
# 1回目のiteration: 成功
loss.backward()
optimizer.step()

# 2回目のiteration: クラッシュ
loss.backward()  # RuntimeError: cudaFree failed: invalid argument
```

特徴的だったのは：

- **1回目は必ず成功する**
- **2回目以降で失敗する**
- FP16を有効にした時だけ発生する
- デバッガでもメモリリークは検出されない

## 問題のコード：thread_localでポインタ比較

メモリ効率化のため、バッファを再利用するキャッシュ機構を実装していた：

```cpp
// ❌ 悪い例：thread_local cache
struct BufferCache {
    void* rgb_fp16 = nullptr;
    void* soa_buffer = nullptr;
};

static thread_local BufferCache g_buffer_cache;

// Forward pass: バッファ確保
void allocate_buffers(GeometryBuffer* geom, bool use_fp16) {
    if (use_fp16) {
        cudaMalloc(&geom->rgb_fp16, size);
        g_buffer_cache.rgb_fp16 = geom->rgb_fp16;  // キャッシュに保存
    }
}

// Backward pass: バッファ解放
void free_buffers(GeometryBuffer* geom) {
    if (geom->rgb_fp16 != nullptr) {
        // キャッシュと比較して、新規確保したものだけ解放
        if (geom->rgb_fp16 != g_buffer_cache.rgb_fp16) {
            cudaFree(geom->rgb_fp16);  // ← ここでdouble free！
        }
    }
}
```

### 何が起きているのか？

このコード、一見正しく見えるが、**PyTorchのスレッドモデル**を理解していないと致命的なバグになる。

## PyTorch autogradのスレッドモデル

### 重要な事実

```
Forward pass:  Thread A で実行
Backward pass: Thread B で実行（Thread Aとは別）
```

PyTorchのautograd engineは、**forward/backwardを異なるスレッドで実行する可能性がある**。これは並列化とパフォーマンスのためだが、`thread_local`変数にとっては致命的。

### thread_localの仕組み

`thread_local`変数は**スレッドごとに独立したコピー**を持つ：

```cpp
static thread_local int value = 0;

// Thread A
value = 10;  // Thread A の value = 10

// Thread B
printf("%d", value);  // 出力: 0（Thread B の value は初期化されたばかり）
```

## バグの完全な再現

### 1回目のiteration

```cpp
// Forward (Thread A)
allocate_buffers(...);
// → Thread A の g_buffer_cache.rgb_fp16 = 0x7f8a3c000000

// Backward (Thread B)
free_buffers(...);
// → Thread B の g_buffer_cache.rgb_fp16 = nullptr（初期値）
// → 比較: 0x7f8a3c000000 != nullptr → true
// → cudaFree(0x7f8a3c000000)  ✅ 成功
```

### 2回目のiteration

```cpp
// Forward (Thread A)
allocate_buffers(...);
// → 既にThread A の g_buffer_cache.rgb_fp16 = 0x7f8a3c000000（前回の値）
// → 新規確保: geom->rgb_fp16 = 0x7f8a3c000000（再利用）

// Backward (Thread B)
free_buffers(...);
// → Thread B の g_buffer_cache.rgb_fp16 = nullptr（Thread Bでは常に初期値）
// → 比較: 0x7f8a3c000000 != nullptr → true
// → cudaFree(0x7f8a3c000000)  💀 double free！
```

**Thread Bは毎回新鮮なthread_local変数を見るため、常に比較がtrueになり、全てのポインタを解放しようとする。**

## 正しい修正：所有権フラグを構造体に持たせる

```cpp
// ✅ 良い例：所有権フラグ
struct GeometryBuffer {
    void* rgb_fp16 = nullptr;
    void* soa_buffer = nullptr;

    // 所有権フラグ（thread_localではなく、構造体のメンバー）
    bool fp16_from_cache = false;
    bool soa_from_cache = false;
};

static thread_local BufferCache g_buffer_cache;

// Forward pass
void allocate_buffers(GeometryBuffer* geom, bool use_fp16) {
    if (use_fp16) {
        if (g_buffer_cache.rgb_fp16 != nullptr) {
            // キャッシュから再利用
            geom->rgb_fp16 = g_buffer_cache.rgb_fp16;
            geom->fp16_from_cache = true;  // フラグをセット
        } else {
            // 新規確保
            cudaMalloc(&geom->rgb_fp16, size);
            g_buffer_cache.rgb_fp16 = geom->rgb_fp16;
            geom->fp16_from_cache = false;  // フラグをセット
        }
    }
}

// Backward pass
void free_buffers(GeometryBuffer* geom) {
    // フラグで判定（ポインタ比較ではない）
    if (geom->rgb_fp16 != nullptr && !geom->fp16_from_cache) {
        cudaFree(geom->rgb_fp16);
    }
    if (geom->soa_buffer != nullptr && !geom->soa_from_cache) {
        cudaFree(geom->soa_buffer);
    }
}
```

### なぜこれで解決するのか？

- **所有権フラグは`GeometryBuffer`構造体のメンバー**
- Forward/Backward間で**同じ構造体インスタンス**が共有される
- スレッドが変わっても、構造体のフラグは変わらない
- `fp16_from_cache = true` → 解放しない
- `fp16_from_cache = false` → 解放する

## デバッグのヒント

### 1. cuda-memcheckを使う

```bash
cuda-memcheck --tool memcheck python train.py
```

しかし、**thread_local起因のバグはcuda-memcheckでは検出できない**（合法的なポインタへの二重解放）。

### 2. CUDA_LAUNCH_BLOCKING=1

```bash
export CUDA_LAUNCH_BLOCKING=1
python train.py
```

同期実行にすることで、エラー箇所を特定しやすくなる。

### 3. ログで追跡

```cpp
void free_buffers(GeometryBuffer* geom) {
    printf("[Thread %ld] Freeing %p (from_cache=%d)\n",
           pthread_self(), geom->rgb_fp16, geom->fp16_from_cache);

    if (geom->rgb_fp16 != nullptr && !geom->fp16_from_cache) {
        cudaFree(geom->rgb_fp16);
    }
}
```

出力：
```
[Thread 140234] Freeing 0x7f8a3c000000 (from_cache=0)  ✅
[Thread 140235] Freeing 0x7f8a3c000000 (from_cache=0)  💀 同じポインタを別スレッドで解放
```

## 他の言語でも同じ問題は起きる？

### Rustの場合

Rustの`thread_local!`も同じ挙動：

```rust
thread_local! {
    static CACHE: RefCell<Option<*mut u8>> = RefCell::new(None);
}

// Forward (thread A)
CACHE.with(|c| *c.borrow_mut() = Some(ptr));

// Backward (thread B)
CACHE.with(|c| {
    // thread B の CACHE は None（初期値）
});
```

Rustでも**所有権フラグをデータ構造に持たせる**のが正解。

### C++20 jthreadの場合

`std::jthread`を使っても同じ：

```cpp
std::jthread forward_thread([&]() {
    g_buffer_cache.rgb_fp16 = ptr;  // thread A
});

std::jthread backward_thread([&]() {
    // thread B の g_buffer_cache は初期値
});
```

## 教訓：PyTorchカスタムオペレータのベストプラクティス

### ❌ 避けるべきパターン

```cpp
// 1. thread_localでポインタ比較
static thread_local void* g_last_ptr;
if (ptr != g_last_ptr) { /* ... */ }

// 2. thread_localでカウンタ管理
static thread_local int g_call_count = 0;
if (++g_call_count > 1) { /* ... */ }

// 3. thread_localで状態フラグ
static thread_local bool g_initialized = false;
if (!g_initialized) { /* ... */ }
```

### ✅ 推奨パターン

```cpp
// 1. 所有権フラグを構造体に持たせる
struct Buffer {
    void* ptr;
    bool owned_by_us;  // ← これ
};

// 2. グローバルmutexで保護（パフォーマンスに注意）
static std::mutex g_cache_mutex;
static std::unordered_map<void*, bool> g_ownership;

// 3. PyTorch autogradのフックを使う
// （PyTorchが適切なタイミングで解放を保証）
```

## まとめ

1. **PyTorchのforward/backwardは異なるスレッドで実行される**
2. **`thread_local`変数はスレッドごとに独立したコピーを持つ**
3. **ポインタ比較による所有権判定は`thread_local`では機能しない**
4. **所有権フラグはデータ構造自体に持たせる**
5. **CUDA拡張のデバッグはcuda-memcheck + ログ追跡が有効**

このバグは**症状が遅延的で、再現条件が複雑**なため、発見が非常に困難。CUDA拡張を書く全ての開発者が知っておくべき罠である。

## 参考資料

- [PyTorch Custom C++ and CUDA Extensions](https://pytorch.org/tutorials/advanced/cpp_extension.html)
- [CUDA C++ Programming Guide - Thread Local Storage](https://docs.nvidia.com/cuda/cuda-c-programming-guide/index.html)
- [cppreference - thread_local storage duration](https://en.cppreference.com/w/cpp/language/storage_duration)

---

この記事は実際に発生したバグ（2026-02-06、HyperRasterizer開発中）の分析に基づいています。4時間のデバッグの末、thread_localの罠に気づきました。同じ苦しみを味わう開発者が減ることを願っています。
