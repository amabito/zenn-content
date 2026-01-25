---
title: "3DGSを商用利用したい人へ：DGRを超える3713FPSの独自ラスタライザを作った話"
emoji: "🚀"
type: "tech"
topics: ["3dgs", "cuda", "gpu", "computervision", "機械学習"]
published: true
---

# TL;DR

| 項目 | 結果 |
|------|------|
| 速度 | **3,713 FPS** (N=100K) |
| DGR比 | **1.29x高速** |
| ライセンス | Apache 2.0（商用無料） |
| GPU | RTX 5090 (Blackwell) |

**diff-gaussian-rasterization (DGR) を超えました。**

---

# 結論から言う

**3D Gaussian Splatting（3DGS）を商用で使いたいなら、ラスタライザを自作するしかない。**

そして私は作った。**HyperRasterizer**。Apache 2.0ライセンス、商用利用OK、**DGRを1.29x上回る3713FPS**。

この記事では、なぜ自作が必要だったのか、どう実装したのか、そしてどれだけ速くなったのかを解説する。

---

# 3DGSの商用利用、実は詰んでる

## 3DGSとは

2023年にSIGGRAPHで発表された3D表現手法。NeRFより高速で高品質。写真から3Dシーンを再構築できる。

デモを見たことがある人は多いだろう。あの「ぬるぬる動く3D」だ。

## 商用利用の壁

3DGSを使いたい企業は増えている。不動産のバーチャルツアー、ECの商品3D化、ゲームの背景生成...

**しかし、公式実装は商用利用できない。**

```
diff-gaussian-rasterization
├── ライセンス: Gaussian-Splatting License
├── 商用利用: ❌ Inria/Max-Planckとの契約が必要
└── 現実: 大企業以外は門前払い
```

「じゃあ代替品を使えばいいじゃん」

そう思うだろう。私もそう思った。

## 代替品の現実

| ラスタライザ | ライセンス | 商用利用 | 速度 |
|-------------|-----------|---------|------|
| diff-gaussian-rasterization | 独自 | ❌ | 21 it/s |
| gsplat | Apache 2.0 | ✅ | **1.7 it/s** |

**10倍以上遅い。**

gsplatは立派なプロジェクトだ。しかし、実用には速度が足りない。1枚の画像をレンダリングするのに、本家の10倍の時間がかかる。

学習なら数時間が数十時間になる。推論なら60fpsが6fpsになる。

---

# 作るしかなかった

## HyperRasterizer

ゼロから設計した3DGS専用ラスタライザ。

```
HyperRasterizer
├── ライセンス: Apache 2.0
├── 商用利用: ✅ 完全OK
├── Forward: 投影 → ソート → レンダリング
├── Backward: 勾配計算（学習に必須）
└── 速度: 1M Gaussians @ 1080p = 1000 FPS
```

## 最大の難関：Backward Pass

Forward（描画）は簡単だ。3D Gaussianを2Dに投影して、ピクセルごとに色を合成するだけ。

**問題はBackward（勾配計算）だ。**

3DGSの学習には、「この画像を出力するために、各Gaussianのパラメータをどう変えるべきか」を計算する必要がある。これがBackward Pass。

### 従来手法の問題

オリジナル実装は**逆順処理**を採用している。

```
ピクセルの色 = G1 + (1-α1) × G2 + (1-α1)(1-α2) × G3 + ...

逆順で勾配を計算:
T_final = (1-α1)(1-α2)...(1-αN)
T_before = T_final / (1-αN)      ← ここで除算
T_before = T_before / (1-αN-1)   ← また除算
...
```

除算の連鎖。数値的に不安定で、しかも遅い。

### Forward-Order Backward

私は**順方向**で勾配を計算する手法を実装した。

従来の逆順処理とは異なり:
- 除算を使わず乗算のみで計算
- 数値的に安定
- キャッシュ効率が良い（メモリアクセスが順方向）

**結果: 8000ms → 60ms（130倍高速化）**

---

# どうやってDGRを超えたか

## ボトルネック分析

