# CUDA開発で3日ハマった話：知っておけば防げた罠3選

## はじめに

自作の3DGSラスタライザを開発中、CUDAの罠に何度もハマった。

この記事では、最も時間を溶かした3つの問題を共有する。

## 罠1: first-frame bug（3日間）

### 症状
最初のフレームだけ真っ黒。2フレーム目以降は正常。

### 原因
**cudaMallocはメモリを初期化しない。**

```cuda
float* buffer;
cudaMalloc(&buffer, size);
// ↑ ゴミデータが入っている！
```

### 解決
```cuda
cudaMalloc(&buffer, size);
cudaMemset(buffer, 0, size);  // ← これだけ
```

**たった1行で3日間のバグが解決。**

## 罠2: 73GB問題（1日間）

### 症状
```
Required: 73GB
Available: 32GB
CUDA out of memory
```

### 原因
バッファサイズ推定が過大。安全マージン4倍が掛け合わさって爆発。

### 解決
```cpp
// ハードキャップを設ける
return min(estimated_size, 4ULL * 1024 * 1024 * 1024);
```

## 罠3: Warp Reductionが逆効果（半日）

### 理論
32スレッドで集約してからAtomicすれば、Atomic操作が1/32になるはず。

### 実測（RTX 5090）
- 直接Atomic: 61ms
- Warp Reduction: 400ms

**6.5倍遅くなった。**

### 理由
RTX 5090のAtomicユニットが強力すぎて、集約のオーバーヘッドの方が大きい。

## 教訓

1. **cudaMallocの後はcudaMemset**
2. **サイズ推定にはハードキャップ**
3. **最新GPUでは常識が変わる。実測あるのみ**

## 詳細はZennで

CUDAメモリ管理、RTX 5090最適化、PyTorch CUDA拡張の詳細はZennで連載中。

**無料記事:**
- [CUDAメモリ管理の罠](https://zenn.dev/amabito/articles/cuda-memory-management)
- [RTX 5090 CUDA最適化](https://zenn.dev/amabito/articles/rtx5090-cuda-optimization)
- [PyTorch CUDA拡張](https://zenn.dev/amabito/articles/pytorch-cuda-extension)

**有料記事（実装コード付き）:**
- [メモリプール実装ガイド](https://zenn.dev/amabito/articles/cuda-memory-management-paid)
- [RTX 5090ベンチマーク詳細](https://zenn.dev/amabito/articles/rtx5090-cuda-optimization-paid)

---

建設コンサルタント × 3DGSエンジニア
RTX 5090で3DGSを高速化中
