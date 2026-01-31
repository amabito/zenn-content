---
title: "【有料】PyTorch CUDA拡張完全ガイド：互換性地獄を乗り越える"
emoji: "🔥"
type: "tech"
topics: ["PyTorch", "CUDA", "Python", "CPP", "Windows"]
published: true
published_at: "2026-01-18 12:00"
price: 500
---

# この記事で得られるもの

- PyTorch **バージョン互換性問題**の完全解決
- **CUBライブラリ**の正しい使い方
- **Backward Pass**の実装方法
- Windows/Linux **両対応**のsetup.py

**対象読者:** PyTorchでカスタムCUDAオペレーションを実装したい人

---

# 無料記事のおさらい

- setup.py + cpp + cuでCUDA拡張を作る
- Windowsではビルドエラーが多い
- C2872エラーはPyTorch 2.8.0で回避

今回は**本格的な実装**を解説する。

---

:::message
ここから有料パートです。
:::

# PyTorchバージョン互換性

## バージョン対応表

| PyTorch | CUDA Toolkit | sm_120 (RTX 5090) | ビルド |
|---------|-------------|-------------------|--------|
| 2.5.1+cu124 | 12.4 | ❌ | ✅ |
| 2.8.0+cu128 | 12.8 | ✅ | ✅ |
| 2.9.0+cu128 | 12.8 | ✅ | ❌ C2872 |
| 2.10.0+cu128 | 12.8 | ✅ | ❌ C2872 |

**結論**: PyTorch 2.8.0 + CUDA 12.8 が最も安定。

## インストールコマンド

```bash
pip install torch==2.8.0+cu128 torchvision==0.23.0+cu128 \
    --index-url https://download.pytorch.org/whl/cu128
```

---

# CUBライブラリの使い方

CUBはNVIDIAの並列アルゴリズムライブラリ。ソート、リダクション等が高速。

## インクルード順序が重要

```cpp
// OK: CUBを先にインクルード
#include <cub/cub.cuh>
#include <torch/extension.h>

// NG: torchを先にインクルードするとエラー
#include <torch/extension.h>
#include <cub/cub.cuh>  // 名前空間衝突！
```

## Radix Sort実装

```cuda
#include <cub/cub.cuh>
#include <torch/extension.h>

void sort_by_keys(
    torch::Tensor keys,    // 入力: ソートキー
    torch::Tensor values,  // 入力: 値
    torch::Tensor sorted_keys,    // 出力
    torch::Tensor sorted_values   // 出力
) {
    int N = keys.size(0);

    // 一時バッファサイズを計算
    size_t temp_storage_bytes = 0;
    cub::DeviceRadixSort::SortPairs(
        nullptr, temp_storage_bytes,
        keys.data_ptr<uint64_t>(),
        sorted_keys.data_ptr<uint64_t>(),
        values.data_ptr<int>(),
        sorted_values.data_ptr<int>(),
        N
    );

    // 一時バッファを確保
    auto temp_storage = torch::empty(
        {(int64_t)temp_storage_bytes},
        torch::dtype(torch::kUInt8).device(keys.device())
    );

    // ソート実行
    cub::DeviceRadixSort::SortPairs(
        temp_storage.data_ptr<void>(), temp_storage_bytes,
        keys.data_ptr<uint64_t>(),
        sorted_keys.data_ptr<uint64_t>(),
        values.data_ptr<int>(),
        sorted_values.data_ptr<int>(),
        N
    );
}
```

---

# Backward Passの実装

## autograd.Function

```python
import torch

class MyCustomOp(torch.autograd.Function):
    @staticmethod
    def forward(ctx, input):
        output = my_extension.forward(input)
        ctx.save_for_backward(input)
        return output

    @staticmethod
    def backward(ctx, grad_output):
        input, = ctx.saved_tensors
        grad_input = my_extension.backward(grad_output, input)
        return grad_input

# 使い方
def my_op(input):
    return MyCustomOp.apply(input)
```

## CUDAカーネル（Forward）

```cuda
__global__ void forward_kernel(
    const float* input,
    float* output,
    int N
) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx < N) {
        // 例: ソフトプラス関数
        float x = input[idx];
        output[idx] = logf(1.0f + expf(x));
    }
}

torch::Tensor forward_cuda(torch::Tensor input) {
    auto output = torch::zeros_like(input);
    int N = input.numel();

    int threads = 256;
    int blocks = (N + threads - 1) / threads;

    forward_kernel<<<blocks, threads>>>(
        input.data_ptr<float>(),
        output.data_ptr<float>(),
        N
    );

    return output;
}
```

