---
title: "Windows PyTorch CUDA環境構築2026：失敗しない完全手順"
emoji: "💻"
type: "tech"
topics: ["PyTorch", "CUDA", "Windows", "環境構築", "NVIDIA"]
published: true
---

# 結論から言う

**PyTorch 2.8.0 + CUDA 12.8 + MSVC 14.44が現時点（2026年1月）の最適解。**

「PyTorch CUDA拡張がビルドできない」「torchがGPUを認識しない」「unsupported Microsoft Visual Studio version」

この記事は、そんなトラブルを2時間以内に解決するためのガイドだ。

---

# 問題の本質

## PyTorch 2.9.0以降の致命的バグ

2024年12月、PyTorch 2.9.0がリリース直後にMSVC互換性問題で使用不能になった。

```
Issue #166123: PyTorch 2.9.0 breaks CUDA extension builds on Windows
Status: Open（2026/01時点）
```

**症状**:
```
error: unsupported Microsoft Visual Studio version! Only 14.41 is supported!
```

**原因**: PyTorch 2.9.0の内部で、MSVC 14.41（VS 2022 17.11）のみを許可するハードコーディング。

**影響**: すべてのCUDA拡張ビルドが失敗。

---

# 環境構築のロードマップ

## Step 1: CUDA Toolkit 12.8インストール

### 1.1 インストーラーのダウンロード

NVIDIA公式サイトから取得:
https://developer.nvidia.com/cuda-12-8-0-download-archive

**選択**:
- OS: Windows
- Architecture: x86_64
- Version: 11
- Installer Type: **exe (network)** （推奨）

### 1.2 インストール

```powershell
# 管理者権限でダウンロードしたexeを実行
cuda_12.8.0_560.35_windows.exe
```

**インストールオプション**:
- カスタムインストール
- ✅ CUDA Toolkit
- ✅ Driver（最新でなければ）
- ❌ Visual Studio Integration（後で手動設定）

### 1.3 環境変数の確認

```powershell
# CUDA_PATHが設定されているか確認
echo $env:CUDA_PATH
# 出力例: C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8

# PATHにnvccが含まれているか確認
nvcc --version
# 出力例: Cuda compilation tools, release 12.8, V12.8.89
```

**設定されていない場合**:

```powershell
# システム環境変数に追加
[System.Environment]::SetEnvironmentVariable(
    "CUDA_PATH",
    "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8",
    [System.EnvironmentVariableTarget]::Machine
)

# PATHに追加
[System.Environment]::SetEnvironmentVariable(
    "Path",
    $env:Path + ";C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8\bin",
    [System.EnvironmentVariableTarget]::Machine
)
```

---

## Step 2: Visual Studio Build Tools 2022インストール

### 2.1 インストーラーのダウンロード

公式サイトから取得:
https://visualstudio.microsoft.com/downloads/

**選択**:
- **Build Tools for Visual Studio 2022**（無料）

### 2.2 インストール

```
インストーラー起動後:
- 「C++によるデスクトップ開発」にチェック
- 個別のコンポーネント:
  ✅ MSVC v143 - VS 2022 C++ x64/x86 build tools (14.44)
  ✅ Windows 11 SDK (10.0.22621.0)
```

**重要**: MSVC 14.44を選択（14.44が現時点の安定版）。

### 2.3 確認

```powershell
# cl.exeのバージョン確認
"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Tools\MSVC\14.44.34433\bin\Hostx64\x64\cl.exe"
# 出力例: Microsoft (R) C/C++ Optimizing Compiler Version 19.44.34433 for x64
```

---

## Step 3: PyTorch 2.8.0インストール

### 3.1 仮想環境の作成

```powershell
# Python 3.11.9（推奨）
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3.2 PyTorch 2.8.0 + CUDA 12.8インストール

```powershell
pip install torch==2.8.0 torchvision==0.20.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128
```

### 3.3 確認

```python
import torch

# CUDAが認識されているか
print(torch.cuda.is_available())  # True

# CUDAバージョン
print(torch.version.cuda)  # 12.8

# GPU名
print(torch.cuda.get_device_name(0))  # NVIDIA GeForce RTX 5090
```

---

## Step 4: 環境変数の設定（CUDA拡張ビルド用）

### 4.1 必須環境変数

```powershell
# CUDA_HOME
[System.Environment]::SetEnvironmentVariable(
    "CUDA_HOME",
    "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8",
    [System.EnvironmentVariableTarget]::User
)

