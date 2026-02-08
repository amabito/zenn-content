---
title: "Windows CUDA環境構築2026：PyTorch 2.8+RTX 5090対応"
emoji: "🔧"
type: "tech"
topics: ["Windows", "CUDA", "PyTorch", "環境構築", "RTX5090"]
published: false
---

# 結論から言う

**Windows 11でCUDA 12.8 + PyTorch 2.8.0 + RTX 5090の環境構築は、MSVC衝突を回避すればスムーズ。** PyTorch 2.9.0以降は避け、2.8.0を使う。この記事では、2026年1月時点の最新・最安定構成を完全解説する。

**対象読者:**
- WindowsでCUDA環境を構築したい人
- RTX 5090 Blackwellを最大限活用したい人
- PyTorch + CUDA で開発する全ての人

**この記事で得られること:**
- 2026年最新の推奨構成（バージョン番号）
- MSVC衝突等のトラブル回避方法
- 動作確認コマンド一式

---

## 推奨構成（2026年1月時点）

### 最安定構成

| コンポーネント | バージョン | 理由 |
|--------------|-----------|------|
| **OS** | Windows 11 23H2 | 最新機能対応 |
| **GPU** | RTX 4090 / RTX 5090 | Blackwell世代推奨 |
| **Driver** | 591.74以降 | RTX 5090対応 |
| **CUDA Toolkit** | **12.8** | Blackwell最適化 |
| **cuDNN** | **9.0.0** | CUDA 12.8対応 |
| **Python** | 3.11.9 | 安定版 |
| **PyTorch** | **2.8.0+cu128** | **重要: 2.9.0はMSVC衝突** |

### なぜこの構成か

```
PyTorch 2.8.0:
  ✅ CUDA 12.8対応
  ✅ MSVC 14.44との互換性あり
  ✅ RTX 5090 (sm_120)サポート

PyTorch 2.9.0以降:
  ❌ MSVC 14.44と衝突
  ❌ ビルドエラー頻発
  → 回避: 2.8.0を使用
```

---

## 完全インストール手順

### Step 1: NVIDIA Driverインストール

```powershell
# 公式サイトからダウンロード
https://www.nvidia.com/Download/index.aspx

# RTX 5090の場合: Game Ready Driver 591.74以降
# または Studio Driver 591.74以降

# インストール後、再起動
# 確認:
nvidia-smi
```

**出力例:**

```
+-----------------------------------------------------------------------------+
| NVIDIA-SMI 591.74       Driver Version: 591.74       CUDA Version: 12.8     |
|-------------------------------+----------------------+----------------------+
| GPU  Name            TCC/WDDM | Bus-Id        Disp.A | Volatile Uncorr. ECC |
| Fan  Temp  Perf  Pwr:Usage/Cap|         Memory-Usage | GPU-Util  Compute M. |
|===============================+======================+======================|
|   0  NVIDIA GeForce ... WDDM  | 00000000:01:00.0  On |                  N/A |
| 30%   35C    P8    25W / 450W |    512MiB / 32768MiB |      0%      Default |
+-------------------------------+----------------------+----------------------+
```

---

### Step 2: Python 3.11.9 インストール

```powershell
# 公式サイトからダウンロード
https://www.python.org/downloads/release/python-3119/

# インストーラー実行
# ☑ Add Python 3.11 to PATH（チェック必須）
# Install Now

# 確認:
python --version
# Python 3.11.9

pip --version
# pip 24.0 from ...
```

---

### Step 3: CUDA Toolkit 12.8 インストール

```powershell
# 公式サイトからダウンロード
https://developer.nvidia.com/cuda-downloads

# Windows > x86_64 > 11 > exe (network)
# cuda_12.8.0_windows_network.exe をダウンロード

# インストーラー実行
# カスタムインストールを選択:

選択する項目:
  ☑ CUDA Toolkit
  ☑ CUDA Documentation
  ☑ CUDA Samples
  ☑ Nsight Systems
  ☑ Nsight Compute

選択しない項目:
  ☐ Visual Studio Integration（競合リスク）
  ☐ GeForce Experience
  ☐ PhysX

# インストール先: C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8
```

---

### Step 4: cuDNN 9.0.0 インストール

