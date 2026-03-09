---
title: "PyTorch 2.8 + CUDA 12.8 互換性問題まとめ【2026年版トラブルシューティング】"
emoji: "🔧"
type: "tech"
topics: ["PyTorch", "CUDA", "環境構築", "トラブルシューティング"]
published: false
---

## TL;DR

PyTorch 2.8 + CUDA 12.8環境では複数の互換性問題がある。cusparse再定義、MSVC衝突、PEP 668、ninja失敗、sm_120対応など。この記事は2026年2月時点の実戦から得た回避策を網羅する。

## 前提環境

```yaml
OS: Windows 11 (ビルド 22H2)
GPU: NVIDIA GeForce RTX 5090 (Compute Capability 12.0)
CUDA: 12.8
Driver: 591.74
Python: 3.11.9
PyTorch: 2.8.0+cu128
MSVC: 14.44 (Visual Studio Build Tools 2022)
```

## 問題1：cusparseGetErrorString 再定義エラー

### エラーメッセージ

```bash
error: identifier "cusparseGetErrorString" is undefined
error: redefinition of "cusparseGetErrorString"
```

### 原因

PyTorch 2.8のヘッダー（`torch/csrc/api/include/torch/types.h`）とCUDA 12.8の`cusparse.h`が両方とも`cusparseGetErrorString`を定義しており、インクルード順序によって衝突する。

### 詳細

```cpp
// PyTorch 2.8: torch/csrc/api/include/torch/types.h（簡略版）
inline const char* cusparseGetErrorString(cusparseStatus_t status) {
    // PyTorchの実装
}

// CUDA 12.8: cusparse.h
const char* cusparseGetErrorString(cusparseStatus_t status);
// ← CUDAネイティブ実装
```

### 解決策1：インクルード順序を調整

```cpp
// ✅ CUDA headers → PyTorch headers
#include <cuda_runtime.h>
#include <cusparse.h>        // CUDA先
#include <torch/extension.h>  // PyTorch後

// ❌ PyTorch headers → CUDA headers
#include <torch/extension.h>  // PyTorch先
#include <cusparse.h>         // CUDA後 → エラー
```

### 解決策2：WSL2でビルド

Windows上のMSVC + CUDA 12.8の組み合わせは不安定。WSL2経由でGCCビルドが推奨：

```bash
# Windows PowerShell
wsl -d Ubuntu-24.04 -- bash -c "
  cd /mnt/d/work/Projects/your-project/src/your_package && \
  rm -rf build && \
  python3 setup.py build_ext --inplace
"
```

**メリット：**
- MSVC特有の問題を回避
- GCC/ClangはPyTorchとの相性が良い
- ninjaビルドも安定

### 解決策3：PyTorchダウングレード

```bash
pip install torch==2.5.0+cu121 --index-url https://download.pytorch.org/whl/cu121
```

PyTorch 2.5以前はcusparse再定義問題が少ない。

## 問題2：MSVC 14.44 + CUDA 12.8 衝突

### エラーメッセージ

```bash
LINK : fatal error LNK1104: cannot open file 'python311.lib'
error: command 'C:\\Program Files (x86)\\...\\cl.exe' failed
```

### 原因

通常のコマンドプロンプトでは、MSVCの環境変数が設定されていない。

### 解決策：VS Developer Command Promptを使用

```cmd
:: Step 1: VS Developer Command Promptを起動
"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat"

:: Step 2: 環境変数を設定
set DISTUTILS_USE_SDK=1

:: Step 3: ビルド
cd /d "D:\work\Projects\your-project\src\your_package"
pip install -e . --no-build-isolation
```

**`DISTUTILS_USE_SDK=1`の役割：**
- distutilsに「既にVS環境が設定済み」と伝える
- distutilsが独自にコンパイラを探さない

### 自動化スクリプト

