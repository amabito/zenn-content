---
title: "CUDA最適化入門：GPUプログラミングで10倍速くする基本テクニック"
emoji: "⚡"
type: "tech"
topics: ["cuda", "gpu", "高速化", "機械学習", "並列処理"]
published: true
---

# 結論から言う

**CUDAの基本を押さえるだけで、10倍以上の高速化は当たり前に達成できる。**

機械学習、画像処理、科学計算...GPUを使うすべての開発者に向けて、CUDA最適化の基本を解説する。

---

# なぜCUDA最適化が必要か

## CPUとGPUの違い

| 項目 | CPU | GPU |
|------|-----|-----|
| コア数 | 8〜64 | **数千〜数万** |
| 得意な処理 | 複雑な分岐 | **単純な並列処理** |
| メモリ帯域 | 50GB/s | **900GB/s以上** |

## 最適化しないとどうなるか

```
最適化前: 100秒
基本的な最適化後: 10秒（10倍高速化）
本格的な最適化後: 1秒（100倍高速化）
```

**「動く」と「速い」は全く別の話。**

---

# 最適化の基本原則

## 原則1: 並列度を最大化する

```cuda
// NG: 1スレッドで全部処理
__global__ void bad_kernel(float* data, int N) {
    for (int i = 0; i < N; i++) {
        data[i] = data[i] * 2.0f;
    }
}

// OK: 各要素を別スレッドで処理
__global__ void good_kernel(float* data, int N) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < N) {
        data[i] = data[i] * 2.0f;
    }
}
```

## 原則2: メモリアクセスを最適化する

```cuda
// NG: 飛び飛びアクセス（ストライドアクセス）
data[threadIdx.x * stride]  // キャッシュ効率悪い

// OK: 連続アクセス（コアレスアクセス）
data[threadIdx.x]  // キャッシュ効率良い
```

## 原則3: 分岐を減らす

```cuda
// NG: warp内で分岐が発生
if (threadIdx.x % 2 == 0) {
    // 偶数スレッドの処理
} else {
    // 奇数スレッドの処理
}

// OK: 全スレッドが同じ処理
float factor = (threadIdx.x % 2 == 0) ? 1.0f : 2.0f;
data[i] = data[i] * factor;
```

---

# 実践テクニック5選

## テクニック1: 共有メモリの活用

```cuda
__shared__ float shared_data[256];

// グローバルメモリから共有メモリにロード
shared_data[threadIdx.x] = global_data[idx];
__syncthreads();

// 共有メモリ内で計算（高速）
float result = shared_data[threadIdx.x] + shared_data[threadIdx.x + 1];
```

**効果: 10〜100倍のメモリアクセス高速化**

## テクニック2: メモリコアレッシング

```cuda
// 構造体配列（AoS）→ 配列構造体（SoA）に変換

// NG: AoS（メモリアクセスが飛び飛び）
struct Particle { float x, y, z; };
Particle particles[N];
particles[i].x = ...;

// OK: SoA（メモリアクセスが連続）
float x[N], y[N], z[N];
x[i] = ...;
```

**効果: 2〜10倍の高速化**

## テクニック3: ストリーム並列化

```cuda
cudaStream_t stream1, stream2;
cudaStreamCreate(&stream1);
cudaStreamCreate(&stream2);

// 2つのカーネルを並列実行
kernel1<<<grid, block, 0, stream1>>>(data1);
kernel2<<<grid, block, 0, stream2>>>(data2);
```

**効果: GPU使用率向上、1.5〜2倍高速化**

## テクニック4: 非同期転送

```cuda
// ページロックメモリを使用
cudaMallocHost(&host_data, size);

// 非同期転送
cudaMemcpyAsync(device_data, host_data, size,
                cudaMemcpyHostToDevice, stream);

// 転送中に別の処理を実行
kernel<<<grid, block, 0, stream>>>(other_data);
```

**効果: 転送と計算のオーバーラップ**

## テクニック5: 占有率の最適化