```powershell
# 公式サイトからダウンロード（NVIDIA Developer登録必要）
https://developer.nvidia.com/cudnn-downloads

# cudnn-windows-x86_64-9.0.0.312_cuda12-archive.zip をダウンロード

# 展開して、CUDA_PATHにコピー
xcopy /E /I cudnn-windows-x86_64-9.0.0.312_cuda12\bin "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8\bin"
xcopy /E /I cudnn-windows-x86_64-9.0.0.312_cuda12\include "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8\include"
xcopy /E /I cudnn-windows-x86_64-9.0.0.312_cuda12\lib "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8\lib"
```

---

### Step 5: 環境変数設定

```powershell
# システム環境変数に追加（管理者権限で実行）

# CUDA_HOME
setx CUDA_HOME "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8" /M

# CUDA_PATH
setx CUDA_PATH "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8" /M

# PATH（既存のPATHに追加）
setx PATH "%PATH%;C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8\bin;C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8\libnvvp" /M

# 再起動（環境変数反映のため）
shutdown /r /t 0
```

---

### Step 6: PyTorch 2.8.0 インストール

```bash
# **重要: 2.8.0を指定（2.9.0以降は避ける）**

pip install torch==2.8.0+cu128 torchvision==0.19.0+cu128 torchaudio==2.8.0+cu128 --index-url https://download.pytorch.org/whl/cu128
```

**インストール時間:** 5-10分（ネットワーク速度に依存）

---

### Step 7: 動作確認

```python
import torch

# PyTorchバージョン
print(f"PyTorch: {torch.__version__}")
# 期待: 2.8.0+cu128

# CUDA利用可能か
print(f"CUDA Available: {torch.cuda.is_available()}")
# 期待: True

# CUDAバージョン
print(f"CUDA Version: {torch.version.cuda}")
# 期待: 12.8

# GPU名
print(f"GPU: {torch.cuda.get_device_name(0)}")
# 期待: NVIDIA GeForce RTX 5090 (or RTX 4090)

# Compute Capability
print(f"Compute Capability: {torch.cuda.get_device_capability(0)}")
# 期待: (10, 0) for RTX 5090, (8, 9) for RTX 4090

# 簡単な演算テスト
x = torch.rand(1000, 1000).cuda()
y = torch.rand(1000, 1000).cuda()
z = torch.matmul(x, y)
print(f"Matrix Multiplication: {z.shape}")
# 期待: torch.Size([1000, 1000])
```

**全てがOKなら、環境構築完了！**

---

## よくあるトラブルと対処法

### トラブル1: PyTorch 2.9.0でMSVC衝突

```
Error: MSVC 14.44 is not compatible with CUDA 12.8
```

**原因:** PyTorch 2.9.0以降がMSVC 14.44と衝突。

**対処法:**

```bash
# PyTorch 2.8.0にダウングレード
pip uninstall torch torchvision torchaudio
pip install torch==2.8.0+cu128 torchvision==0.19.0+cu128 torchaudio==2.8.0+cu128 --index-url https://download.pytorch.org/whl/cu128
```

---

### トラブル2: `torch.cuda.is_available()` が False

**原因1:** Driverが古い

```powershell
# Driver更新
nvidia-smi
# バージョン確認 → 591.74以降か？
```

**原因2:** PyTorchがCPU版

```bash
# CUDA版を再インストール
pip uninstall torch
pip install torch==2.8.0+cu128 --index-url https://download.pytorch.org/whl/cu128
```

**原因3:** 環境変数が反映されていない

```powershell
# 再起動
shutdown /r /t 0
```

---

### トラブル3: cuDNNが見つからない

```
Could not find cudnn_ops_infer64_9.dll
```

**対処法:**

```powershell
# cuDNNのDLLがPATHに含まれているか確認
echo %PATH%
# C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8\bin が含まれているか

# 含まれていない場合、Step 5を再実行
```

---

### トラブル4: CUDA out of memory

```
RuntimeError: CUDA out of memory
```

**対処法:**

```python
# バッチサイズを減らす
batch_size = 8  # 16 → 8

# または Gradient Checkpointing
from torch.utils.checkpoint import checkpoint

def forward(self, x):
    x = checkpoint(self.layer1, x)
    return x
```

---

### トラブル5: 学習が遅い

