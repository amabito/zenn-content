---
title: "thread_local + PyTorch autograd = double free: 非再現バグの完全デバッグ記録"
emoji: "🔍"
type: "tech"
topics: ["CUDA", "PyTorch", "デバッグ", "GPU", "C++"]
published: false
published_at: "2026-02-27 18:00"
---

## これは「intermittentバグ」の話だ

バグには2種類ある。「常に再現するバグ」と「たまにしか起きないバグ」。

後者は最悪だ。何度実行しても出ないのに、タイミングによって突然クラッシュする。CUDAカーネル開発でこれに遭遇した。

**症状：**

```python
# 通常は動く
for i in range(1000):
    loss = compute_loss(render, gt)
    loss.backward()  # ← 時々ここでクラッシュ

# エラーメッセージ（非一貫的）
RuntimeError: CUDA error: an illegal memory access was encountered
# または
double free or corruption (out)
# または
cudaFree failed: invalid argument
```

同じコードで同じデータを使っているのに、失敗したりしなかったりする。

---

## 犯人：static thread_local とキャッシュ

問題のコードはこれだ：

```cpp
// CustomKernel.cu

struct BufferCache {
    void* ptr = nullptr;
    size_t size = 0;
    bool owned = false;  // これが問題を引き起こした
};

// スレッドローカルなキャッシュ
static thread_local BufferCache g_cache;

void* get_or_allocate(size_t required_size) {
    if (g_cache.ptr != nullptr && g_cache.size >= required_size) {
        return g_cache.ptr;  // キャッシュヒット
    }

    // 古いバッファを解放
    if (g_cache.ptr != nullptr && g_cache.owned) {
        cudaFree(g_cache.ptr);  // ← double freeの現場
    }

    cudaMalloc(&g_cache.ptr, required_size);
    g_cache.size = required_size;
    g_cache.owned = true;
    return g_cache.ptr;
}
```

一見何も問題ないように見える。`thread_local`だから各スレッドが独自のキャッシュを持つはずだ。

---

## PyTorch autogradの内部構造

問題は「PyTorch autogradのforward/backwardが**必ずしも同一スレッドで実行されない**」という事実だ。

```
Thread A: forward() 呼び出し
  → g_cache.ptr = 0x7f123456 (allocate)
  → g_cache.owned = true
  → forwardカーネル実行

Thread B: backward() 呼び出し（別スレッド！）
  → g_cache.ptr = nullptr (Thread Bはキャッシュを持っていない)
  → 新規allocate → g_cache.ptr = 0x7f789abc
  → backwardカーネル実行完了
  → cudaFree(0x7f789abc) → OK

Thread A: 次のforwardが来た
  → g_cache.ptr = 0x7f123456 (まだThread Aのキャッシュ)
  → get_or_allocate呼び出し
  → 条件: ptr != null && owned == true
  → cudaFree(0x7f123456) ← この時点でThread Bがすでに解放済みかも...
```

問題は「Thread Bが**別の目的で**Thread AのキャッシュアドレスにアクセスするCUDA操作をした後」に起きる。CUDAのメモリ管理はアドレス空間を再利用するため、`0x7f123456`が別の目的で再利用されていると二重解放になる。

### PyTorchのスレッドモデル

```
MainThread:
  loss = forward(input)     # Thread A実行
  loss.backward()           # ThreadPool内のThread B/C/Dに分散

ThreadPool (4 workers):
  Thread B: conv layer backward
  Thread C: custom cuda backward  ← ここが問題
  Thread D: other backward
```

`backward()`はメインスレッドではなく、内部の**スレッドプール**で実行される。しかもどのスレッドで実行されるかは実行タイミングによって変わる。

---

## なぜ「たまにしか」起きないのか

```
パターン1（成功）:
  Thread A: forward → allocate(0x100) → owned=true
  Thread A: next forward → free(0x100) → allocate(0x200)
  # forwardが同一スレッドで連続実行 → OK

パターン2（失敗）:
  Thread A: forward → allocate(0x100) → owned=true
  Thread C: backward → (Thread Cのキャッシュはnull) → allocate(0x300) → use → free(0x300)
  # CUDAが0x300を解放後、0x100に近いアドレスを次の割り当てで返す可能性
  Thread A: next forward → g_cache.ptr = 0x100 → もう一度操作 → BOOM
```

スレッドスケジューリングのタイミング依存。デバッグビルドより**リリースビルドで発生しやすい**（最適化でスレッド切り替えタイミングが変わる）。

---

## 診断方法

### 1. cuda-memcheck（最重要ツール）

```bash
# CUDA APIエラーを詳細に追跡
compute-sanitizer --tool memcheck python train.py

# もしくは古いcuda-memcheck
cuda-memcheck python train.py
```

