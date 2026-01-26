---
title: "PyTorch CUDA拡張がビルドできない？Windowsで動かす完全ガイド"
emoji: "🔧"
type: "tech"
topics: ["pytorch", "cuda", "python", "cpp", "windows"]
published: true
---

# 結論から言う

**PyTorch CUDA拡張のWindowsビルドは罠だらけ。でも、正しい手順を踏めば必ず動く。**

「C2872エラーで詰んだ」「undefined symbolで動かない」「DLLが見つからない」

WindowsでCUDA拡張をビルドしようとして、こんなエラーに遭遇しませんでしたか？

**この記事で得られること:**
- Windows特有のビルドエラーと解決策
- PyTorchバージョン別の互換性表
- コピペで動くsetup.py

---

# CUDA拡張とは

## なぜ必要か

```python
# PyTorch標準（遅い）
for i in range(N):
    result[i] = torch.exp(input[i])

# CUDA拡張（速い）
result = my_custom_exp(input)  # 自作CUDAカーネル
```

特殊な処理や、パフォーマンスが重要な場合にCUDA拡張が必要。

## 構成要素

```
my_extension/
├── setup.py          # ビルドスクリプト
├── my_ext.cpp        # C++/PyBind11バインディング
└── cuda/
    └── kernel.cu     # CUDAカーネル
```

---

# 最小構成

## setup.py

```python
from setuptools import setup
from torch.utils.cpp_extension import BuildExtension, CUDAExtension

setup(
    name='my_extension',
    ext_modules=[
        CUDAExtension(
            name='my_extension',
            sources=[
                'my_ext.cpp',
                'cuda/kernel.cu',
            ],
        ),
    ],
    cmdclass={
        'build_ext': BuildExtension
    }
)
```

## my_ext.cpp

```cpp
#include <torch/extension.h>

// CUDAカーネルの宣言
torch::Tensor my_cuda_function(torch::Tensor input);

// PyBind11バインディング
PYBIND11_MODULE(TORCH_EXTENSION_NAME, m) {
    m.def("my_function", &my_cuda_function, "My CUDA function");
}
```

## cuda/kernel.cu

```cuda
#include <torch/extension.h>
#include <cuda_runtime.h>

__global__ void my_kernel(float* input, float* output, int N) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx < N) {
        output[idx] = expf(input[idx]);
    }
}

torch::Tensor my_cuda_function(torch::Tensor input) {
    auto output = torch::zeros_like(input);

    int N = input.numel();
    int threads = 256;
    int blocks = (N + threads - 1) / threads;

    my_kernel<<<blocks, threads>>>(
        input.data_ptr<float>(),
        output.data_ptr<float>(),
        N
    );

    return output;
}
```

## ビルド

```bash
pip install .
```

---

# Windowsでの罠

## 罠1: Visual Studioのバージョン

PyTorchとCUDAはVisual Studioのバージョンに厳しい。

| PyTorch | CUDA | 推奨VS |
|---------|------|--------|
| 2.8 | 12.8 | VS 2022 (14.44) |
| 2.5 | 12.4 | VS 2022 (14.40) |
| 2.0 | 11.8 | VS 2019 |

**バージョンが合わないとビルドが通らない。**

## 罠2: C2872エラー

```
error C2872: 'detail': ambiguous symbol
```

PyTorch 2.9以降で発生する。`compiled_autograd.h`の名前空間衝突。

**解決策**: PyTorch 2.8.0を使う。

```bash
pip install torch==2.8.0+cu128 --index-url https://download.pytorch.org/whl/cu128
```

## 罠3: Ninja not found

```
RuntimeError: Ninja is required to load C++ extensions
```

```bash
pip install ninja
```

---

# デバッグのコツ

## verbose出力

```bash
pip install . --verbose
```

エラーの詳細が見える。

## JITコンパイル

開発中はJITコンパイルが便利。

```python
from torch.utils.cpp_extension import load

my_ext = load(
    name='my_extension',
    sources=['my_ext.cpp', 'cuda/kernel.cu'],
    verbose=True
)

result = my_ext.my_function(input)
```

毎回ビルドされるので遅いが、setup.pyを書かなくていい。

---

# 関連記事

## CUDA開発シリーズ
- [RTX 5090 CUDA最適化](https://zenn.dev/amabito/articles/rtx5090-cuda-optimization) - Blackwell世代の最適化
- [CUDAメモリ管理の罠](https://zenn.dev/amabito/articles/cuda-memory-management) - メモリプール実装
- **この記事** → PyTorch CUDA拡張の罠

## 3DGSシリーズ
- [HyperRasterizer完全解説](https://zenn.dev/amabito/articles/hyper-rasterizer-zenn) - 4169FPS達成の独自ラスタライザ
- [3DGS商用化ガイド](https://zenn.dev/amabito/articles/3dgs-commercial-guide) - ライセンス問題の整理
- [建設現場×3DGS](https://zenn.dev/amabito/articles/construction-3dgs) - 実用事例

---

詳細な実装とPyTorchバージョン互換性の解決方法は有料記事で解説しています。

https://zenn.dev/amabito/articles/pytorch-cuda-extension-paid