プロファイリングの結果、**ソート処理が全体の60%**を占めていることが判明。

```
preprocess:  10%
count:       15%
sort:        60%  ← ここがボトルネック
forward:     12%
copy:         8%
```

## Hash-based Forward Rendering

グローバルRadix Sortを**空間ハッシュテーブル + タイル内Bitonic Sort**に置換。

- グローバルソート: O(n log n) 全Gaussian
- Hash-based: O(k log k) タイル内のみ (k << n)

## 4つのレンダリングモード

| モード | 品質 | 速度 | 用途 |
|--------|------|------|------|
| SORTED | 同等 | 8.1x | トレーニング |
| WSR | -1~2dB | 7.5x | プレビュー |
| HYBRID | -0.5dB | 4.5x | バランス |

詳細な実装解説は👇の有料記事で公開しています。

https://zenn.dev/amabito/articles/hyper-rasterizer-impl-paid

---

# 技術詳細

## アーキテクチャ

```
preprocessing.cu   3D→2D投影、カリング、球面調和関数評価
      ↓
sorting.cu         CUB Radix Sort（深度順ソート）
      ↓
hash_table.cu      空間ハッシュテーブル（Hash-basedモード）
      ↓
forward.cu         タイルベースレンダリング
      ↓
backward.cu        Forward-Order勾配計算 + Quad Reduction
```

## 最適化テクニック

### 1. 早期終了

```cuda
// 透過率がほぼ0になったら、残りのGaussianをスキップ
if (T < 0.0001f) break;
```

単純だが効果は大きい。画面の大部分は数個のGaussianで決まる。

### 2. ソートビット最適化

深度値のソートに64bitは不要。上位bitだけでソートすれば十分。

```cuda
// 64bit全部ソート → 32bitだけソート
cub::DeviceRadixSort::SortPairs(..., 0, 32);  // 10-20%高速化
```

### 3. Fast Math

```cuda
// 標準math
float g = expf(-0.5f * power);

// Fast math（精度は落ちるが高速）
float g = __expf(-0.5f * power);  // 3-5%高速化
```

RTX 5090のような最新GPUでは、精度を少し犠牲にして速度を稼ぐ選択が有効。

### 4. GPU自動検出

GPU世代（SM番号）を検出し、最適なパラメータを自動選択:
- Blackwell/Ada世代: 大きなバッチサイズ、Fast Math有効
- Ampere世代: 中程度のバッチサイズ
- 旧世代: 控えめな設定

### 5. Quad Reduction

Backward Passでの勾配集約を4スレッドグループで行い、Atomic操作を4分の1に削減。

### 6. メモリプール

フレームごとのcudaMallocオーバーヘッドを排除。適切なbinning推定で1M Gaussiansに対応。

---

# ベンチマーク

RTX 5090（32GB VRAM）での計測結果。

## DGR超え達成 (2026/01/25 更新)

### Full Pipeline比較 (N=100K, 800x600, sh=3)

| モード | 時間 | FPS | DGR比 |
|--------|------|-----|-------|
| Standard | 2.19 ms | 457 | 0.16x |
| **Hash-SORTED** | **0.27 ms** | **3,713** | **1.29x** |
| Hash-WSR | 0.29 ms | 3,413 | 1.19x |
| Hash-HYBRID | 0.48 ms | 2,072 | 0.72x |
| DGR (参考) | 0.35 ms | 2,870 | 1.0x |

### 高速化の内訳

1. **Hash-based Forward**: ソートボトルネック(60%)を削減
2. **32-bit Compact Keys**: メモリ帯域50%削減
3. **Memory Pool**: cudaMallocオーバーヘッド排除(+15%)
4. **Early Termination**: 収束ピクセルの計算スキップ

## Forward Pass（推論）

| Gaussians | 解像度 | FPS | 備考 |
|-----------|--------|-----|------|
| 100K | 800x600 | **3,713** | Hash-SORTED |
| 100K | 1920x1080 | **2,800+** | Hash-SORTED |
| 500K | 1920x1080 | **1,800+** | 実用レベル |
| 1M | 800x600 | **1,153** | メモリプール有効 |
| 1M | 1920x1080 | **1,000** | メモリプール有効 |

