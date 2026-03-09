---
title: "3DGSは商用利用できない？ライセンス問題と3つの解決策"
emoji: "💼"
type: "tech"
topics: ["3DGS", "ライセンス", "OSS", "商用利用"]
published: false
---

# 結論から言う

**3DGS公式実装は商用利用できない。でも、合法的に使う方法は3つある。**

「3DGSすごい！うちのサービスに使おう！」→「えっ、ライセンスが...」

この経験、ありませんか？私も同じ壁にぶつかった。

**この記事で得られること:**
- 3DGSライセンス問題の全体像
- 商用利用可能な3つの選択肢
- それぞれのメリット・デメリット

---

# ライセンス問題の整理

## オリジナル実装

```
gaussian-splatting (Inria/Max-Planck)
├── diff-gaussian-rasterization
└── ライセンス: Gaussian-Splatting License
```

**商用利用: 要契約。大企業以外は事実上不可。**

ライセンス条文より:
> "For commercial use, please contact Inria and Max-Planck..."

## 代替実装の比較

| 実装 | ライセンス | 商用利用 | 速度 | 備考 |
|------|-----------|---------|------|------|
| diff-gaussian-rasterization | 独自 | ❌ | 速い | 公式 |
| gsplat | Apache 2.0 | ✅ | 遅い | nerfstudio |
| taichi-splatting | MIT | ✅ | 中 | Taichi依存 |
| 3DGS.cpp | MIT | ✅ | 中 | CPU推論可 |

---

# 選択肢

## 選択肢1: gsplatを使う

**メリット:**
- すぐ使える
- Apache 2.0で完全に商用OK
- nerfstudioエコシステム

**デメリット:**
- **10倍以上遅い**（1.7 it/s vs 21 it/s）
- JITコンパイルで初回が重い

```bash
pip install gsplat
```

## 選択肢2: Inriaと契約

**メリット:**
- 公式実装が使える
- サポートあり

**デメリット:**
- **費用が高い**（数百万円〜）
- 契約交渉に時間がかかる
- スタートアップには非現実的

## 選択肢3: 自作する

**メリット:**
- 完全にコントロール可能
- 好きなライセンスで公開可能
- 最適化の自由度

**デメリット:**
- **開発コスト**
- CUDAの深い知識が必要

---

# 私が選んだ道: 自作

gsplatは遅すぎる。Inriaとの契約は高すぎる。

**ならば自分で作る。**

## HyperRasterizer

```
HyperRasterizer
├── ライセンス: Apache 2.0
├── 商用利用: ✅ 完全OK
├── 速度: 1M Gaussians @ 1080p = 1000 FPS
└── 学習: 221 it/s（gsplatの130倍）
```

---

# 自作への道

## 必要な知識

1. **CUDAプログラミング** - カーネル実装、メモリ管理
2. **コンピュータグラフィックス** - ラスタライズ、α-blending
3. **機械学習** - Backward Pass、勾配計算
4. **PyTorch拡張** - C++/CUDAバインディング

## 実装のロードマップ

```
Phase 1: Forward Pass（2週間）
├── 3D→2D投影
├── タイルベースソート
└── α-blendingレンダリング

Phase 2: Backward Pass（3週間）
├── 色への勾配
├── 位置/スケールへの勾配
└── 共分散への勾配

Phase 3: 最適化（2週間）
├── メモリプール
├── 早期終了
└── GPU世代別チューニング
```

---

# Apache 2.0で公開するには

## 手順

1. **LICENSEファイルを追加**

```
Copyright 2026 Your Name

Licensed under the Apache License, Version 2.0 (the "License");
...
```

2. **ソースファイルにヘッダー追加**（推奨）

```cpp
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Your Name
```

3. **READMEにライセンス明記**

```markdown
## License

This project is licensed under the Apache License 2.0.
See [LICENSE](LICENSE) for details.
```

## 注意点

- **依存ライブラリのライセンス確認** - Apache 2.0互換か？
- **特許条項** - Apache 2.0には特許付与条項がある
- **商標** - Apache 2.0は商標権を付与しない

---

# 結論

3DGS商用化の現実的な選択肢:

| 状況 | 推奨 |
|------|------|
| すぐ使いたい、速度は妥協 | gsplat |
| 大企業、予算あり | Inria契約 |
| スタートアップ、速度重視 | **自作** |

**技術力があるなら、自作が最もコスパが良い。**

---

# 関連記事

## 3DGSシリーズ
- [HyperRasterizer完全解説](https://zenn.dev/amabito/articles/hyper-rasterizer-zenn) - 4169FPS達成の独自ラスタライザ
- **この記事** → 商用化ガイド（ライセンス問題）
- [建設現場×3DGS](https://zenn.dev/amabito/articles/construction-3dgs) - 実用事例

## CUDA開発シリーズ
- [RTX 5090 CUDA最適化](https://zenn.dev/amabito/articles/rtx5090-cuda-optimization) - Blackwell世代の最適化
- [CUDAメモリ管理の罠](https://zenn.dev/amabito/articles/cuda-memory-management) - メモリプール実装
- [PyTorch CUDA拡張](https://zenn.dev/amabito/articles/pytorch-cuda-extension) - Windowsビルドの罠

---

詳細な自作ガイド（Forward/Backward実装）は有料記事で解説しています。

https://zenn.dev/amabito/articles/3dgs-commercial-guide-paid