出力例：
```
========= CUDA-MEMCHECK
========= Invalid __global__ read of size 4
=========     at 0x0000000000c0 in backward_kernel
========= Address 0x7f123456 is out of bounds
```

### 2. AddressSanitizer（C++側）

```cmake
# CMakeLists.txt
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fsanitize=address")
```

ただしCUDAコードと組み合わせると誤検出が多い。

### 3. スレッドIDのロギング

```cpp
#include <thread>

void* get_or_allocate(size_t required_size) {
    auto tid = std::this_thread::get_id();
    printf("[DEBUG] Thread %lu: accessing cache ptr=%p\n",
           std::hash<std::thread::id>{}(tid), g_cache.ptr);
    // ...
}
```

これで「forwardとbackwardのthread_idが異なる」ことが確認できる。

---

## 修正：所有権をデータ構造に持たせる

```cpp
// After: 所有権管理をデータ構造に組み込む

class ManagedBuffer {
public:
    void* ptr = nullptr;
    size_t allocated_size = 0;
    std::mutex mutex;  // スレッドセーフ

    void* get(size_t required_size) {
        std::lock_guard<std::mutex> lock(mutex);

        if (ptr != nullptr && allocated_size >= required_size) {
            return ptr;
        }

        if (ptr != nullptr) {
            cudaFree(ptr);
            ptr = nullptr;
        }

        cudaMalloc(&ptr, required_size);
        allocated_size = required_size;
        return ptr;
    }

    ~ManagedBuffer() {
        if (ptr != nullptr) {
            cudaFree(ptr);
        }
    }
};

// グローバルシングルトン（スレッドローカルではない）
static ManagedBuffer g_buffer;
```

ただしこれはmutexによる競合が発生する。より良い解決策：

```cpp
// Best: forward passの入力テンソルにメタデータを添付する

struct ForwardContext {
    void* workspace_ptr;
    size_t workspace_size;
    // owned lifetime = forward → backward (autogradが管理)
};

// Autograd functionとして実装
class CustomKernelFunction : public torch::autograd::Function<CustomKernelFunction> {
    static torch::Tensor forward(
        torch::autograd::AutogradContext* ctx,
        torch::Tensor input
    ) {
        // workspaceをtensorとして確保（autogradが寿命管理）
        auto workspace = torch::zeros({WORKSPACE_SIZE}, input.options());

        // ctxに保存 → backwardで使える
        ctx->save_for_backward({workspace});

        return run_forward_kernel(input, workspace.data_ptr());
    }

    static std::vector<torch::Tensor> backward(
        torch::autograd::AutogradContext* ctx,
        std::vector<torch::Tensor> grad_outputs
    ) {
        auto saved = ctx->get_saved_variables();
        auto workspace = saved[0];  // forward時のworkspaceを再利用

        return {run_backward_kernel(grad_outputs[0], workspace.data_ptr())};
    }
};
```

**Autograd FunctionにworkspaceをTensorとして渡すことで、PyTorchが寿命管理を行う。**

thread_localのような手動メモリ管理は一切不要になる。

---

## 教訓

1. **`static thread_local`はPyTorchのマルチスレッド環境では危険**
   - forward/backwardは同一スレッドで実行されるとは限らない
   - スレッドプールのサイズや実行順は実行時に変わる

2. **intermittentなCUDAクラッシュ = スレッド間の状態共有が怪しい**
   - 同一スレッドで実行することを前提としたコードを疑う
   - タイミング依存のバグはcuda-memcheckで検出できる

3. **PyTorch Autograd Functionを使えば所有権問題を避けられる**
   - `ctx->save_for_backward()`でTensorの寿命をautogradに委ねる
   - 手動のcudaMalloc/cudaFreeはなるべく避ける

4. **デバッグの順序**
   - まずcuda-memcheck（最も直接的な情報）
   - 次にthread IDロギング（スレッド間の問題を可視化）
   - 最後にAddressSanitizer（C++側のメモリエラー）

---

## まとめ

```
症状: 2回目のiterationでたまにcudaFreeがクラッシュ
原因: static thread_local + PyTorch autogradのマルチスレッド実行
なぜintermittent: スレッドスケジューリングのタイミング依存
診断: cuda-memcheck + thread IDロギング
修正: Autograd FunctionでworkspaceをTensorとして管理
```

「たまにしか起きない」バグは「常に起きる」バグより怖い。条件がわかった瞬間の快感も格別だが。

---

## 関連記事

- [3DGS Backwardの勾配公式を間違えてPSNRが17→24dBになった話](/articles/3dgs-backward-gradient-formula-wrong)
- [CUDAデバッグatomicを本番カーネルに残したら18倍スローダウンした話](/articles/cuda-debug-atomic-performance-trap)
