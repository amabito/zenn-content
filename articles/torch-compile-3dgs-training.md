---
title: "torch.compileで3DGS学習を高速化する実践テクニック"
emoji: "🚀"
type: "tech"
topics: ["PyTorch", "torchcompile", "3DGS", "CUDA", "最適化"]
published: true
---

# 結論から言う

**torch.compileは3DGS学習の「一部」に効く。カスタムCUDAカーネル（ラスタライザ）はcompile対象外だが、損失計算・SH評価・密度化ロジックの周辺処理を最適化することで、全体のスループットを改善できる。** 適用箇所の選定とgraph break回避が鍵。

**対象読者:**
- 3D Gaussian Splattingの学習を高速化したい人
- torch.compileを実プロジェクトに導入したい人
- PyTorch 2.x系のコンパイラスタックに興味がある人

**この記事で得られること:**
- TorchDynamo + TorchInductorの仕組み
- 3DGS学習のどの部分にcompileが効くか（効かないか）
- graph breakの検出と回避方法
- 動的形状（解像度変化）での再コンパイル回避
- compile有無でのスループット比較

---

## torch.compileの現在地

PyTorch 2.0で導入された`torch.compile`は、2.x系を通じて成熟してきた。PyTorch 2.10の時点で、多くのモデルアーキテクチャで安定した高速化を実現している。

### コンパイラスタックの全体像

```
Python コード
  ↓
TorchDynamo（CPython Frame Evaluation API）
  ↓ グラフキャプチャ
FX Graph（中間表現）
  ↓ AOT Autograd（Forward + Backward）
PrimTorch（~250プリミティブに正規化）
  ↓
TorchInductor（コード生成）
  ├── GPU → Tritonカーネル
  └── CPU → C++/OpenMP
```

### TorchDynamoの仕組み

TorchDynamoはCPythonのFrame Evaluation API（PEP 523）を使い、Pythonバイトコードを実行直前に動的に書き換える。

1. **バイトコード解析**: Pythonフレームのバイトコードをシンボリック評価
2. **FX Graphの構築**: PyTorch操作をFXグラフとしてキャプチャ
3. **ガードの生成**: 再コンパイルが必要な条件（形状変化等）を記録
4. **コンパイル済みコードの挿入**: TorchInductorが生成したコードで置き換え

### TorchInductorの役割

FXグラフを受け取り、GPU向けにはTritonカーネル、CPU向けにはC++/OpenMPコードを生成する。Pythonで記述されたdefine-by-runのループレベルIRを使い、フュージョンやメモリ最適化を自動で行う。

---

## 3DGS学習への適用：何にcompileが効くか

3DGS学習パイプラインを分解して、compile適用可能性を整理する。

### 学習パイプラインの構成

```
[3DGS学習ループ]
├── 1. カメラ選択・データ読み込み       → compile不可（I/O）
├── 2. SH係数 → RGB変換              → compile可能
├── 3. Gaussian投影（3D→2D）          → ラスタライザ依存
├── 4. ラスタライズ（Forward Pass）     → compile不可（CUDAカーネル）
├── 5. 損失計算（L1 + SSIM）           → compile可能
├── 6. 逆伝播                         → 部分的にcompile可能
├── 7. オプティマイザステップ            → compile可能
├── 8. 密度化（Densification）          → graph breakしやすい
└── 9. プルーニング                     → graph breakしやすい
```

### compile可能な部分

**損失計算（SSIM、Perceptual Loss）:**

```python
@torch.compile
def compute_loss(rendered, gt_image, lambda_dssim=0.2):
    l1_loss = torch.abs(rendered - gt_image).mean()
    ssim_val = ssim(rendered, gt_image)
    return (1.0 - lambda_dssim) * l1_loss + lambda_dssim * (1.0 - ssim_val)
```

SSIMはConv2d + テンソル演算の組み合わせであり、TorchInductorによるフュージョンが効きやすい。

**SH（Spherical Harmonics）評価:**

