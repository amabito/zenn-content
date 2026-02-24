---
title: "RTX 5090 (sm_120) でPyTorch 2.8.0を選んだ理由: CUDA 12.8環境構築の落とし穴"
emoji: "⚡"
type: "tech"
topics: ["cuda", "pytorch", "rtx5090", "windows", "3dgs"]
published: true
published_at: "2026-03-02 12:00"
---

## RTX 5090を買った

2026年1月、RTX 5090（32GB VRAM, sm_120）をRyzen 9 9950X3Dと組み合わせた開発機を構築した。

3DGSのカスタムCUDAカーネル開発が主な用途だ。RTX 4090（sm_89）から移行することになる。

---

## 最初の壁: sm_120（Blackwell）とは何か

RTX 5090のCUDAアーキテクチャは**sm_120（Blackwell）**だ。

sm_120は2025年末に登場した新アーキテクチャで、いくつかの特徴がある。

### Blackwellの変更点（sm_89→sm_120）

既存のCUDAカーネルをsm_120向けにリコンパイルするだけでは動く。ただし最適化の観点では注意点がある。

```makefile
# CMakeLists.txtでのアーキテクチャ指定
set_target_properties(my_cuda_ext PROPERTIES
    CUDA_ARCHITECTURES "89;120"  # 4090+5090両対応
)
```

sm_120で新しく使えるようになった機能（Tensor Memory Accelerator等）を使わない限り、基本的な互換性は保たれる。

### 最大共有メモリ

sm_120の最大共有メモリは**100KB**（動的確保時）。静的な`__shared__`は48KB上限が続く。

```
sm_86 (RTX 3090): 100KB
sm_89 (RTX 4090): 100KB
sm_120 (RTX 5090): 100KB
```

この点は変わらない。

---

## 本題: PyTorchのバージョン選択

### PyTorch 2.9.0+を試してすぐ諦めた

最初にPyTorch最新版（2.9.0+cu128）を試した。

```bash
pip install torch==2.9.0+cu128 --index-url https://download.pytorch.org/whl/cu128
```

カスタムCUDAカーネルをビルドしようとすると：

```
D:\PyTorch\include\torch\csrc\api\include\torch\nn\functional.h(1): error C2039: 'GetErrorString':
is not a member of 'cusparseas'
```

あるいは：

```
C:\Users\...\include\cusparse.h(1234): error C2371: 'cusparseGetErrorString':
redefinition; different basic types
```

`cusparseGetErrorString`の再定義エラーだ。

### 原因: PyTorch 2.9.0+とMSVC + CUDA 12.8の衝突

このエラーはPyTorch 2.9.0以降のヘッダーファイルと、CUDA 12.8のcusparseヘッダーの間で発生する型定義の衝突だ。

CUDA 12.8で`cusparseGetErrorString`の定義が変更され、PyTorch側の内部定義と競合する。

Linuxではgccを使うため発生しにくいが、Windows + MSVCの組み合わせで頻発する。

### 解決策: PyTorch 2.8.0に固定

```bash
pip install torch==2.8.0+cu128 torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cu128
```

PyTorch 2.8.0+cu128は、CUDA 12.8 + Windows + MSVC 14.44の組み合わせで安定している。

```python
import torch
print(torch.__version__)   # 2.8.0+cu128
print(torch.cuda.is_available())  # True
print(torch.cuda.get_device_name(0))  # NVIDIA GeForce RTX 5090
```

---

## Windowsでのカスタムカーネルビルド

### 必須: VS Developer Command Promptを使う

通常のPowerShellやコマンドプロンプトではビルドが失敗することがある。**Visual Studio Developer Command Prompt**を使うこと。

```cmd
:: VS Build Tools 2022のDeveloper Command Promptを開く
"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat" -arch=amd64
:: -arch=amd64が重要（省略するとx86のcl.exeが使われることがある）

set DISTUTILS_USE_SDK=1

cd /d "D:\work\Projects\my_project\src\my_extension"
pip install -e . --no-build-isolation
```

`-arch=amd64`を省略すると、x86版の`cl.exe`が選ばれることがあり、そこからcudafe++が呼ばれると謎のクラッシュが起きる。

### DISTUTILS_USE_SDK=1

この環境変数を設定しないと、PythonのビルドシステムがVisual Studioのコンパイラを正しく検出できないことがある。

```cmd
set DISTUTILS_USE_SDK=1
set MSSdk=1
```

### ビルドスクリプトの例