## 学習速度比較

| 項目 | diff-gaussian | gsplat | HyperRasterizer |
|------|--------------|--------|-----------------|
| 学習速度 | 21 it/s | 1.7 it/s | **354 it/s** |
| Backward | 速い | 遅い | **130x改善** |
| 商用利用 | ❌ | ✅ | ✅ |
| DGR比 | 1.0x | 0.08x | **1.29x** |

**商用利用可能で、DGRより1.29倍速い。**

---

# 実装済みの最適化

| 最適化 | 効果 | 状態 |
|--------|------|------|
| Forward-Order Backward | 130x高速化 | ✅ 完了 |
| 早期終了 | 10-30%高速化 | ✅ 完了 |
| ソートビット最適化 | 10-20%高速化 | ✅ 完了 |
| Fast Math (__expf) | 3-5%高速化 | ✅ 完了 |
| Lazy SH評価 | 推論15-25%高速化 | ✅ 完了 |
| GPU自動検出 | 最適パラメータ選択 | ✅ 完了 |
| Quad Reduction | Atomic 4x削減 | ✅ 完了 |
| メモリプール | 1M Gaussians対応 | ✅ 完了 |

## 試したが効果がなかったもの

- **Warp Reduction**: 61ms → 400msに悪化。RTX 5090ではAtomic操作が十分高速で、オーバーヘッドの方が大きかった。

---

# 解決した難問

## メモリプールの罠

**問題1: first-frame bug**
- cudaMalloc後のメモリが初期化されていない
- 解決: cudaMemsetでゼロ初期化

**問題2: binning推定の爆発**
- 1M Gaussians @ 1080pで73GBを要求
- 解決: 現実的なカバレッジ推定 + 適切なキャップ設定
- 結果: **0.1 FPS → 1000 FPS**

## Quad Reductionのwarp同期

**問題**: `__shfl_xor_sync`が条件分岐内で呼ばれ、デッドロック
**解決**: shuffle操作を条件分岐外へ移動

---

# オープンソース公開

Apache 2.0ライセンスでGitHubに公開しました。

https://github.com/amabito/hyper-rasterizer

⭐ Star、Issue、PRお待ちしています！

## 今後の予定

- FP8対応（Blackwell Tensor Core活用）
- さらなる最適化

---

# おわりに

3DGSの商用利用は、ライセンス問題で多くの企業が諦めている。

「オープンソースなのに使えない」という矛盾。

HyperRasterizerはその問題を解決する。Apache 2.0で、誰でも自由に商用利用できる。

**技術は、使われてこそ意味がある。**

質問やフィードバックがあればコメントへ。

---

# 関連記事

## 3DGSシリーズ
- **この記事** → HyperRasterizer完全解説
- [【有料】実装詳細ガイド](https://zenn.dev/amabito/articles/hyper-rasterizer-impl-paid) - Forward/Backward実装コード
- [3DGS商用化ガイド](https://zenn.dev/amabito/articles/3dgs-commercial-guide) - ライセンス問題の整理
- [建設現場×3DGS](https://zenn.dev/amabito/articles/construction-3dgs) - 実用事例

## CUDA開発シリーズ
- [RTX 5090 CUDA最適化](https://zenn.dev/amabito/articles/rtx5090-cuda-optimization) - Blackwell世代の最適化
- [CUDAメモリ管理の罠](https://zenn.dev/amabito/articles/cuda-memory-management) - メモリプール実装
- [PyTorch CUDA拡張](https://zenn.dev/amabito/articles/pytorch-cuda-extension) - Windowsビルドの罠

---

# 参考

- [3D Gaussian Splatting (原論文)](https://repo-sam.inria.fr/fungraph/3d-gaussian-splatting/)
- [gsplat](https://github.com/nerfstudio-project/gsplat)
- [FlashGS (CVPR 2025)](https://github.com/InternLandMark/FlashGS)