# TORCH_CUDA_ARCH_LIST（GPU世代に応じて設定）
# RTX 5090 (Blackwell): sm_120
[System.Environment]::SetEnvironmentVariable(
    "TORCH_CUDA_ARCH_LIST",
    "8.9+PTX;12.0",
    [System.EnvironmentVariableTarget]::User
)
```

### 4.2 MSVC環境変数

```powershell
# MSVCのパスを追加
$env:Path += ";C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Tools\MSVC\14.44.34433\bin\Hostx64\x64"
```

---

## Step 5: CUDA拡張のビルドテスト

### 5.1 サンプルコード

```python
# test_cuda_ext.py
from torch.utils.cpp_extension import load

cuda_ext = load(
    name="test",
    sources=["test.cu"],
    extra_cuda_cflags=["-O3", "--use_fast_math"],
    verbose=True
)
```

```cuda
// test.cu
#include <torch/extension.h>

__global__ void test_kernel(float* output, int N) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < N) {
        output[i] = i * 2.0f;
    }
}

torch::Tensor test_func(int N) {
    auto output = torch::zeros({N}, torch::TensorOptions().dtype(torch::kFloat32).device(torch::kCUDA));
    test_kernel<<<(N+255)/256, 256>>>(output.data_ptr<float>(), N);
    return output;
}

PYBIND11_MODULE(TORCH_EXTENSION_NAME, m) {
    m.def("test_func", &test_func, "Test CUDA function");
}
```

### 5.2 実行

```powershell
python test_cuda_ext.py
```

**成功時**:
```
Using CUDA 12.8
Detected CUDA files, patching ldflags
Emitting ninja build file...
Building extension module test...
Loading extension module test...
```

---

# トラブルシューティング

## エラー1: "CUDA runtime error: no kernel image is available"

**原因**: `TORCH_CUDA_ARCH_LIST`の設定ミス。

**解決**:

```powershell
# RTX 5090 (sm_120) の場合
$env:TORCH_CUDA_ARCH_LIST = "8.9+PTX;12.0"

# RTX 4090 (sm_89) の場合
$env:TORCH_CUDA_ARCH_LIST = "8.9+PTX"

# RTX 3090 (sm_86) の場合
$env:TORCH_CUDA_ARCH_LIST = "8.6+PTX"
```

---

## エラー2: "unsupported Microsoft Visual Studio version"

**原因**: PyTorch 2.9.0を使っている。

**解決**:

```powershell
# PyTorch 2.8.0にダウングレード
pip uninstall torch torchvision torchaudio
pip install torch==2.8.0 torchvision==0.20.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128
```

---

## エラー3: "nvcc: command not found"

**原因**: CUDA_PATHまたはPATHの設定ミス。

**解決**:

```powershell
# 環境変数を確認
echo $env:CUDA_PATH
echo $env:Path | Select-String "CUDA"

# 設定されていなければ追加（Step 1.3参照）
```

---

## エラー4: "torch.cuda.is_available() returns False"

**原因**: GPUドライバーが古い、またはCUDA Toolkitとの不整合。

**解決**:

```powershell
# ドライバーバージョン確認
nvidia-smi

# CUDA 12.8に対応するドライバー: 560.35以上
# 古い場合はNVIDIA公式からドライバー更新
```

---

# 検証方法

## 完全な動作確認スクリプト

```python
import torch
import sys

def verify_setup():
    print("=== PyTorch CUDA Setup Verification ===\n")

    # Python version
    print(f"Python: {sys.version}")

    # PyTorch version
    print(f"PyTorch: {torch.__version__}")

    # CUDA availability
    cuda_available = torch.cuda.is_available()
    print(f"CUDA Available: {cuda_available}")

    if not cuda_available:
        print("❌ CUDA is not available!")
        return False

    # CUDA version
    print(f"CUDA Version: {torch.version.cuda}")

    # GPU count
    gpu_count = torch.cuda.device_count()
    print(f"GPU Count: {gpu_count}")

    # GPU details
    for i in range(gpu_count):
        print(f"GPU {i}: {torch.cuda.get_device_name(i)}")
        print(f"  Memory: {torch.cuda.get_device_properties(i).total_memory / 1e9:.1f} GB")

    # Simple test
    print("\n=== Simple Tensor Test ===")
    x = torch.rand(1000, 1000, device='cuda')
    y = torch.matmul(x, x)
    print(f"✅ CUDA tensor operation succeeded")

    return True

