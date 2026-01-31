---
title: "CUDA 12.8 Blackwell対応の全貌：sm_120開発者が知るべき新機能"
emoji: "⚡"
type: "tech"
topics: ["CUDA", "Blackwell", "RTX5090", "GPU", "sm120"]
published: true
published_at: "2026-02-09 07:00"
---

# 結論から言う

**CUDA 12.8はBlackwell（sm_100/sm_101/sm_120）を完全サポートする最初のToolkitであり、コンパイラ・ライブラリ・開発ツールの全レイヤーで刷新が入った。** RTX 5090（sm_120）で開発するなら、CUDA 12.8以降は必須。

**対象読者:**
- RTX 5090 / Blackwell GPUでCUDA開発をしている人
- sm_89（Ada）からsm_120への移行を考えている人
- CUDA Toolkit 12.8の新機能を把握したい人

**この記事で得られること:**
- CUDA 12.8の主要変更点（コンパイラ、ライブラリ、API、ツール）
- Blackwellアーキテクチャ向けの実践的なビルド設定
- 開発者が押さえるべきポイントの全体像

---

## Blackwell GPUのSMバージョン

CUDA 12.8で追加されたBlackwellアーキテクチャのSMバージョンは3種類ある。

| SM | 対応GPU | 用途 |
|----|---------|------|
| sm_100 | B100, B200 | データセンター |
| sm_101 | Blackwell Thor, DIGITS | エッジ、組み込み |
| sm_120 | **RTX 5090, RTX 5080**, RTX 50シリーズ全般 | コンシューマ、ワークステーション |

sm_120はGB202/GB203/GB205/GB206/GB207チップに対応し、GeForce RTX 50シリーズの全モデルをカバーする。

---

## コンパイラ：LLVM 18ベースの新NVVM IRダイアレクト

### モダンダイアレクトとは

CUDA 12.8から、Blackwell以降のアーキテクチャ（`compute_100`以上）では**LLVM 18.1.8ベースの新しいNVVM IR ダイアレクト**（モダンダイアレクト）が使われる。

```
Pre-Blackwell (compute_89以下):
  → レガシーNVVM IRダイアレクト

Blackwell以降 (compute_100以上):
  → モダンNVVM IRダイアレクト（LLVM 18.1.8ベース）
```

### 開発者への影響

- ソースコードの変更は基本的に不要
- 古いダイアレクトで生成されたビットコードはBlackwell向けに再コンパイル可能（デバッグメタデータを除く）
- libNVVMを直接使用している場合は、モダンダイアレクトへの対応が必要

### ホストコンパイラ対応の拡充

| コンパイラ | CUDA 12.8対応 |
|-----------|--------------|
| GCC 14 | 新規対応 |
| MSVC 14.44 | 対応 |
| Clang 18 | 対応 |

GCC 14がホストコンパイラとして正式サポートされた。

---

## CUDA Graphs：IF/ELSEとSWITCHでGPU完結の動的制御フロー

### 従来の問題

CUDA Graphsは一連のGPU操作を事前に記録・再生する仕組みだが、動的な制御フロー（収束判定ループなど）にはCPUの介入が必要だった。

```
従来:
  GPU実行 → CPUで条件判定 → GPU再実行
  ※GPUとCPU間の同期がボトルネック
```

### CUDA 12.8の改善

新しい条件ノード型が追加された。

| ノード型 | 機能 |
|---------|------|
| IF/ELSE | 条件分岐（GPUで評価） |
| SWITCH | 多方向分岐（GPUで評価） |

```
CUDA 12.8:
  GPU実行 → GPU上で条件判定 → GPU内で分岐
  ※CPUとの同期が不要
```

### 効果

CPUオーバーヘッドが**最大2倍削減**される。反復収束アルゴリズム（CG法、ニュートン法など）で特に効果が大きい。

```cuda
// 概念的な使用例
cudaGraphConditionalHandle handle;
cudaGraphConditionalHandleCreate(&handle, graph, 1, 0);

// IF/ELSEノードでGPU上の条件判定
// 収束判定、閾値チェックなどがCPUを介さずに完結
```

---

## 数学ライブラリ：MX-FP8 / MX-FP4テンソルコア対応

### Blackwellテンソルコアの新データ型

Blackwellの第5世代テンソルコアは、ブロックスケーリング方式の新しい狭精度フォーマットに対応している。