```python
@torch.compile
def eval_sh(deg, sh_coeffs, dirs):
    """球面調和関数の評価 — 純粋なテンソル演算"""
    result = sh_coeffs[:, 0] * 0.28209479177387814
    if deg > 0:
        x, y, z = dirs[:, 0:1], dirs[:, 1:2], dirs[:, 2:3]
        result = result + sh_coeffs[:, 1] * (-0.4886025119029199 * y)
        result = result + sh_coeffs[:, 2] * (0.4886025119029199 * z)
        result = result + sh_coeffs[:, 3] * (-0.4886025119029199 * x)
        # ... 高次項の評価
    return result
```

### compile不可の部分

**カスタムCUDAラスタライザ:**

diff-gaussian-rasterization、gsplat、HyperRasterizerなどのカスタムCUDAカーネルは、TorchDynamoのグラフキャプチャ対象外だ。C拡張モジュールの内部はDynamoから不可視であり、ガードの生成もできない。

```python
# これはcompileに含めない
# CUDAカーネルの呼び出しは不透明
rendered = rasterizer.forward(means3d, scales, quats, colors, opacities, ...)
```

**密度化ロジック:**

密度化には条件分岐とテンソルの動的操作（マスキング、追加、削除）が含まれる。

```python
# graph breakの原因になりやすいコード
if iteration > densify_from and iteration % densify_interval == 0:
    grads = gaussians.xyz_gradient_accum / gaussians.denom
    grads[grads.isnan()] = 0.0

    # 条件に基づくGaussianの分裂・クローン
    mask = grads.squeeze() >= grad_threshold   # データ依存の条件分岐
    selected = gaussians.get_xyz[mask]          # 動的サイズ
    # ...
```

---

## graph breakの検出と対策

### graph breakの検出方法

**方法1: fullgraph=Trueでエラーを出す**

```python
# graph breakがあればエラーで停止
compiled_fn = torch.compile(my_function, fullgraph=True)
```

`fullgraph=True`を指定すると、関数全体を単一のグラフとしてキャプチャできない場合にエラーが発生する。開発中にgraph breakの箇所を特定するのに有用。

**方法2: ログで確認**

```bash
TORCH_LOGS="graph_breaks" python train.py
```

graph breakの理由とコード位置がログに出力される。

**方法3: torch._dynamo.explainで詳細分析**

```python
explanation = torch._dynamo.explain(my_function)(input_tensor)
print(f"Graph breaks: {explanation.graph_break_count}")
print(f"Reasons: {explanation.break_reasons}")
```

### graph break回避のパターン

| 原因 | 回避策 |
|------|--------|
| `tensor.item()` | バッチ終了後にまとめて取得 |
| `print(tensor)` | `torch._dynamo.config.reorderable_logging_functions`を設定 |
| データ依存の条件分岐 | compile対象から除外 |
| C拡張呼び出し | compile対象から除外 |
| 動的リスト操作 | 事前にサイズを確定 |

---

## 再コンパイル問題：動的形状への対処

### 問題

3DGS学習では、学習画像の解像度が異なる場合がある。解像度が変わるたびにtorch.compileが再コンパイルを実行し、オーバーヘッドが発生する。

```
画像1 (800x600)   → コンパイル（初回、数秒〜数十秒）
画像2 (1920x1080) → 再コンパイル
画像3 (800x600)   → キャッシュヒット
画像4 (1280x720)  → 再コンパイル
...
```

再コンパイル回数が`torch._dynamo.config.recompile_limit`（デフォルト8）に達すると、以降はeagerモードにフォールバックする。

### 解決策1: dynamic=Trueで動的形状を有効化

```python
@torch.compile(dynamic=True)
def compute_loss(rendered, gt_image):
    l1_loss = torch.abs(rendered - gt_image).mean()
    ssim_val = ssim(rendered, gt_image)
    return 0.8 * l1_loss + 0.2 * (1.0 - ssim_val)
```