```python
# force_rebuild.py
import subprocess
import os

def rebuild():
    vscmd = r"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat"
    package_dir = r"D:\work\Projects\your-project\src\your_package"

    cmd = f'''
    call "{vscmd}" && ^
    set DISTUTILS_USE_SDK=1 && ^
    cd /d "{package_dir}" && ^
    pip install -e . --no-build-isolation
    '''

    subprocess.run(cmd, shell=True, check=True)

if __name__ == "__main__":
    rebuild()
```

実行：

```bash
python force_rebuild.py
```

## 問題3：PEP 668 externally-managed-environment

### エラーメッセージ

```bash
error: externally-managed-environment

× This environment is externally managed
╰─> To install Python packages system-wide, try apt install
    python3-xyz, where xyz is the package you are trying to
    install.
```

### 原因

PEP 668（2023年導入）により、システムPythonへの直接インストールが禁止された。Ubuntu 24.04などで発生。

### 解決策1：setup.py直接実行（推奨）

```bash
python3 setup.py build_ext --inplace
```

**メリット：**
- pip経由でないため、PEP 668の制約を受けない
- ビルド成果物を直接生成
- 開発時の反復ビルドに最適

### 解決策2：--break-system-packages（非推奨）

```bash
pip install -e . --break-system-packages
```

**デメリット：**
- システム環境を汚染する可能性
- パッケージマネージャとの衝突リスク

### 解決策3：venv/condaを使用

```bash
# venv
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# conda
conda create -n your-env python=3.11
conda activate your-env
pip install -e .
```

## 問題4：ninja ビルド失敗（Windows）

### エラーメッセージ

```bash
ninja: error: loading 'build.ninja': The system cannot find the file specified.
```

または：

```bash
RuntimeError: Ninja is required to load C++ extensions
```

### 原因

Windowsでninjaビルドシステムが不安定、またはパス問題。

### 解決策1：ninjaを無効化

```bash
set MAX_JOBS=1
pip install -e . --no-build-isolation
```

**`MAX_JOBS=1`の効果：**
- 並列ビルドを無効化
- ninjaの代わりにMSBuildを使用

### 解決策2：ninjaを手動インストール

```bash
pip install ninja
```

パスが通っているか確認：

```bash
where ninja
# 出力: C:\Python311\Scripts\ninja.exe
```

### 解決策3：WSL2を使用

WSL2ではninjaが安定動作：

```bash
wsl -d Ubuntu-24.04 -- bash -c "
  sudo apt update && sudo apt install -y ninja-build
  cd /mnt/d/... && python3 setup.py build_ext --inplace
"
```

## 問題5：sm_120 (Blackwell) 対応

### エラーメッセージ

```bash
nvcc fatal : Unsupported gpu architecture 'compute_120'
```

または：

```bash
RuntimeError: CUDA error: no kernel image is available for execution
```

### 原因

RTX 5090（Blackwell世代、Compute Capability 12.0）はCUDA 12.8以降が必要だが、PyTorchがsm_120でビルドされていない。

### 解決策1：PyTorchソースビルド

```bash
# CUDA 12.8 + sm_120対応PyTorchをビルド
git clone --recursive https://github.com/pytorch/pytorch
cd pytorch

export TORCH_CUDA_ARCH_LIST="8.0;8.6;8.9;9.0;12.0"
export CUDA_HOME=/usr/local/cuda-12.8

python setup.py install
```

**注意：**
- ビルド時間: 1-2時間
- メモリ: 16GB以上推奨
- ディスク: 30GB以上必要

### 解決策2：setup.pyでアーキテクチャ指定

```python
# setup.py
from setuptools import setup
from torch.utils.cpp_extension import BuildExtension, CUDAExtension

setup(
    name='your_package',
    ext_modules=[
        CUDAExtension(
            'your_package._C',
            ['csrc/bindings.cpp', 'csrc/kernel.cu'],
            extra_compile_args={
                'nvcc': [
                    '-gencode=arch=compute_120,code=sm_120',  # Blackwell
                    '-gencode=arch=compute_90,code=sm_90',    # Hopper
                    '-gencode=arch=compute_89,code=sm_89',    # Ada
                ]
            }
        )
    ],
    cmdclass={'build_ext': BuildExtension}
)
```