| フォーマット | ビット幅 | 用途 |
|------------|---------|------|
| MXFP8 | 8-bit | 推論・学習 |
| MXFP4 | 4-bit | 推論（高スループット） |
| MXFP6 | 6-bit | 推論 |
| NVFP4 | 4-bit（NVIDIA独自） | 推論 |

### cuBLASの性能

cuBLAS 12.9以降では、これらのフォーマットを活用した行列演算が利用可能。

| 構成 | スループット |
|------|-------------|
| Blackwell FP4 (GB200) | 最大**6,787 TFLOPS/s** |
| Blackwell FP4 vs Hopper FP8 | **4.6倍高速** |
| BF16テンソルコアによるFP32エミュレーション | ネイティブFP32の**3〜4倍高速** |

### CUTLASS 3.8

NVIDIA CUTLASSもBlackwellテンソルコアをフルサポート。Blackwell GEMM性能はピークの**98%**を達成している。

```
CUTLASS 3.8でサポートされるデータ型:
├── MXFP4, MXFP6, MXFP8（OCP標準）
├── NVFP4（NVIDIA独自）
├── INT8, INT4
└── BF16, FP16, TF32
```

---

## 新API

### cudaStreamGetDevice

CUDAストリームに関連付けられたデバイスを取得するAPI。

```cuda
int device;
cudaStreamGetDevice(stream, &device);
```

従来は開発者がストリームとデバイスの対応を自分で管理する必要があった。マルチGPU環境でのコードが簡潔になる。

### cuMemcpyBatchAsync

複数のソース・デスティネーションバッファ間で、可変サイズの非同期メモリコピーをバッチ実行するAPI。

```cuda
// 複数のメモリコピーを1回のAPI呼び出しで実行
cuMemcpyBatchAsync(
    ops,       // コピー操作の配列
    numOps,    // 操作数
    stream     // CUDAストリーム
);
```

個別のcudaMemcpyAsyncを繰り返すよりもオーバーヘッドが小さい。大量の小さなバッファを転送するシナリオ（Gaussian Splattingのタイル処理など）で有効。

---

## HMM（Heterogeneous Memory Management）

### 概要

ホストメモリとGPUメモリの間でシームレスなデータ共有を可能にする機能。`cudaMalloc`を使わずに、通常のmallocで確保したメモリにGPUからアクセスできる。

### 制限事項

| 制限 | 詳細 |
|------|------|
| OS | Linux限定（カーネル6.1.24+または6.2.11+） |
| ドライバ | NVIDIA GPU Open Kernel Modules必須 |
| CPU | x86_64のみ（Armは未対応） |
| 性能 | cudaMallocよりは遅い（最適化途上） |
| GPU atomic | ファイルバックドメモリでのatomic操作は未対応 |

### 使いどころ

性能が最優先でない場面（プロトタイピング、データ前処理、ホスト↔GPU間の頻繁なデータ共有）で有効。明示的なメモリ管理のオーバーヘッドを削減できる。

---

## 開発ツールの改善

### Compute Sanitizer

| 改善点 | 詳細 |
|--------|------|
| **Pythonスタック対応** | Python経由で起動したCUDAカーネルのエラーを、Pythonコードの行番号まで追跡可能 |
| **テンソルコアガードレール** | Blackwellテンソルコアのプログラミングエラー（未割当メモリアクセス等）を検出 |
| **HMMサポート** | `--hmm-support`オプションでHMMアプリケーションの診断が可能 |

Pythonスタック対応は、PyTorchのカスタムCUDA拡張をデバッグする際に極めて有用。

```bash
# PyTorchカスタムCUDAカーネルのデバッグ
compute-sanitizer --tool memcheck python train.py
```

### nvdisasm

**JSON形式のSASS出力**が追加された。

```bash
# JSON形式で逆アセンブリ出力
nvdisasm --print-json kernel.cubin
```

自動化ツールとの統合（パフォーマンス解析パイプライン等）が容易になった。

---

## Pythonエコシステム：cuda.core / cuda.bindings

CUDA Pythonの構造が刷新された。

```
従来:
  cuda-python（単一パッケージ）

CUDA 12.8:
  cuda.core     → 高レベルのPythonic API
  cuda.bindings → 低レベルのCUDAバインディング
```