`dynamic=True`を指定すると、形状を動的に扱うカーネルが生成される。再コンパイルは発生しないが、静的形状よりもわずかに遅い場合がある。

### 解決策2: 解像度を統一する

```python
# 学習画像をリサイズして解像度を統一
target_resolution = (800, 600)
gt_image = F.interpolate(gt_image, size=target_resolution, mode="bilinear")
```

解像度を統一すれば再コンパイルは発生しない。ただし、元画像の解像度情報が失われる。

### 解決策3: mark_dynamicで特定次元を動的に

```python
# H, W次元だけ動的にする
torch._dynamo.mark_dynamic(rendered, 2)  # H
torch._dynamo.mark_dynamic(rendered, 3)  # W
```

特定の次元だけを動的にすることで、不要な再コンパイルを抑制しつつ、静的次元の最適化を維持する。

---

## MX-FP8 / MX-FP4：Blackwellテンソルコア向けMixed Precision

### 3DGS学習での適用

Blackwellテンソルコアは、MX-FP8/MX-FP4のブロックスケーリングフォーマットに対応している。3DGS学習では主に以下の場面で活用できる。

| 処理 | 精度 | 効果 |
|------|------|------|
| SH評価の行列演算 | MX-FP8 | メモリ帯域50%削減 |
| SSIM計算のConv2d | MX-FP8 | スループット向上 |
| Perceptual Lossの特徴抽出 | MX-FP8 | VRAM削減 |

### PyTorchでの設定

```python
# AMP（Automatic Mixed Precision）との併用
with torch.autocast(device_type="cuda", dtype=torch.float8_e4m3fn):
    loss = compute_loss(rendered, gt_image)

# またはtorch.compile + AMPの組み合わせ
@torch.compile
def compute_loss_amp(rendered, gt_image):
    with torch.autocast(device_type="cuda", dtype=torch.float8_e4m3fn):
        l1_loss = torch.abs(rendered - gt_image).mean()
        ssim_val = ssim(rendered, gt_image)
    return 0.8 * l1_loss + 0.2 * (1.0 - ssim_val)
```

注意: Gaussianのパラメータ（位置、スケール、クォータニオン）はFP32を維持すべき。低精度にすると幾何学的な品質が劣化する。

---

## 実測：compile有無でのスループット比較

RTX 5090（sm_120）、PyTorch 2.8.0+cu128で計測。

### テスト条件

```
シーン: Mip-NeRF 360 bicycle
Gaussians: ~500K
解像度: 1920x1080
ラスタライザ: HyperRasterizer
学習: 30,000 iterations
```

### 結果

| 構成 | スループット (it/s) | 改善率 |
|------|-------------------|--------|
| ベースライン（compileなし） | 18.2 | - |
| 損失計算のみcompile | 19.5 | +7.1% |
| 損失計算 + SH評価 compile | 20.1 | +10.4% |
| 上記 + dynamic=True | 19.8 | +8.8% |
| 上記 + AMP (FP16) | 21.3 | +17.0% |

### 分析

- **損失計算のcompile**: SSIMのConv2d演算がフュージョンされ、安定した改善
- **SH評価のcompile**: テンソル演算のフュージョンで追加の改善
- **dynamic=True**: 解像度統一の場合はわずかにオーバーヘッド
- **AMP併用**: compile + AMPの組み合わせが最も効果的

全体の17%高速化のうち、compileが約10%、AMPが約7%を占める。ラスタライザ（全体の50%以上を占める）がcompile対象外であることを考えると、compile可能な部分に対しては20%以上の高速化を達成している。

---

## ベストプラクティス

### fullgraph vs 部分compile

```python
# 推奨: 部分compile（compile可能な関数だけを個別にcompile）
@torch.compile
def compute_loss(rendered, gt_image):
    ...

@torch.compile
def eval_sh(deg, sh_coeffs, dirs):
    ...

# 非推奨: 学習ループ全体をcompile（graph breakが多すぎる）
# @torch.compile  ← CUDAカーネル呼び出しでbreak
# def train_step(gaussians, camera, gt_image):
#     ...
```

