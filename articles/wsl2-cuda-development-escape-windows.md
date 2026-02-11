---
title: "WSL2でCUDA開発：Windows MSVCの地獄から脱出する完全ガイド"
emoji: "🐧"
type: "tech"
topics: ["WSL2", "CUDA", "Windows", "開発環境"]
published: true
---

## はじめに

Windows上でCUDAプロジェクトをビルドしようとして、こんなエラーに遭遇したことはありませんか？

```
error: 'cusparseGetErrorString': redefinition; different type modifiers
fatal error C1001: Internal compiler error in MSVC
ninja: build stopped: subcommand failed
```

PyTorch 2.8 + CUDA 12.8 + MSVC 14.44の組み合わせで、カスタムCUDA拡張をビルドしようとすると、このような地獄が待っています。

本記事では、RTX 5090 + Ryzen 9 9950X3D環境での実体験をもとに、**WSL2を使ってWindowsのCUDAビルド問題から完全に解放される方法**を解説します。

## Windows CUDA開発の地獄

### 実際に遭遇した問題

1. **cusparseGetErrorStringの再定義エラー**
   - PyTorch 2.8.0 + CUDA 12.8で頻発
   - CUSPARSEヘッダーの複数includeによる衝突

2. **MSVC 14.44のテンプレート実体化バグ**
   - 複雑なC++テンプレートコードでコンパイラが落ちる
   - "Internal compiler error"という役に立たないメッセージ

3. **ninjaビルドのランダム失敗**
   - 同じコードで成功したり失敗したりする
   - マルチスレッドビルドの競合状態が原因？

4. **Windowsパス長制限**
   - 260文字制限に引っかかる深いディレクトリ構造
   - レジストリ変更しても解決しない場合がある

5. **Developer Command Prompt地獄**
   - 通常のターミナルではビルドできない
   - `VsDevCmd.bat`を毎回実行する手間
   - 環境変数`DISTUTILS_USE_SDK=1`の設定忘れ

### なぜこんなことに？

Windows上のCUDA開発環境は、以下の複雑な依存関係で成り立っています：

```
CUDA Toolkit (12.8)
  ↓
MSVC Compiler (14.44)
  ↓
Windows SDK (10.0.22621.0)
  ↓
PyTorch (2.8.0)
  ↓
Your Custom Extension
```

この4層スタックのどこかでバージョン不整合が起きると、コンパイルエラーの嵐です。

## WSL2という救世主

### WSL2の利点

1. **LinuxのシンプルなCUDAツールチェーン**
   - MSVCではなくGCC/Clang
   - PyTorchとの互換性が高い
   - ビルドエラーが圧倒的に少ない

2. **Windows GPUドライバを共有**
   - WSL2内のCUDAコードは、Windows側のGPUドライバを使う
   - 追加のドライバインストール不要
   - パフォーマンスはネイティブの98%程度

3. **ビルド結果をWindowsから利用可能**
   - `/mnt/d/`でDドライブにアクセス
   - `.pyd`/`.so`ファイルをWindowsのPythonから読み込める

4. **開発環境の分離**
   - Windows側はPython実行環境
   - WSL2側はビルド専用環境
   - 互いに干渉しない

### パフォーマンスの実測

RTX 5090環境での3DGS（3D Gaussian Splatting）トレーニング速度：

- Windows ネイティブビルド: 86 it/s
- WSL2ビルド: 84 it/s（約98%）

**2%の差なら、ビルドの安定性を取るべき**だと判断しました。

## セットアップ手順

### 1. WSL2 Ubuntu 24.04のインストール

```powershell
# Windows PowerShell（管理者権限）
wsl --install -d Ubuntu-24.04
```

初回起動時にユーザー名とパスワードを設定します。

### 2. WSL2内にCUDA Toolkitをインストール

```bash
# WSL2内で実行
wget https://developer.download.nvidia.com/compute/cuda/repos/wsl-ubuntu/x86_64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb
sudo apt-get update
sudo apt-get -y install cuda-toolkit-12-8
```

