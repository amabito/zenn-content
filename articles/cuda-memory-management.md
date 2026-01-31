---
title: "CUDAメモリ管理で3日ハマった話：first-frame bugと73GB問題"
emoji: "🐛"
type: "tech"
topics: ["CUDA", "GPU", "メモリ管理", "デバッグ", "NVIDIA"]
published: true
published_at: "2026-01-09 18:00"
---

# 3日間、真っ黒な画面と戦った

自作の3DGSラスタライザを動かしたら、**最初のフレームだけ真っ黒**になる。

2フレーム目以降は正常。なぜ？

この記事では、CUDAメモリ管理でハマった罠と、その解決策を共有する。

---

# 問題1: first-frame bug

## 症状

```
Frame 0: 真っ黒（radii=0, viewspace=0）
Frame 1: 正常
Frame 2: 正常
...
```

レンダリング自体は動いている（rendered_sum > 0）のに、出力が真っ黒。

## 原因

**cudaMallocはメモリを初期化しない。**

```cuda
float* buffer;
cudaMalloc(&buffer, size);
// buffer の中身は不定！ゴミデータが入っている
```

CPUの`malloc`と同じ。初期化されていないメモリには、GPUキャッシュに残った古いデータが入っている。

## 解決

```cuda
float* buffer;
cudaMalloc(&buffer, size);
cudaMemset(buffer, 0, size);  // ゼロ初期化
```

**たった1行で3日間のバグが解決した。**

---

# 問題2: 73GB問題

## 症状

1M Gaussians @ 1080pを処理しようとしたら、こんなログが出た。

```
Estimating binning buffer size...
Required: 73GB
Available: 32GB
CUDA out of memory
```

32GBのVRAMに73GBを要求している。明らかにおかしい。

## 原因

binning（各タイルに影響するGaussianのリスト）のサイズ推定が過大だった。

```cpp
// 問題のあるコード
size_t estimate_binning_size(int num_gaussians, int num_tiles) {
    // 各Gaussianが25%のタイルに影響すると仮定
    size_t avg_tiles_per_gaussian = num_tiles * 0.25;
    return num_gaussians * avg_tiles_per_gaussian * sizeof(uint64_t);
}
```

1080pのタイル数 = 120 × 68 = 8160
1M Gaussians × 8160 × 0.25 × 8 bytes = **16GB**

...まだ73GBには足りない。他にも問題があった。

## 本当の原因

```cpp
// さらに問題のあるコード
size_t total = num_gaussians * avg_tiles * sizeof(uint64_t);
total += num_gaussians * sizeof(int) * 2;  // keys + values
total += num_tiles * sizeof(int2);          // ranges
total *= 4;  // 安全マージン ← これ！
```

安全マージン4倍が掛け合わさって、推定が爆発していた。

## 解決

```cpp
size_t estimate_binning_size(int num_gaussians, int num_tiles) {
    // 5%タイルカバレッジ推定（現実的な値）
    size_t avg_tiles = num_tiles * 0.05f;

    // 256タイル/Gaussianでキャップ
    avg_tiles = min(avg_tiles, (size_t)256);

    size_t total = num_gaussians * avg_tiles * sizeof(uint64_t);

    // 4GBハードキャップ
    return min(total, 4ULL * 1024 * 1024 * 1024);
}
```

**結果: 0.1 FPS → 1000 FPS**

---

# 教訓

## CUDAメモリ管理のチェックリスト

- [ ] cudaMallocの後にcudaMemset
- [ ] サイズ推定は控えめに
- [ ] ハードキャップを設ける
- [ ] 実際のメモリ使用量をログ出力

## デバッグのコツ

```cuda
// メモリ使用量をログ
size_t free_mem, total_mem;
cudaMemGetInfo(&free_mem, &total_mem);
printf("GPU Memory: %.2f / %.2f GB\n",
       (total_mem - free_mem) / 1e9,
       total_mem / 1e9);
```

---

# 関連記事

## CUDA開発シリーズ
- [RTX 5090 CUDA最適化](https://zenn.dev/amabito/articles/rtx5090-cuda-optimization) - Blackwell世代の最適化
- **この記事** → CUDAメモリ管理の罠
- [PyTorch CUDA拡張](https://zenn.dev/amabito/articles/pytorch-cuda-extension) - Windowsビルドの罠

## 3DGSシリーズ
- [HyperRasterizer完全解説](https://zenn.dev/amabito/articles/hyper-rasterizer-zenn) - 4169FPS達成の独自ラスタライザ
- [3DGS商用化ガイド](https://zenn.dev/amabito/articles/3dgs-commercial-guide) - ライセンス問題の整理
- [建設現場×3DGS](https://zenn.dev/amabito/articles/construction-3dgs) - 実用事例

---

詳細な実装（メモリプール、grow処理）は有料記事で解説しています。

https://zenn.dev/amabito/articles/cuda-memory-management-paid
