# 3DGSを商用利用したい人へ：知っておくべきライセンス問題と解決策

## TL;DR

- オリジナル3DGSは**商用利用不可**
- 代替のgsplatは**10倍遅い**
- 自作ラスタライザで**1000FPS**達成

## 3DGSとは

3D Gaussian Splatting（3DGS）は2023年にSIGGRAPHで発表された3D表現手法。写真から高品質な3Dシーンを再構築できる。

不動産のバーチャルツアー、ECの商品3D化、ゲームの背景生成など、ビジネス用途での需要が急増している。

## 問題：商用利用できない

オリジナル実装（diff-gaussian-rasterization）は**商用利用不可**。

```
Gaussian-Splatting License
→ 商用利用にはInria/Max-Planckとの契約が必要
→ 大企業以外は事実上門前払い
```

## 代替の現状

| ラスタライザ | ライセンス | 商用 | 速度 |
|-------------|-----------|------|------|
| diff-gaussian | 独自 | ❌ | 21 it/s |
| gsplat | Apache 2.0 | ✅ | 1.7 it/s |

**gsplatは商用OKだが、10倍以上遅い。**

## 解決策

私はゼロからラスタライザを自作した。

```
HyperRasterizer
├── ライセンス: Apache 2.0（商用OK）
├── 速度: 1M Gaussians @ 1080p = 1000 FPS
└── 学習: 221 it/s（gsplatの130倍）
```

## 技術のポイント

自作で達成した高速化：

1. **Forward-Order Backward** - 逆順計算を順方向に（130倍高速化）
2. **Quad Reduction** - Atomic操作を4分の1に
3. **GPU自動検出** - RTX 5090/4090/3090に最適化
4. **メモリプール** - cudaMallocのオーバーヘッド排除

## 詳細はZennで

実装の詳細、ベンチマーク、商用化ガイドはZennで連載しています。

**無料記事:**
- [HyperRasterizer完全解説](https://zenn.dev/amabito/articles/hyper-rasterizer-zenn)
- [3DGS商用化ガイド](https://zenn.dev/amabito/articles/3dgs-commercial-guide)

**有料記事（実装コード付き）:**
- [ラスタライザ自作ガイド](https://zenn.dev/amabito/articles/3dgs-commercial-guide-paid)

---

建設コンサルタント × 3DGSエンジニア
商用利用可能な3DGS実装を開発中