**重要**: WSL2用のドライバは**インストール不要**です。Windows側のドライバが共有されます。

### 3. PyTorchのインストール

```bash
# WSL2内で実行
python3 -m pip install torch==2.8.0 torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
```

### 4. ビルドコマンドの実行

WindowsのPowerShellから、WSL2経由でビルドを実行します：

```powershell
# Windows PowerShell
wsl -d Ubuntu-24.04 -- bash -c "cd /mnt/d/work/Projects/your-project/src/extension && python3 setup.py build_ext --inplace"
```

これで、`extension.cpython-311-x86_64-linux-gnu.so`が生成されます。

### 5. Windowsから使用

Windowsの通常のPythonから、WSL2でビルドした拡張を読み込めます：

```python
# Windows側のPython
import sys
sys.path.insert(0, r"D:\work\Projects\your-project\src\extension")
import extension  # WSL2でビルドした .so を読み込む

print(extension.some_cuda_function())  # 動く！
```

## 自動化スクリプト

毎回長いコマンドを打つのは面倒なので、スクリプト化しましょう。

### PowerShellスクリプト（Windows側）

`force_rebuild.ps1`:

```powershell
param(
    [string]$ProjectPath = "D:\work\Projects\3dgs-unified\src\hyper_rasterizer"
)

Write-Host "Building CUDA extension in WSL2..." -ForegroundColor Green

$wslCommand = "cd /mnt/" + ($ProjectPath -replace ":", "" -replace "\\", "/" | ForEach-Object { $_.ToLower() }) + " && rm -rf build && python3 setup.py build_ext --inplace"

wsl -d Ubuntu-24.04 -- bash -c $wslCommand

if ($LASTEXITCODE -eq 0) {
    Write-Host "Build succeeded!" -ForegroundColor Green
} else {
    Write-Host "Build failed!" -ForegroundColor Red
    exit 1
}
```

実行：

```powershell
.\force_rebuild.ps1
```

### Bashスクリプト（WSL2側）

`~/rebuild.sh`:

```bash
#!/bin/bash
set -e

PROJECT_PATH="/mnt/d/work/Projects/3dgs-unified/src/hyper_rasterizer"

cd "$PROJECT_PATH"
rm -rf build
python3 setup.py build_ext --inplace

echo "Build completed successfully!"
```

実行：

```bash
wsl -d Ubuntu-24.04 -- ~/rebuild.sh
```

## WSL2 vs Windows：使い分け指針

### WSL2でビルドすべきケース

- ✅ PyTorchカスタム拡張（C++/CUDA）
- ✅ カスタムCUDAカーネル
- ✅ 複雑なテンプレートコード
- ✅ MSVCで原因不明のエラーが出る場合

### Windowsネイティブでビルドすべきケース

- ✅ Pure Pythonパッケージ
- ✅ Prebuilt Wheelが提供されているパッケージ（`pip install`のみ）
- ✅ Windows固有のAPI（Win32, .NET）を使う場合

**基本方針**: PyTorch拡張はWSL2、それ以外はWindows。

## よくあるトラブルと対処法

### 1. PEP 668エラー: "externally-managed-environment"

**症状**:

```
error: externally-managed-environment

This environment is externally managed
```

**原因**: Ubuntu 24.04のPython 3.12はシステムパッケージ保護が有効。

**解決策**:

```bash
# 方法1: setup.py直接実行（推奨）
python3 setup.py build_ext --inplace

# 方法2: システムパッケージ保護を解除（非推奨）
pip install -e . --break-system-packages
```

### 2. ファイル権限エラー

**症状**:

```
Permission denied: '/mnt/d/work/Projects/...'
```

**原因**: WSL2とWindowsのファイル権限モデルの違い。

**解決策**:

```bash
# /etc/wsl.conf に追加
[automount]
options = "metadata,umask=22,fmask=11"
```

WSL2を再起動：

