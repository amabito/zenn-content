---
title: "3DGSラスタライザ自作30の設計判断：130倍高速化の全記録"
emoji: "🛠️"
type: "tech"
topics: ["3DGS", "CUDA", "GPU", "ラスタライザ", "最適化"]
published: false
---

# 結論から言う

**3D Gaussian Splattingのラスタライザを自作し、130倍の高速化（CPU 1.5秒 → CUDA 11ms）を達成した。** Forward-Order Backward、Quad Reduction、Lazy Backward等の独自最適化を実装。この記事では、設計判断の全記録と失敗から学んだ教訓を公開する。

**対象読者:**
- 3DGSのラスタライザを自作したい人
- CUDA最適化の実践例を知りたい人
- 論文実装の設計判断プロセスに興味がある人

**この記事で得られること:**
- ラスタライザ自作の設計判断30個（成功・失敗含む）
- 130倍高速化の具体的アプローチ
- 避けるべき罠と推奨アプローチ

**注意:** 機密情報（具体的なアルゴリズム・実装コード）は含みません。概念と設計判断のみを扱います。

---

## なぜラスタライザを自作したか

### 既存実装の3つの課題

| 課題 | 詳細 | 影響 |
|------|------|------|
| **ライセンス問題** | オリジナル3DGS（Inria）がNon-Commercial | 商用利用不可 |
| **拡張性の低さ** | モジュール化されていない | カスタマイズ困難 |
| **最適化の余地** | 学術実装（速度より再現性重視） | 本番環境で遅い |

### 目標設定

```
1. Apache 2.0ライセンス（商用利用可能）
2. オリジナル3DGS比で同等以上の速度
3. モジュール設計（プラガブル）
4. RTX 5090 Blackwellへの最適化
```

---

## 設計判断30個

### Phase 1: 基本設計（判断1-10）

#### 判断1: メモリレイアウト（SoA vs AoS）

**選択:** Structure of Arrays（SoA）

```cpp
// ❌ Array of Structures（AoS）
struct Gaussian {
    float3 mean;
    float opacity;
    float3 scale;
};
Gaussian gaussians[N];

// ✅ Structure of Arrays（SoA）
float3 means[N];
float opacities[N];
float3 scales[N];
```

**理由:**

- CUDAのCoalesced Memory Access（連続メモリアクセス）に最適
- 帯域利用効率が2-3倍向上

---

#### 判断2: Tile Size（16x16 vs 32x32）

**選択:** 16x16（初期）→ 可変（最終）

| Tile Size | 共有メモリ | スレッド数 | 速度 |
|-----------|-----------|----------|------|
| **8x8** | 小 | 64 | 遅い（起動オーバーヘッド） |
| **16x16** | 中 | 256 | 標準 |
| **32x32** | 大 | 1024 | 速い（RTX 5090） |

**教訓:** ハードウェア依存。RTX 4090では16x16、RTX 5090では32x32が最適。

---

#### 判断3: Sorting（Radix Sort vs Bitonic Sort）

**選択:** CUB Radix Sort

```cuda
// CUB（NVIDIA公式ライブラリ）
cub::DeviceRadixSort::SortPairs(
    d_keys, d_sorted_keys,
    d_values, d_sorted_values,
    num_items
);
```

**理由:**

- 最適化済み（自作より5-10倍速い）
- メンテナンス不要

**失敗例:** 最初はBitonic Sortを自作 → CUBの3倍遅かった。

---

#### 判断4: Alpha Blending（Forward vs Reverse）

**選択:** Forward Order（前から後ろへ）

```
通常: 遠い → 近い（Reverse Order）
選択: 近い → 遠い（Forward Order）
```

**理由:**

- Early Terminationが容易（不透明度が1に達したら終了）
- Backwardパスで逆順処理が効率的

---

#### 判断5: 球面調和関数（SH）の次数

**選択:** 可変（0次〜3次）

| 次数 | 係数数 | 速度 | 品質 |
|------|--------|------|------|
| **0次** | 1 | 最速 | 低（Lambertian） |
| **1次** | 4 | 速い | 中 |
| **2次** | 9 | 中 | 高 |
| **3次** | 16 | 遅い | 最高 |

**実装:** マクロで切り替え可能に。

---

#### 判断6: メモリプール（Custom vs CUDAデフォルト）

**選択:** カスタムメモリプール

```cuda
// フレーム間でバッファを再利用
class GaussianMemoryPool {
    void* buffers[MAX_FRAMES];
    void* allocate(size_t size);
    void free(void* ptr);
};
```

**効果:** cudaMalloc/cudaFree のオーバーヘッド削減（5-10ms → 0.1ms）。