### Warmupの扱い

```python
# 最初の数イテレーションはcompileのオーバーヘッドがある
for iteration in range(30000):
    if iteration == 0:
        print("初回イテレーションはコンパイルのため遅い（数秒〜数十秒）")

    rendered = rasterizer.forward(...)
    loss = compute_loss(rendered, gt_image)  # compileはここで発火
    loss.backward()
```

初回コンパイルに数秒〜数十秒かかる。学習が30,000イテレーション以上であれば、warmupのコストは無視できる。

### コンパイルキャッシュ

```python
# キャッシュを有効化（デフォルトで有効）
import torch._inductor.config
torch._inductor.config.fx_graph_cache = True

# キャッシュディレクトリの指定
import os
os.environ["TORCHINDUCTOR_CACHE_DIR"] = "/tmp/torch_compile_cache"
```

キャッシュが有効であれば、2回目以降の起動でコンパイル時間がスキップされる。

### torch.compile適用のチェックリスト

```
1. [ ] compile対象を特定（CUDAカーネル呼び出しを含まない関数）
2. [ ] fullgraph=Trueでgraph breakを検出
3. [ ] graph breakの原因を修正 or 対象から除外
4. [ ] dynamic=True/False/Noneの選択
5. [ ] warmupを考慮したベンチマーク
6. [ ] キャッシュの有効化を確認
```

---

## まとめ

| 項目 | 詳細 |
|------|------|
| **compileが効く部分** | 損失計算（SSIM等）、SH評価、オプティマイザステップ |
| **compileが効かない部分** | CUDAラスタライザ、密度化ロジック、I/O |
| **主な障壁** | graph break（C拡張、データ依存分岐）、再コンパイル（動的形状） |
| **実測改善** | compile単体で+10%、AMP併用で+17% |
| **推奨戦略** | 部分compile（fullgraphではなく関数単位で適用） |

torch.compileは3DGS学習の銀の弾丸ではないが、compile可能な部分に正しく適用すれば確実にスループットを改善できる。ラスタライザの高速化はCUDAカーネルの最適化で行い、周辺処理の高速化はtorch.compileで行う。この組み合わせが現時点での最適戦略だ。

---

## 関連記事

- [PyTorch CUDA拡張の作り方](https://zenn.dev/amabito/articles/pytorch-cuda-extension) - カスタムCUDA拡張の実装
- [CUDA最適化入門](https://zenn.dev/amabito/articles/cuda-optimization-basics) - GPU開発の基礎
- [RTX 5090 CUDA最適化ガイド](https://zenn.dev/amabito/articles/rtx5090-cuda-optimization) - Blackwell世代の最適化
- [HyperSplat開発記録](https://zenn.dev/amabito/articles/hypersplat-training-evolution) - 3DGS学習フレームワークの進化

---

## 参考

- [torch.compile ドキュメント（PyTorch 2.10）](https://docs.pytorch.org/docs/stable/generated/torch.compile.html) - 公式API
- [TorchDynamo Overview](https://docs.pytorch.org/docs/stable/torch.compiler_dynamo_overview.html) - Dynamoの仕組み
- [torch.compile チュートリアル](https://docs.pytorch.org/tutorials/intermediate/torch_compile_tutorial.html) - 入門ガイド
- [Common Graph Breaks](https://docs.pytorch.org/docs/stable/compile/programming_model.common_graph_breaks.html) - graph breakの一覧
- [State of torch.compile for Training（2025年8月）](https://blog.ezyang.com/2025/08/state-of-torch-compile-august-2025/) - 現状分析
- [How does torch.compile work?（UW PLSE）](https://uwplse.org/2025/04/28/torchdynamo.html) - 内部実装の解説
- [gsplat: An Open-Source Library for Gaussian Splatting](https://arxiv.org/abs/2409.06765) - gsplat論文

---

ご質問・ご相談はコメント欄へ。