### cuda.core

Pythonらしいオブジェクトモデルで、デバイス管理・メモリ管理・カーネル起動を記述できる。

### cuda.bindings

CUDA Driver API / Runtime APIの薄いラッパー。従来のcuda-pythonの機能を引き継ぐ。

---

## RTX 5090での実践：ビルド設定

### CMakeでのsm_120指定

```cmake
set(CMAKE_CUDA_ARCHITECTURES "89;120")
```

sm_89（RTX 4090）とsm_120（RTX 5090）の両方に対応するバイナリを生成する。

### nvccの直接指定

```bash
nvcc -gencode=arch=compute_89,code=sm_89 \
     -gencode=arch=compute_120,code=sm_120 \
     kernel.cu -o kernel
```

### PyTorchカスタムCUDA拡張

```bash
TORCH_CUDA_ARCH_LIST="8.9;12.0" pip install -e .
```

または`setup.py`/`setup.cfg`で指定：

```python
# setup.py
import os
os.environ["TORCH_CUDA_ARCH_LIST"] = "8.9;12.0"
```

### PyTorch本体の対応状況

PyTorch安定版リリースは歴史的にsm_90までのサポートだった。RTX 5090（sm_120）で使うには**PyTorch Nightly（cu128以降）**が必要。PyTorch 2.8.0+cu128以降で安定した動作を確認している。

```bash
# PyTorch 2.8.0 cu128のインストール
pip install torch==2.8.0 --index-url https://download.pytorch.org/whl/cu128
```

---

## まとめ

| 分野 | CUDA 12.8の変更 |
|------|----------------|
| **コンパイラ** | LLVM 18ベースのモダンNVVM IR、GCC 14対応 |
| **CUDA Graphs** | IF/ELSE、SWITCHノードでGPU完結の制御フロー |
| **数学ライブラリ** | MX-FP8/FP4テンソルコア対応、cuBLASで6,787 TFLOPS/s |
| **新API** | cudaStreamGetDevice、cuMemcpyBatchAsync |
| **メモリ** | HMM（Linux限定） |
| **開発ツール** | Compute SanitizerのPythonスタック対応、nvdisasm JSON出力 |
| **Python** | cuda.core / cuda.bindings の分離 |
| **ビルド** | sm_120指定、TORCH_CUDA_ARCH_LIST="12.0" |

CUDA 12.8は「Blackwellに対応した」だけでなく、開発体験の改善（Pythonデバッグ、Graphsの動的制御フロー）やライブラリ性能の大幅向上を含む包括的なアップデートだ。RTX 5090ユーザーは早期に移行する価値がある。

---

## 関連記事

- [RTX 5090 CUDA最適化ガイド](https://zenn.dev/amabito/articles/rtx5090-cuda-optimization) - Blackwell世代の最適化テクニック
- [CUDA最適化入門](https://zenn.dev/amabito/articles/cuda-optimization-basics) - GPU開発の基礎
- [CUDAメモリ管理の罠と対策](https://zenn.dev/amabito/articles/cuda-memory-management) - メモリプール実装
- [RTX 5090 sm_120の実測と移行ガイド](https://zenn.dev/amabito/articles/rtx5090-sm120-migration-guide) - アーキテクチャ変更点と実測

---

## 参考

- [CUDA Toolkit 12.8 Features Archive](https://docs.nvidia.com/cuda/archive/12.8.0/cuda-features-archive/index.html) - 公式機能一覧
- [CUDA 12.8 Release Notes](https://docs.nvidia.com/cuda/archive/12.8.0/cuda-toolkit-release-notes/index.html) - リリースノート
- [NVIDIA Blog: CUDA Toolkit 12.8](https://developer.nvidia.com/blog/cuda-toolkit-12-8-delivers-nvidia-blackwell-support) - 技術ブログ
- [Blackwell Compatibility Guide](https://docs.nvidia.com/cuda/blackwell-compatibility-guide/) - 互換性ガイド
- [cuBLAS 12.9 Performance Blog](https://developer.nvidia.com/blog/boosting-matrix-multiplication-speed-and-flexibility-with-nvidia-cublas-12-9) - cuBLAS性能
- [CUTLASS GitHub](https://github.com/NVIDIA/cutlass) - テンプレートライブラリ

---

ご質問・ご相談はコメント欄へ。