---

#### 判断7: Precision（FP32 vs FP16）

**選択:** Hybrid（Forward FP32、Backward FP16）

| Stage | Precision | 理由 |
|-------|-----------|------|
| **Forward** | FP32 | 精度重視（色・不透明度計算） |
| **Backward** | FP16 | 速度重視（勾配計算） |

**効果:** 学習速度1.4倍、品質劣化なし。

---

#### 判断8: Gaussian Clipping（球 vs 楕円体）

**選択:** 楕円体（3σ）

```cuda
// 各Gaussianを楕円体としてクリップ
if (mahalanobis_distance(pixel, gaussian) > 3.0) {
    continue;  // 寄与が小さい → スキップ
}
```

**効果:** 不要な計算を30-40%削減。

---

#### 判断9: Backward Pass（Dual Pass vs Single Pass）

**選択:** Dual Pass（通常Forward + Backward用Forward）

```
Forward Pass（レンダリング）: 画像生成
Backward Pass:
  1. Forward再実行（中間値記録）
  2. 逆順で勾配計算
```

**理由:** メモリ使用量削減（中間値を保存しない）。

---

#### 判断10: Tile処理順序（Row-Major vs Hilbert Curve）

**選択:** Row-Major（標準）

```
Tile順序:
  0  1  2  3
  4  5  6  7
  8  9 10 11
```

**失敗例:** Hilbert Curveを試したが、効果なし（並べ替えコストが大きい）。

---

### Phase 2: 高速化（判断11-20）

#### 判断11: Lazy Backward（選択的勾配計算）

**選択:** 導入（重要度<1/512のGaussianをスキップ）

```cuda
// 不透明度が低いGaussianの勾配計算をスキップ
if (gaussian.opacity * weight < 1.0 / 512.0) {
    // 勾配計算スキップ
    // ただしT recoveryとaccum_recは更新
    continue;
}
```

**効果:** Backward Pass 1.2-1.3倍高速化。

---

#### 判断12: Quad Reduction（4画素同時処理）

**選択:** 導入（2x2タイル単位）

```cuda
// 4画素を1スレッドで処理
__global__ void render_quad() {
    float4 colors[4];  // 2x2画素
    // ベクトル命令で並列処理
}
```

**効果:** 1.15-1.2倍高速化（ただし実装複雑）。

---

#### 判断13: Shared Memory Bank Conflict回避

**選択:** パディング追加

```cuda
// ❌ Bank Conflict発生
__shared__ float data[256];

// ✅ パディングで回避
__shared__ float data[256 + 32];  // 32 = warp size
```

**効果:** 5-10%高速化。

---

#### 判断14: Warp Shuffle（スレッド間通信）

**選択:** 導入（Reduction処理）

```cuda
// Warp内でのReduction（共有メモリ不要）
__inline__ __device__
float warp_reduce_sum(float val) {
    for (int offset = 16; offset > 0; offset /= 2)
        val += __shfl_down_sync(0xffffffff, val, offset);
    return val;
}
```

**効果:** Tile内Reduction 2倍高速化。

---

#### 判断15: 動的並列性（Dynamic Parallelism）

**選択:** 不採用

**理由:** オーバーヘッドが大きい（CUDA 12.8でも）。Static Parallelismで十分。

---

#### 判断16: Tensor Core活用（FP16行列演算）

**選択:** 一部導入（SH係数計算）

```cuda
// SH係数の行列演算にTensor Core使用
nvcuda::wmma::fragment<...> a, b, c;
nvcuda::wmma::mma_sync(c, a, b, c);
```

**効果:** SH計算1.3倍高速化（ただし実装複雑）。

---

#### 判断17: Occupancy最適化

**選択:** 共有メモリ使用量を調整

| 共有メモリ | Occupancy | 速度 |
|-----------|----------|------|
| **64 KB** | 50% | 遅い |
| **48 KB** | 75% | 標準 |
| **32 KB** | 100% | **最速** |

**教訓:** Occupancy 100%が常に最速とは限らない。実測必須。

---

#### 判断18: Stream並列実行

**選択:** 導入（複数視点の並列レンダリング）

```cuda
cudaStream_t streams[4];
for (int i = 0; i < 4; i++) {
    render_kernel<<<..., streams[i]>>>(...);
}
```

**効果:** バッチレンダリング1.8倍高速化。

---

#### 判断19: Unified Memory（自動データ転送）

**選択:** 不採用（明示的cudaMemcpyの方が速い）

**理由:** オーバーヘッドとページフォールト。

---

#### 判断20: Persistent Kernels