```cuda
// レジスタ使用量を制限
__launch_bounds__(256, 4)  // 最大256スレッド、最低4ブロック/SM
__global__ void optimized_kernel(...) {
    // ...
}
```

**効果: SM稼働率向上、10〜30%高速化**

---

# よくある間違い

## 間違い1: cudaMallocの乱用

```cuda
// NG: 毎回アロケート
for (int i = 0; i < 1000; i++) {
    cudaMalloc(&buffer, size);  // 遅い！
    kernel<<<...>>>(buffer);
    cudaFree(buffer);
}

// OK: 事前アロケート
cudaMalloc(&buffer, size);
for (int i = 0; i < 1000; i++) {
    kernel<<<...>>>(buffer);
}
cudaFree(buffer);
```

## 間違い2: 不要な同期

```cuda
// NG: 毎回同期
for (int i = 0; i < 1000; i++) {
    kernel<<<...>>>();
    cudaDeviceSynchronize();  // 遅い！
}

// OK: 最後だけ同期
for (int i = 0; i < 1000; i++) {
    kernel<<<...>>>();
}
cudaDeviceSynchronize();
```

## 間違い3: ブロックサイズの不適切な設定

```cuda
// NG: 32の倍数でない
kernel<<<N/100, 100>>>();  // warpが無駄に

// OK: 32の倍数（256が一般的）
kernel<<<(N+255)/256, 256>>>();
```

---

# プロファイリング

## Nsight Computeの使い方

```bash
# プロファイリング実行
ncu --set full ./my_program

# 主要メトリクス
# - SM Throughput: 計算効率
# - Memory Throughput: メモリ効率
# - Occupancy: 占有率
```

## ボトルネック特定

| メトリクス | 低い場合の原因 |
|-----------|---------------|
| SM Throughput | 分岐が多い、レジスタ不足 |
| Memory Throughput | コアレッシング不足 |
| Occupancy | ブロックサイズ不適切 |

---

# GPU世代別の最適化

## RTX 5090 (Blackwell)

```
- L2キャッシュ: 96MB（大容量）
- Tensor Core: FP8対応
- 推奨: 大きなバッチサイズ、FP8活用
```

## RTX 4090 (Ada Lovelace)

```
- L2キャッシュ: 72MB
- Tensor Core: FP8対応
- 推奨: Tensor Core活用
```

## RTX 3090 (Ampere)

```
- L2キャッシュ: 6MB
- 推奨: 共有メモリ活用
```

---

# チェックリスト

| # | 項目 | 確認 |
|---|------|------|
| 1 | 並列度は十分か（数万スレッド以上） | □ |
| 2 | メモリアクセスはコアレスか | □ |
| 3 | 共有メモリを活用しているか | □ |
| 4 | 不要な同期を削除したか | □ |
| 5 | ブロックサイズは32の倍数か | □ |
| 6 | プロファイリングで確認したか | □ |

---

# まとめ

| 原則 | 内容 |
|------|------|
| 並列度最大化 | 数万スレッドを起動 |
| メモリ最適化 | コアレッシング、共有メモリ |
| 分岐削減 | warp divergence回避 |
| 同期削減 | 不要なsynchronize削除 |
| プロファイリング | 推測ではなく測定 |

**「まず測定、次に最適化」が鉄則。**

---

# 関連記事

## CUDA開発シリーズ
- [RTX 5090 CUDA最適化](https://zenn.dev/amabito/articles/rtx5090-cuda-optimization) - 最新GPU対応
- [CUDAメモリ管理の罠](https://zenn.dev/amabito/articles/cuda-memory-management) - メモリプール実装
- [CUDA warp同期の罠](https://zenn.dev/amabito/articles/cuda-warp-sync-trap) - デッドロック回避

## 3DGSシリーズ
- [HyperRasterizer完全解説](https://zenn.dev/amabito/articles/hyper-rasterizer-zenn) - 4169FPS達成の技術

---

質問はコメント欄へ。
