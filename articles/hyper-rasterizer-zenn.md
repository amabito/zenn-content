---
title: "3DGSを商用利用したい人へ：130倍高速な独自ラスタライザを作った話"
emoji: "🚀"
type: "tech"
topics: ["3dgs", "cuda", "機械学習", "コンピュータグラフィックス", "gpu"]
published: true
---

# 結論から言う

**3D Gaussian Splatting（3DGS）を商用で使いたいなら、ラスタライザを自作するしかない。**

そして私は作った。**HyperRasterizer**。Apache 2.0ライセンス、商用利用OK、オリジナルより**130倍高速**。

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
└── 速度: 221 it/s（diff-gaussian比 10倍）
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

```
T_before = 1.0
for i = 1 to N:
    // 勾配計算（T_beforeを使用）
    T_before = T_before * (1 - αi)   ← 乗算のみ
```

除算なし。数値的に安定。そしてキャッシュ効率が良い（メモリアクセスが順方向）。

**結果: 8000ms → 60ms（130倍高速化）**

---

# 技術詳細

## アーキテクチャ

```
preprocessing.cu   3D→2D投影、カリング、球面調和関数評価
      ↓
sorting.cu         CUB Radix Sort（深度順ソート）
      ↓
forward.cu         タイルベースレンダリング
      ↓
backward.cu        Forward-Order勾配計算
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

```cpp
// GPU世代に応じて最適なパラメータを選択
if (sm >= 120) {      // Blackwell (RTX 5090)
    batch_size = 512;
    use_fast_math = true;
} else if (sm >= 89) { // Ada (RTX 4090)
    batch_size = 512;
    use_fast_math = true;
} else if (sm >= 86) { // Ampere (RTX 3090)
    batch_size = 256;
    use_fast_math = true;
}
```

---

# ベンチマーク

RTX 5090（32GB VRAM）での計測結果。

| 項目 | diff-gaussian | gsplat | HyperRasterizer |
|------|--------------|--------|-----------------|
| 学習速度 | 21 it/s | 1.7 it/s | **221 it/s** |
| Forward | 速い | 遅い | 速い |
| Backward | 速い | 遅い | **130x改善** |
| 商用利用 | ❌ | ✅ | ✅ |

**商用利用可能で、gsplatより130倍速い。**

---

# まだやることはある

## 実装済みの最適化

| 最適化 | 効果 | 状態 |
|--------|------|------|
| Forward-Order Backward | 130x高速化 | ✅ 完了 |
| 早期終了 | 10-30%高速化 | ✅ 完了 |
| ソートビット最適化 | 10-20%高速化 | ✅ 完了 |
| Fast Math (__expf) | 3-5%高速化 | ✅ 完了 |
| Lazy SH評価 | 推論15-25%高速化 | ✅ 完了 |
| GPU自動検出 | 最適パラメータ選択 | ✅ 完了 |

## 試したが効果がなかったもの

- **Warp Reduction**: 61ms → 400msに悪化。RTX 5090ではAtomic操作が十分高速で、オーバーヘッドの方が大きかった。

## 解決済みの課題

1. **メモリプール first-frame bug**: cudaMalloc後のメモリ未初期化が原因。cudaMemsetでゼロ初期化して解決。

## 未解決の課題

1. **Quad Reduction**: warp同期問題で無効化中。

## 今後の予定

- FP8対応（Blackwell Tensor Core活用）
- オープンソース公開

---

# おわりに

3DGSの商用利用は、ライセンス問題で多くの企業が諦めている。

「オープンソースなのに使えない」という矛盾。

HyperRasterizerはその問題を解決する。Apache 2.0で、誰でも自由に商用利用できる。

**技術は、使われてこそ意味がある。**

質問やフィードバックがあればコメントへ。

---

# 参考

- [3D Gaussian Splatting (原論文)](https://repo-sam.inria.fr/fungraph/3d-gaussian-splatting/)
- [gsplat](https://github.com/nerfstudio-project/gsplat)
- [FlashGS (CVPR 2025)](https://github.com/InternLandMark/FlashGS)