if __name__ == "__main__":
    verify_setup()
```

**実行**:

```powershell
python verify_setup.py
```

**期待される出力**:

```
=== PyTorch CUDA Setup Verification ===

Python: 3.11.9
PyTorch: 2.8.0+cu128
CUDA Available: True
CUDA Version: 12.8
GPU Count: 1
GPU 0: NVIDIA GeForce RTX 5090
  Memory: 32.0 GB

=== Simple Tensor Test ===
✅ CUDA tensor operation succeeded
```

---

# GPU世代別の設定まとめ

| GPU | sm_XX | TORCH_CUDA_ARCH_LIST |
|-----|-------|---------------------|
| RTX 5090 (Blackwell) | sm_120 | `8.9+PTX;12.0` |
| RTX 4090 (Ada) | sm_89 | `8.9+PTX` |
| RTX 3090 (Ampere) | sm_86 | `8.6+PTX` |
| RTX 3080 (Ampere) | sm_86 | `8.6+PTX` |
| RTX 2080 Ti (Turing) | sm_75 | `7.5+PTX` |

**`+PTX`の意味**: 将来のGPUアーキテクチャでも動作する互換コードを生成。

---

# よくある質問

## Q1: PyTorch 2.10以降はいつ使える？

**A**: Issue #166123が解決されるまで待つ。2026年2月頃に修正版がリリース予定（非公式情報）。

## Q2: CUDA 12.9は使える？

**A**: PyTorch 2.8.0はCUDA 12.8ビルド。CUDA 12.9を使う場合は、PyTorchをソースからビルドする必要がある（非推奨）。

## Q3: Minicondaでも同じ手順？

**A**: はい。`pip install`の代わりに`conda install`を使う以外は同じ。

```bash
conda install pytorch==2.8.0 torchvision==0.20.0 torchaudio==2.8.0 pytorch-cuda=12.8 -c pytorch -c nvidia
```

---

# チェックリスト

| # | 項目 | 確認 |
|---|------|------|
| 1 | CUDA Toolkit 12.8インストール | □ |
| 2 | nvcc --version で確認 | □ |
| 3 | Visual Studio Build Tools 2022 (MSVC 14.44) | □ |
| 4 | PyTorch 2.8.0 + CUDA 12.8インストール | □ |
| 5 | torch.cuda.is_available() == True | □ |
| 6 | CUDA_HOME環境変数設定 | □ |
| 7 | TORCH_CUDA_ARCH_LIST設定（GPU世代に応じて） | □ |
| 8 | CUDA拡張ビルドテスト成功 | □ |

**全てチェックできれば環境構築完了。**

---

# まとめ

Windows + PyTorch + CUDA環境構築の鉄則:

1. **PyTorch 2.8.0を使う**（2.9.0以降は避ける）
2. **CUDA 12.8 + MSVC 14.44の組み合わせ**
3. **環境変数は正確に設定**（CUDA_HOME、TORCH_CUDA_ARCH_LIST）
4. **検証スクリプトで必ず確認**

「動かない」の9割は環境変数の設定ミス。このガイドを順番に実行すれば、2時間以内に環境構築完了。

---

# 関連記事

## PyTorch/CUDA開発シリーズ
- **この記事** → Windows PyTorch CUDA環境構築
- [RTX 5090 CUDA最適化](https://zenn.dev/amabito/articles/rtx5090-cuda-optimization) - Blackwell世代の最適化
- [PyTorch CUDA拡張](https://zenn.dev/amabito/articles/pytorch-cuda-extension) - ビルドの詳細
- [CUDAメモリ管理の罠](https://zenn.dev/amabito/articles/cuda-memory-management) - メモリプール実装

## 3DGSシリーズ
- [HyperRasterizer完全解説](https://zenn.dev/amabito/articles/hyper-rasterizer-zenn) - 4169FPS達成の独自ラスタライザ
- [3DGS商用化ガイド](https://zenn.dev/amabito/articles/3dgs-commercial-guide) - ライセンス問題の整理

---

質問はコメント欄へ。環境構築で困っている方の助けになれば幸いだ。