### 解決策3：実行時アーキテクチャ確認

```python
import torch
print(f"CUDA available: {torch.cuda.is_available()}")
print(f"CUDA version: {torch.version.cuda}")
print(f"GPU: {torch.cuda.get_device_name(0)}")
print(f"Capability: {torch.cuda.get_device_capability(0)}")
```

出力例：

```
CUDA available: True
CUDA version: 12.8
GPU: NVIDIA GeForce RTX 5090
Capability: (12, 0)  ← Compute Capability 12.0
```

## 統合ビルドスクリプト（推奨）

すべての問題を考慮した自動ビルドスクリプト：

```python
# auto_build.py
import subprocess
import sys
import os
import platform

def check_environment():
    """環境チェック"""
    print("[1/5] Checking environment...")

    # CUDA確認
    try:
        result = subprocess.run(['nvcc', '--version'], capture_output=True, text=True)
        print(f"✅ CUDA: {result.stdout.split('release')[-1].split(',')[0].strip()}")
    except FileNotFoundError:
        print("❌ CUDA not found. Please install CUDA 12.8+")
        sys.exit(1)

    # PyTorch確認
    try:
        import torch
        print(f"✅ PyTorch: {torch.__version__}")
        print(f"✅ GPU: {torch.cuda.get_device_name(0)}")
        print(f"✅ Compute Capability: {torch.cuda.get_device_capability(0)}")
    except ImportError:
        print("❌ PyTorch not found. Please install PyTorch 2.8+")
        sys.exit(1)

def build_wsl2():
    """WSL2ビルド"""
    print("[2/5] Building via WSL2...")

    project_dir = "D:/work/Projects/your-project/src/your_package"
    wsl_path = project_dir.replace("D:/", "/mnt/d/").replace("\\", "/")

    cmd = f'''wsl -d Ubuntu-24.04 -- bash -c "
        cd {wsl_path} &&
        rm -rf build &&
        python3 setup.py build_ext --inplace
    "'''

    subprocess.run(cmd, shell=True, check=True)
    print("✅ WSL2 build completed")

def build_windows():
    """Windowsビルド"""
    print("[2/5] Building on Windows...")

    vscmd = r"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat"
    package_dir = r"D:\work\Projects\your-project\src\your_package"

    if not os.path.exists(vscmd):
        print("❌ VS Build Tools not found. Trying WSL2...")
        return build_wsl2()

    cmd = f'''
    call "{vscmd}" && ^
    set DISTUTILS_USE_SDK=1 && ^
    cd /d "{package_dir}" && ^
    python setup.py build_ext --inplace
    '''

    try:
        subprocess.run(cmd, shell=True, check=True)
        print("✅ Windows build completed")
    except subprocess.CalledProcessError:
        print("⚠️ Windows build failed. Trying WSL2...")
        build_wsl2()

def verify_build():
    """ビルド検証"""
    print("[3/5] Verifying build...")

    try:
        import your_package._C as _C
        funcs = [f for f in dir(_C) if not f.startswith('_')]
        print(f"✅ Build verified. Functions: {len(funcs)}")
        for func in funcs[:5]:  # 最初の5個を表示
            print(f"   - {func}")
    except ImportError as e:
        print(f"❌ Build verification failed: {e}")
        sys.exit(1)

def run_tests():
    """テスト実行"""
    print("[4/5] Running tests...")

    result = subprocess.run(['pytest', '-v', 'tests/'], capture_output=True, text=True)
    if result.returncode == 0:
        print("✅ All tests passed")
    else:
        print(f"⚠️ Some tests failed:\n{result.stdout}")

def main():
    print("=== Auto Build Script ===\n")

    check_environment()

    if platform.system() == "Windows":
        # WSL2優先（安定性のため）
        try:
            subprocess.run(['wsl', '--status'], capture_output=True, check=True)
            print("ℹ️ WSL2 detected. Using WSL2 build (recommended).")
            build_wsl2()
        except (FileNotFoundError, subprocess.CalledProcessError):
            print("ℹ️ WSL2 not available. Using Windows build.")
            build_windows()
    else:
        # Linux/macOS
        subprocess.run(['python3', 'setup.py', 'build_ext', '--inplace'], check=True)

    verify_build()
    run_tests()

    print("\n[5/5] ✅ Build completed successfully!")

if __name__ == "__main__":
    main()
```