## CUDAカーネル（Backward）

```cuda
__global__ void backward_kernel(
    const float* grad_output,
    const float* input,
    float* grad_input,
    int N
) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx < N) {
        // ソフトプラスの導関数: sigmoid(x)
        float x = input[idx];
        float sigmoid = 1.0f / (1.0f + expf(-x));
        grad_input[idx] = grad_output[idx] * sigmoid;
    }
}

torch::Tensor backward_cuda(
    torch::Tensor grad_output,
    torch::Tensor input
) {
    auto grad_input = torch::zeros_like(input);
    int N = input.numel();

    int threads = 256;
    int blocks = (N + threads - 1) / threads;

    backward_kernel<<<blocks, threads>>>(
        grad_output.data_ptr<float>(),
        input.data_ptr<float>(),
        grad_input.data_ptr<float>(),
        N
    );

    return grad_input;
}
```

---

# Windows/Linux両対応setup.py

```python
import os
import sys
from setuptools import setup
from torch.utils.cpp_extension import BuildExtension, CUDAExtension

def get_cuda_arch_flags():
    """GPU世代に応じたアーキテクチャフラグ"""
    import torch
    if torch.cuda.is_available():
        capability = torch.cuda.get_device_capability()
        arch = f"{capability[0]}{capability[1]}"
        return [f'-gencode=arch=compute_{arch},code=sm_{arch}']
    return []

def get_extra_compile_args():
    """OS別のコンパイルフラグ"""
    if sys.platform == 'win32':
        return {
            'cxx': ['/O2', '/std:c++17'],
            'nvcc': [
                '-O3',
                '--use_fast_math',
                '-std=c++17',
                '-Xcompiler', '/O2',
            ] + get_cuda_arch_flags()
        }
    else:  # Linux
        return {
            'cxx': ['-O3', '-std=c++17'],
            'nvcc': [
                '-O3',
                '--use_fast_math',
                '-std=c++17',
                '-Xcompiler', '-fPIC',
            ] + get_cuda_arch_flags()
        }

setup(
    name='my_extension',
    ext_modules=[
        CUDAExtension(
            name='my_extension',
            sources=[
                'my_ext.cpp',
                'cuda/forward.cu',
                'cuda/backward.cu',
            ],
            extra_compile_args=get_extra_compile_args(),
        ),
    ],
    cmdclass={
        'build_ext': BuildExtension.with_options(use_ninja=True)
    }
)
```

---

# 勾配検証

実装したBackwardが正しいか検証する。

```python
import torch
from torch.autograd import gradcheck

def test_gradcheck():
    input = torch.randn(10, requires_grad=True, dtype=torch.float64).cuda()

    # gradcheckはfloat64が必要
    result = gradcheck(
        my_op,
        (input,),
        eps=1e-6,
        atol=1e-4,
        rtol=1e-3
    )
    assert result, "Gradient check failed!"
    print("Gradient check passed!")

if __name__ == '__main__':
    test_gradcheck()
```

---

# トラブルシューティング

## undefined symbol: _ZN3c104cuda...

PyTorchとCUDAのABI不一致。

```bash
# クリーンビルド
rm -rf build/ *.so *.egg-info
pip install . --no-build-isolation
```

## CUDA error: no kernel image is available

GPUアーキテクチャが指定されていない。

```python
# setup.pyでアーキテクチャを明示
extra_compile_args['nvcc'].append('-gencode=arch=compute_86,code=sm_86')
```

## ImportError: DLL load failed

WindowsでDLLが見つからない。

```bash
# CUDA PATHを確認
echo %CUDA_PATH%
# 環境変数に追加
set PATH=%CUDA_PATH%\bin;%PATH%
```

---

# まとめ

| 問題 | 解決策 |
|------|--------|
| C2872エラー | PyTorch 2.8.0を使用 |
| CUBインクルード | CUBを先にインクルード |
| Backward | autograd.Function + CUDAカーネル |
| クロスプラットフォーム | OS判定してフラグを変える |
| 勾配検証 | torch.autograd.gradcheck |

**CUDA拡張は罠だらけ。この記事を参考に乗り越えてほしい。**