**原因:** CPUで実行されている可能性

```python
# モデルとデータをGPUに明示的に転送
model = MyModel().cuda()
data = data.cuda()
```

---

## 追加パッケージ推奨

### 3D Gaussian Splatting開発

```bash
pip install numpy scipy matplotlib
pip install imageio opencv-python
pip install tqdm
```

### CUDA拡張開発

```bash
pip install ninja  # 高速ビルド
```

### Jupyter Notebook

```bash
pip install jupyter notebook ipykernel
python -m ipykernel install --user --name pytorch --display-name "PyTorch 2.8.0"
```

---

## パフォーマンス確認

### ベンチマークスクリプト

```python
import torch
import time

# デバイス情報
device = torch.device('cuda')
print(f"GPU: {torch.cuda.get_device_name(0)}")
print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.2f} GB")

# 行列乗算ベンチマーク
sizes = [1000, 2000, 4000, 8000]
for size in sizes:
    x = torch.rand(size, size, device=device)
    y = torch.rand(size, size, device=device)

    # ウォームアップ
    _ = torch.matmul(x, y)
    torch.cuda.synchronize()

    # 計測
    start = time.time()
    for _ in range(10):
        z = torch.matmul(x, y)
        torch.cuda.synchronize()
    elapsed = time.time() - start

    flops = 2 * size**3 * 10 / elapsed / 1e12  # TFLOPS
    print(f"Size {size}x{size}: {elapsed/10*1000:.2f}ms, {flops:.2f} TFLOPS")
```

**期待値（RTX 5090）:**

```
Size 1000x1000: 0.5ms, 4.0 TFLOPS
Size 2000x2000: 2.0ms, 8.0 TFLOPS
Size 4000x4000: 10.0ms, 12.8 TFLOPS
Size 8000x8000: 60.0ms, 17.1 TFLOPS
```

---

## Visual Studio Code設定（推奨）

### 拡張機能

```
- Python（Microsoft）
- Pylance（Microsoft）
- Jupyter（Microsoft）
- CUDA C/C++（NVIDIA）
```

### settings.json

```json
{
  "python.defaultInterpreterPath": "C:\\Users\\YourName\\AppData\\Local\\Programs\\Python\\Python311\\python.exe",
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": true,
  "editor.formatOnSave": true,
  "python.formatting.provider": "black"
}
```

---

## まとめ

| 項目 | 推奨バージョン |
|------|--------------|
| **OS** | Windows 11 23H2 |
| **Driver** | 591.74以降 |
| **CUDA Toolkit** | 12.8 |
| **cuDNN** | 9.0.0 |
| **Python** | 3.11.9 |
| **PyTorch** | **2.8.0+cu128**（2.9.0以降は避ける） |

**重要なポイント:**

1. PyTorch 2.8.0を使う（2.9.0はMSVC衝突）
2. 環境変数を正しく設定（再起動必須）
3. cuDNNのDLLをCUDA PATHにコピー

この手順で、Windows 11でのCUDA環境構築は完了する。RTX 5090の性能を最大限引き出せる。

---

## 関連記事

- [無料] [RTX 5090 Blackwell最適化ガイド](https://zenn.dev/amabito/articles/rtx5090-blackwell-optimization-2026) - 最適化テクニック
- [無料] [CUDA最適化入門](https://zenn.dev/amabito/articles/cuda-optimization-basics) - CUDA基礎
- [無料] [PyTorch CUDA拡張開発](https://zenn.dev/amabito/articles/pytorch-cuda-extension) - カスタムカーネル
- [無料] [RTX 5090 vs RTX 4090比較](https://zenn.dev/amabito/articles/rtx5090-vs-rtx4090) - ベンチマーク

---

## 参考

- [CUDA Toolkit Documentation](https://docs.nvidia.com/cuda/) - NVIDIA公式
- [PyTorch Installation Guide](https://pytorch.org/get-started/locally/) - PyTorch公式
- [cuDNN Documentation](https://docs.nvidia.com/deeplearning/cudnn/) - cuDNN公式
- [RTX 5090 Compatibility Guide](https://apatero.com/blog/rtx-5090-cuda-12-8-compatibility-fix-complete-guide-2025) - トラブルシューティング

---

ご質問・ご相談はコメント欄へ。