**選択:** 実験中（未確定）

**アイデア:** カーネルを常駐させ、起動コストを削減。

---

### Phase 3: 商用化対応（判断21-30）

#### 判断21: エラーハンドリング

**選択:** 全CUDAコールをチェック

```cuda
#define CUDA_CHECK(call) \
    do { \
        cudaError_t err = call; \
        if (err != cudaSuccess) { \
            throw std::runtime_error(cudaGetErrorString(err)); \
        } \
    } while(0)
```

---

#### 判断22: APIインターフェース（C++ vs C）

**選択:** C++（ヘッダーオンリー）

```cpp
// シンプルなAPI
GaussianRasterizer rasterizer(width, height);
torch::Tensor output = rasterizer.render(gaussians, camera);
```

---

#### 判断23: ライセンス選択

**選択:** Apache 2.0

**理由:** 商用利用可能、特許リスク低い。

---

#### 判断24: ドキュメント

**選択:** Doxygen + サンプルコード

---

#### 判断25: CI/CD

**選択:** GitHub Actions（テスト自動化）

---

#### 判断26: バージョニング

**選択:** セマンティックバージョニング（v1.0.0形式）

---

#### 判断27: 依存関係最小化

**選択:** PyTorch + CUB のみ

**避けたもの:** OpenCV、Boost等の重い依存。

---

#### 判断28: プラットフォーム対応

**選択:** Linux優先、Windows対応

**課題:** MSVCとのCUDA互換性（PyTorch 2.8.0で回避）。

---

#### 判断29: GPU対応範囲

**選択:** Compute Capability 8.0以降（RTX 3000番台以降）

---

#### 判断30: 公開タイミング

**選択:** 2026年Q2目標（品質確保優先）

---

## パフォーマンス推移

### 各フェーズの速度

| バージョン | 時間（1920x1080） | 倍率（vs CPU） |
|----------|-----------------|---------------|
| **CPUベースライン** | 1500ms | 1倍 |
| **CUDA v1（Naive）** | 150ms | 10倍 |
| **v2（Sorting最適化）** | 50ms | 30倍 |
| **v3（Tile最適化）** | 25ms | 60倍 |
| **v4（Lazy Backward）** | 18ms | 83倍 |
| **v5（Quad Reduction）** | 15ms | 100倍 |
| **v6（現在）** | **11ms** | **136倍** |

---

## 失敗から学んだ教訓

### 失敗1: 過度な最適化

**失敗:** Hilbert Curve、複雑なキャッシング → 効果なし

**教訓:** 実測ベースで判断。理論より実測。

---

### 失敗2: メモリリーク

**失敗:** cudaFree忘れ → 長時間実行でクラッシュ

**教訓:** RAII（Resource Acquisition Is Initialization）パターン必須。

---

### 失敗3: 数値精度問題

**失敗:** FP16で色計算 → 色むら

**教訓:** 重要な計算はFP32。

---

## まとめ

| 項目 | 詳細 |
|------|------|
| **達成した高速化** | 136倍（CPU 1.5秒 → CUDA 11ms） |
| **重要な判断** | SoA、Lazy Backward、Quad Reduction |
| **避けるべき罠** | Unified Memory、Dynamic Parallelism |
| **ライセンス** | Apache 2.0（商用利用可能） |
| **公開予定** | 2026年Q2（目標） |

3DGSラスタライザ自作は、CUDAの実践的学習に最適。論文実装の設計判断プロセスを体験できる。

---

## 関連記事

- [無料] [3DGSラスタライザ比較](https://zenn.dev/amabito/articles/3dgs-rasterizer-comparison) - 既存実装の比較
- [無料] [CUDA最適化入門](https://zenn.dev/amabito/articles/cuda-optimization-basics) - CUDA基礎
- [無料] [HyperSplat学習進化](https://zenn.dev/amabito/articles/hypersplat-training-evolution) - 学習側の最適化
- [有料¥980] [HyperRasterizer実装詳細](https://zenn.dev/amabito/articles/hyper-rasterizer-impl-paid) - 実装ガイド

---

## 参考

- [3D Gaussian Splatting原論文](https://arxiv.org/abs/2308.04079) - SIGGRAPH 2023
- [CUDA C++ Programming Guide](https://docs.nvidia.com/cuda/cuda-c-programming-guide/) - NVIDIA公式
- [CUB Library](https://nvlabs.github.io/cub/) - NVIDIA Collective Algorithms
- [HyperRasterizer GitHub](https://github.com/amabito/hyper-rasterizer) - ソースコード（公開予定）

---

ご質問・ご相談はコメント欄へ。