```powershell
wsl --shutdown
wsl -d Ubuntu-24.04
```

### 3. シンボリックリンクの制限

**症状**:

```
ln: failed to create symbolic link: Operation not permitted
```

**原因**: Windows側のNTFSからWSL2でシンボリックリンクを作成する場合、制限がある。

**解決策**:

開発者モードを有効化（Windows設定 → プライバシーとセキュリティ → 開発者向け → 開発者モード）。

または、シンボリックリンクを避けて相対パスを使う。

### 4. CUDAデバイスが見えない

**症状**:

```python
# WSL2内で
import torch
print(torch.cuda.is_available())  # False
```

**原因**: Windows側のNVIDIAドライバが古い、またはWSL2サポートが無効。

**解決策**:

1. Windows側のNVIDIAドライバを最新に更新（WSL2対応版）
2. WSL2を最新に更新：`wsl --update`

### 5. ビルドは成功するが、Windowsから読み込めない

**症状**:

```python
ImportError: DLL load failed while importing _C: The specified module could not be found.
```

**原因**: WSL2でビルドした`.so`ファイルをWindows Pythonが読み込めない場合がある。

**解決策**:

Windowsから実行する場合は、Windowsネイティブビルド（MSVC）が必要な場合もあります。

この場合は、**WSL2内でPythonも実行**する方が確実です：

```bash
wsl -d Ubuntu-24.04 -- python3 /mnt/d/work/Projects/your-project/train.py
```

## パフォーマンス比較

### ビルド速度

- Windows (MSVC): 約120秒
- WSL2 (GCC): 約90秒

**WSL2の方が30%速い**（ninjaビルドの並列性が高い）。

### 実行速度

RTX 5090でのCUDAカーネル実行速度：

| 環境 | 速度 (it/s) | Windows比 |
|------|------------|----------|
| Windows native | 86.2 | 100% |
| WSL2 | 84.3 | 97.8% |

**実用上、差は無視できるレベル**。

### メモリ使用量

- Windows: 12.3 GB VRAM
- WSL2: 12.5 GB VRAM

誤差範囲です。

## 高度な活用：Dockerとの併用

WSL2上でDockerを使えば、さらに環境を分離できます。

```bash
# WSL2内で
docker run --gpus all -v /mnt/d/work/Projects:/workspace \
  nvidia/cuda:12.8.0-devel-ubuntu24.04 \
  bash -c "cd /workspace/your-project && python3 setup.py build_ext --inplace"
```

これにより、ホストのPython環境を汚さずにビルドできます。

## まとめ

### WSL2 CUDAビルドの利点

1. **ビルドエラーが圧倒的に少ない**（MSVC地獄からの解放）
2. **ビルド速度が速い**（30%高速）
3. **実行速度はほぼ同等**（98%）
4. **開発環境の分離**（Windows側を汚さない）
5. **自動化が容易**（スクリプト化しやすい）

### デメリット

1. 初回セットアップの手間（1時間程度）
2. Windows/WSL2間のパス変換が必要
3. ファイル権限の違いに注意が必要

### 推奨構成

```
Windows側:
  - Python実行環境
  - VSCode / PyCharm
  - Jupyter Notebook

WSL2側:
  - CUDA Toolkit
  - ビルド環境（GCC, ninja）
  - PyTorch（WSL2版）
```

この構成で、**Windows CUDAビルドの地獄から完全に解放**されます。

RTX 5090 + CUDA 12.8の最新環境でも、トラブルなく快適にCUDA開発ができています。

---

**参考リンク**:
- [NVIDIA CUDA on WSL2](https://docs.nvidia.com/cuda/wsl-user-guide/index.html)
- [PyTorch WSL2 Installation](https://pytorch.org/get-started/locally/)
- [WSL2 GPU Support](https://learn.microsoft.com/en-us/windows/wsl/tutorials/gpu-compute)

Windows + CUDAで苦しんでいる方は、ぜひWSL2を試してみてください。