実行：

```bash
python auto_build.py
```

## クイックリファレンス

| エラー | 解決策 | 優先度 |
|--------|--------|--------|
| `cusparseGetErrorString` 再定義 | WSL2ビルド / インクルード順序 | ⭐⭐⭐ |
| `cannot open file 'python311.lib'` | VS Developer Command Prompt | ⭐⭐⭐ |
| `externally-managed-environment` | `setup.py` 直接実行 | ⭐⭐ |
| `ninja: error` | `MAX_JOBS=1` / WSL2 | ⭐⭐ |
| `Unsupported gpu architecture 'compute_120'` | setup.pyでarch指定 | ⭐⭐⭐ |

## 推奨環境構築フロー

### 新規セットアップ（Windows）

```bash
# 1. WSL2インストール（推奨）
wsl --install -d Ubuntu-24.04

# 2. WSL2内でCUDA Toolkit
wsl -d Ubuntu-24.04
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb
sudo apt update
sudo apt install -y cuda-toolkit-12-8

# 3. PyTorch
pip3 install torch==2.8.0+cu128 --index-url https://download.pytorch.org/whl/cu128

# 4. ビルドツール
sudo apt install -y ninja-build build-essential

# 5. プロジェクトビルド
cd /mnt/d/work/Projects/your-project/src/your_package
python3 setup.py build_ext --inplace
```

### 既存環境の修正

```bash
# Windows（VS Build Tools使用）
python auto_build.py  # 上記の統合スクリプト

# または手動
"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat"
set DISTUTILS_USE_SDK=1
cd /d "D:\work\Projects\..."
python setup.py build_ext --inplace
```

## まとめ

1. **WSL2ビルドが最も安定**（cusparse衝突、ninja問題を回避）
2. **Windows直接ビルドはVS Developer Command Prompt必須**
3. **PEP 668は`setup.py`直接実行で回避**
4. **sm_120対応はsetup.pyで`-gencode`指定**
5. **自動ビルドスクリプトで環境差を吸収**

## トラブルシューティングチェックリスト

- [ ] CUDA 12.8以降がインストールされているか？
- [ ] PyTorch 2.8がインストールされているか？
- [ ] WSL2が利用可能か？（Windows）
- [ ] VS Build Tools 2022がインストールされているか？（Windows直接ビルド時）
- [ ] `nvcc --version`と`torch.version.cuda`が一致するか？
- [ ] `torch.cuda.is_available()`が`True`を返すか？
- [ ] setup.pyに正しい`-gencode`が指定されているか？（RTX 5090の場合）

## 参考資料

- [PyTorch CUDA Extension Documentation](https://pytorch.org/tutorials/advanced/cpp_extension.html)
- [CUDA 12.8 Release Notes](https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/index.html)
- [PEP 668 – Marking Python base environments as "externally managed"](https://peps.python.org/pep-0668/)
- [NVIDIA Compute Capability Table](https://developer.nvidia.com/cuda-gpus)

---

この記事は実際のプロジェクト（3dgs-unified、2026年1-2月）で遭遇した問題の解決策をまとめたものです。特にRTX 5090（Blackwell世代）環境での知見を反映しています。
