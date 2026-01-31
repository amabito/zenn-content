---
title: "RTX 5090 CUDA最適化：知らないと損する5つの新常識"
emoji: "⚡"
type: "tech"
topics: ["CUDA", "GPU", "RTX5090", "Blackwell", "最適化"]
published: true
published_at: "2026-01-19 21:00"
---

# 結論から言う

**RTX 5090では、従来の最適化テクニックが逆効果になることがある。**

「RTX 5090買ったのに速くならない」「Warp Reductionしたら遅くなった」

こんな経験、ありませんか？私はRTX 5090で3DGSラスタライザを開発し、この罠にハマった。

**この記事で得られること:**
- Blackwell世代の5つの新常識
- 従来テクニックが逆効果になる理由
- 実測ベンチマークデータ

---

# Blackwellの特徴

## スペック比較

| 項目 | RTX 4090 (Ada) | RTX 5090 (Blackwell) |
|------|---------------|---------------------|
| SM Version | 89 | 120 |
| CUDA Cores | 16384 | 21760 |
| L2 Cache | 72MB | **96MB** |
| Memory | 24GB GDDR6X | **32GB GDDR7** |
| Memory BW | 1TB/s | 1.8TB/s |

## 何が変わったか

1. **L2キャッシュが巨大** - 96MBはもはやVRAMレベル
2. **Atomicが超高速** - 従来の最適化が逆効果になることも
3. **FP8対応** - Tensor Coreで低精度計算が可能
4. **メモリ帯域幅1.8倍** - データ転送がボトルネックになりにくい

---

# 最適化の基本方針

## 1. GPU世代を検出してパラメータを変える

```cpp
int get_sm_version() {
    int device;
    cudaGetDevice(&device);
    int major, minor;
    cudaDeviceGetAttribute(&major, cudaDevAttrComputeCapabilityMajor, device);
    cudaDeviceGetAttribute(&minor, cudaDevAttrComputeCapabilityMinor, device);
    return major * 10 + minor;
}

void configure_for_gpu() {
    int sm = get_sm_version();

    if (sm >= 120) {
        // Blackwell: 大きなバッチ、Fast Math ON
        batch_size = 512;
        use_fast_math = true;
    } else if (sm >= 89) {
        // Ada: 同様に大きなバッチ
        batch_size = 512;
        use_fast_math = true;
    } else if (sm >= 86) {
        // Ampere: 中程度のバッチ
        batch_size = 256;
        use_fast_math = true;
    } else {
        // 古いGPU: 控えめに
        batch_size = 128;
        use_fast_math = false;
    }
}
```

## 2. Fast Mathを積極的に使う

```cuda
// 標準（精度重視）
float result = expf(x);

// Fast Math（速度重視、Blackwellでは十分な精度）
float result = __expf(x);
```

RTX 5090では、Fast Mathの精度低下が実用上問題になることは少ない。積極的に使う。

## 3. L2キャッシュを意識したデータ配置

96MBのL2キャッシュは、中規模のデータセットなら丸ごと載る。

```cpp
// NG: ランダムアクセス
for (int i = 0; i < N; i++) {
    int idx = random_indices[i];
    process(data[idx]);
}

// OK: 連続アクセス（L2キャッシュが効く）
for (int i = 0; i < N; i++) {
    process(data[i]);
}
```

---

# 実測で分かったこと

## Warp Reductionは逆効果だった

理論上、32スレッドで値を集約してからAtomicすれば、Atomic操作が32分の1になる。

```cuda
// 理論上は良さそう
float warp_sum = warp_reduce(local_value);
if (lane_id == 0) {
    atomicAdd(&global_sum, warp_sum);
}
```

**実測結果（RTX 5090）:**
- 直接Atomic: 61ms
- Warp Reduction: 400ms

**6.5倍遅くなった。**

理由: RTX 5090のAtomicユニットとL2キャッシュが強力すぎて、Warp内で集約するオーバーヘッドの方が大きい。

## Quad Reductionは効果あり

4スレッド（2x2ピクセル）での集約は効果があった。

```cuda
float quad_sum = val;
quad_sum += __shfl_xor_sync(0xFFFFFFFF, quad_sum, 1);
quad_sum += __shfl_xor_sync(0xFFFFFFFF, quad_sum, 2);

if ((threadIdx.x & 3) == 0) {
    atomicAdd(&global_sum, quad_sum);
}
```

**効果: Atomic操作が4分の1に削減**

---

# まとめ

RTX 5090でのCUDA最適化ポイント:

1. **GPU検出して設定を変える** - sm_120以上なら大きなバッチ、Fast Math ON
2. **L2キャッシュを意識** - 96MBを活用、連続アクセス重視
3. **古い最適化を疑う** - Warp Reductionが逆効果になることも
4. **必ず実測** - 理論と実測は違う

**教訓: 最新GPUでは常識が変わる。実測あるのみ。**

---

# 関連記事

## CUDA開発シリーズ
- **この記事** → RTX 5090最適化の基本
- [CUDAメモリ管理の罠](https://zenn.dev/amabito/articles/cuda-memory-management) - メモリプール実装
- [PyTorch CUDA拡張](https://zenn.dev/amabito/articles/pytorch-cuda-extension) - Windowsビルドの罠

## 3DGSシリーズ
- [HyperRasterizer完全解説](https://zenn.dev/amabito/articles/hyper-rasterizer-zenn) - 4169FPS達成の独自ラスタライザ
- [3DGS商用化ガイド](https://zenn.dev/amabito/articles/3dgs-commercial-guide) - ライセンス問題の整理
- [建設現場×3DGS](https://zenn.dev/amabito/articles/construction-3dgs) - 実用事例

---

詳細な実装とベンチマーク結果は有料記事で解説しています。

https://zenn.dev/amabito/articles/rtx5090-cuda-optimization-paid