```batch
@echo off
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat" -arch=amd64

set DISTUTILS_USE_SDK=1
set MSSdk=1

cd /d "D:\work\Projects\my_project\src\my_extension"

echo [BUILD] Cleaning old build artifacts...
if exist build rmdir /s /q build

echo [BUILD] Building CUDA extension...
pip install -e . --no-build-isolation --verbose 2>&1 | findstr /i "error warning"

echo [BUILD] Verifying...
python -c "import my_extension; print('OK:', dir(my_extension))"
```

---

## WSL2での代替ビルド

Windowsでのビルドに問題が生じたとき、WSL2（Ubuntu 24.04）でのビルドが安定している。

```bash
# WSL2でのビルド
wsl -d Ubuntu-24.04 -- bash -c "
    cd /mnt/d/work/Projects/my_project/src/my_extension && \
    rm -rf build && \
    python3 setup.py build_ext --inplace
"
```

WSL2でビルドした`.so`ファイルは、WindowsのPythonからは使えない（ELF vs PEの問題）。

WSL2ビルドはWSL2上のPython環境で使う場合に有効だ。

### なぜWSL2が安定しているか

1. gcc + nvccの組み合わせが安定している（MSVCを経由しない）
2. cusparse等のCUDAヘッダーとgccの互換性が高い
3. PEP 668問題（externally-managed-environment）は`setup.py build_ext --inplace`で回避できる

---

## 既存ビルドの維持

一度安定したビルド（`.pyd`ファイル）を得たら、**簡単には再ビルドしない**という判断をした。

理由：

1. PyTorch 2.8.0の`cusparseGetErrorString`問題は解決済みだが、2.9.0以降で再発する可能性が残る
2. sm_120のサポートは完全には確立されていない（2026年2月時点）
3. ビルドに失敗するとカーネル開発が止まる

```python
# 既存ビルドの動作確認
import my_extension._C as _C
print([f for f in dir(_C) if not f.startswith('_')])
# 期待する関数が全て表示されればOK
```

ビルド済みの`.pyd`が動作しているなら、PyTorchや環境を更新するモチベーションは低い。

---

## 環境まとめ

```
CPU: Ryzen 9 9950X3D
GPU: RTX 5090 (32GB, sm_120, Blackwell)
OS: Windows 11 Pro
CUDA: 12.8
Driver: 591.74
Python: 3.11.9
PyTorch: 2.8.0+cu128
MSVC: 14.44 (VS Build Tools 2022)
```

この組み合わせで、カスタムCUDAカーネルのビルドと実行が安定している。

---

## トラブルシューティング

### cusparseGetErrorString 再定義エラー

**症状**: ビルド時に`error C2371: 'cusparseGetErrorString': redefinition`

**原因**: PyTorch 2.9.0+とCUDA 12.8のcusparseヘッダーの衝突

**解決策**: PyTorch 2.8.0に固定

```bash
pip install torch==2.8.0+cu128 --index-url https://download.pytorch.org/whl/cu128
```

### "Unable to find Visual Studio"

**症状**: `python setup.py build_ext`で`Unable to find Visual Studio`

**解決策**: VS Developer Command Promptを使う（通常のターミナルはNG）

### cudafe++ クラッシュ

**症状**: ビルド途中でcudafe++がセグメンテーションフォルトのように落ちる

**解決策**: VsDevCmd.batに`-arch=amd64`を付ける

```cmd
call VsDevCmd.bat -arch=amd64  :: ← これが重要
```

### sm_120の明示指定

**症状**: 正常にビルドできるがRTX 5090でのパフォーマンスが低い

**原因**: sm_86やsm_89向けにコンパイルされたコードをJITコンパイルで動かしている

**解決策**: `CUDA_ARCHITECTURES`に120を追加

```python
# setup.py内
extra_compile_args = {
    "nvcc": [
        "-arch=sm_120",
        # または複数アーキテクチャ
        # "--generate-code", "arch=compute_89,code=sm_89",
        # "--generate-code", "arch=compute_120,code=sm_120",
    ]
}
```

---

## 学んだこと

1. **PyTorch最新版≠最適版**: CUDA 12.8+Windowsでは2.8.0が安定
2. **VSDevCmd.batに`-arch=amd64`を必ず付ける**: 省略するとx86ビルドになりうる
3. **安定したビルドは壊さない**: 環境アップデートは慎重に
4. **WSL2は代替手段として強力**: MSVCを回避できる

RTX 5090自体は素直で、sm_120向けに正しくビルドすれば既存のCUDAカーネルはほぼそのまま動く。問題はWindows環境のツールチェーンにある。
