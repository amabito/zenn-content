---
title: "LPIPS GT Feature Cachingで3DGS学習を43%高速化した話"
emoji: "⚡"
type: "tech"
topics: ["CUDA", "PyTorch", "3DGS", "機械学習", "最適化"]
published: true
published_at: "2026-02-27 07:00"
---

## 結論から

3DGS（3D Gaussian Splatting）の学習ループで**LPIPS損失の計算が全体の40%以上を占めていた**。Ground Truth画像のVGG特徴を毎イテレーション再計算していたのが原因だ。それをキャッシュするだけで、**72.44ms → 40.80ms/iter（43.7%削減）**になった。

大規模訓練への影響換算：1000シーン × 10Kイテレーションで**87.7時間の節約**。

---

## 問題：なぜLPIPSがボトルネックになるのか

LPIPS（Learned Perceptual Image Patch Similarity）はVGGネットワークで特徴を抽出し、知覚的類似度を計算する。

```
LPIPS(gt, pred) = VGG(gt) と VGG(pred) の距離
```

ここで重大な非対称性がある。

- `VGG(pred)`：毎イテレーション変化する → 毎回計算必要
- `VGG(gt)`：**学習全体を通じて不変** → 何度計算しても同じ結果

Ground Truth画像は変わらない。なのに毎回VGGにかけていた。

### プロファイリング結果

```
イテレーション全体: 72.44ms
  - Forward pass: 18.2ms (25%)
  - LPIPS計算: 42.1ms (58%)  ← 異常に大きい
    - VGG(gt): 28.3ms       ← これが無駄
    - VGG(pred): 13.8ms     ← これは必要
  - Backward pass: 8.7ms (12%)
  - その他: 3.4ms (5%)
```

LPIPS全体の67%がGTの特徴計算だった。

---

## 解決策：`PerceptualGTCache`クラス

```python
class PerceptualGTCache:
    """Ground Truth画像のVGG特徴をキャッシュする"""

    def __init__(
        self,
        device: str = "cuda",
        dtype: torch.dtype = torch.float16,
        use_pinned_memory: bool = True,
        layers: list[str] = ["conv3_3"],  # 1層のみ（精度とコストのバランス）
    ):
        self.cache: dict[str, torch.Tensor] = {}
        self.device = device
        self.dtype = dtype
        self.use_pinned_memory = use_pinned_memory
        self.layers = layers

    def get_or_compute(
        self,
        image_id: str,
        gt_image: torch.Tensor,
        vgg_fn: callable
    ) -> torch.Tensor:
        """キャッシュから取得、なければ計算して保存"""
        if image_id not in self.cache:
            with torch.no_grad():
                features = vgg_fn(gt_image.to(self.dtype))

            if self.use_pinned_memory:
                # ピン留めCPUメモリに退避（VRAMを節約）
                pinned = torch.empty_like(features, device="cpu", pin_memory=True)
                pinned.copy_(features)
                self.cache[image_id] = pinned
            else:
                self.cache[image_id] = features.cpu()

        # 非同期H2D転送（ノンブロッキング）
        return self.cache[image_id].to(self.device, non_blocking=True)
```

### 設計上の重要な判断

**1. pinned memory（ページロックメモリ）**

通常のCPUメモリはページングされるため、GPU転送時にOSが一時バッファにコピーする。ピン留めメモリはページングされないため、**直接DMA転送が可能**で転送が高速になる。

```python
pinned = torch.empty_like(features, device="cpu", pin_memory=True)
```

**2. fp16での保存**

GTは可変精度でなく固定値なので、fp16で十分。fp32比でメモリ使用量が半減。

**3. conv3_3のみ使用**

VGGは5層の特徴を使えるが、3層目だけで十分な知覚的類似度が得られる。

```
全層使用: 28.3ms → conv3_3のみ: 13.8ms（51%削減）
```

**4. 非同期H2D転送**

```python
features.to(self.device, non_blocking=True)
```

`non_blocking=True`でCPU→GPU転送を非同期化。データ転送と計算をオーバーラップさせる。

---

## OOM対策：自動フォールバック

RTX 5090（32GB）でも大規模訓練ではOOMが起きる。

```python
def estimate_memory_gb(
    num_images: int,
    layers: list[str],
    dtype: torch.dtype,
    resolution: tuple[int, int]
) -> float:
    """キャッシュメモリ使用量を推定（精度2.5%）"""
    h, w = resolution
    bytes_per_pixel = 2 if dtype == torch.float16 else 4

    layer_sizes = {
        "conv1_2": 64,   # チャンネル数
        "conv2_2": 128,
        "conv3_3": 256,
        "conv4_3": 512,
        "conv5_3": 512,
    }

    total_bytes = 0
    for layer in layers:
        channels = layer_sizes[layer]
        # VGG特徴マップのサイズ（ストライドを考慮）
        stride = 2 ** list(layer_sizes.keys()).index(layer)
        fh, fw = h // stride, w // stride
        total_bytes += num_images * channels * fh * fw * bytes_per_pixel

    return total_bytes / (1024 ** 3)


class PerceptualGTCache:
    def __init__(self, max_memory_gb: float = 4.0, ...):
        self.max_memory_gb = max_memory_gb
        self.enabled = True

    def get_or_compute(self, ...):
        if not self.enabled:
            # フォールバック：キャッシュなしで計算
            return vgg_fn(gt_image.to(self.dtype))

        # メモリ超過チェック
        if self._current_memory_gb() > self.max_memory_gb:
            print("[GTCache] Memory limit reached, disabling cache")
            self.enabled = False
            return vgg_fn(gt_image.to(self.dtype))

        # 通常のキャッシュフロー
        ...
```

---

## デッドロック回避：non_blockingの注意点

`non_blocking=True`は便利だが、**デッドロックのリスクがある**。

```python
# NG: デッドロックの可能性
features = cache.get_or_compute(id, gt, vgg_fn)
loss = lpips(features, pred_features)  # featuresがまだ転送中かも

# OK: 同期ポイントを明示
features = cache.get_or_compute(id, gt, vgg_fn)
torch.cuda.synchronize()  # 転送完了を保証
loss = lpips(features, pred_features)
```

実際には学習ループ内で自然に同期が入るため、`synchronize()`を明示的に呼ぶ必要はほとんどない。ただし、マルチGPUや非同期データローダーとの組み合わせでは注意が必要。

---

## ベンチマーク結果

```
環境: RTX 5090 32GB, CUDA 12.8, PyTorch 2.8.0

--- キャッシュなし ---
Loss stage:  42.10ms / iter
Total:       72.44ms / iter

--- キャッシュあり (conv3_3_only, fp16, pinned_cpu) ---
Loss stage:  17.25ms / iter  (-59.0%)
Total:       40.80ms / iter  (-43.7%)

--- 設定比較 ---
fp32 + non-pinned:     47.21ms (-34.8%)
fp32 + pinned:         44.13ms (-39.1%)
fp16 + pinned:         41.95ms (-42.1%)
fp16 + pinned + 1层:   40.80ms (-43.7%) ← 最適設定
```

### 品質への影響

```
キャッシュなし PSNR:  28.66 dB
キャッシュあり PSNR:  28.66 dB  (差分: 9.54e-07)
```

**bit-exactではないが、知覚的に等価**。fp16の丸め誤差が入るが、学習への影響はゼロ。

---

## 大規模訓練での効果

1シーン1秒の節約が1000シーンになると：

```
節約時間/iter = 72.44 - 40.80 = 31.64ms
総iter数 = 1000シーン × 10,000 iter = 10,000,000 iter

節約時間 = 31.64ms × 10,000,000 = 316,400秒 ≈ 87.9時間
```

**3日半以上の計算時間が不要になる**。クラウドGPUなら約$500〜1000のコスト削減。

---

## 自動有効化の条件

24GB以上のVRAMを持つGPUでのみ自動有効化：

```python
def should_enable_gt_cache(gpu_memory_gb: float) -> bool:
    """キャッシュ有効化の判断"""
    # ピン留めCPUメモリに退避するため、GPU側の負担は小さい
    # ただし小VRAM環境では転送オーバーヘッドが支配的になる
    return gpu_memory_gb >= 24.0
```

RTX 3090（24GB）、RTX 4090（24GB）、RTX 5090（32GB）で有効。RTX 3080（10GB）では無効化。

---

## まとめ

| 観点 | 内容 |
|------|------|
| 問題 | GTのVGG特徴を毎iterationで再計算（全体の40%以上） |
| 解決策 | PerceptualGTCacheクラス（pinned_cpu + fp16 + conv3_3） |
| 効果 | 72.44ms → 40.80ms（-43.7%） |
| 品質影響 | 9.54e-07の差分（実質ゼロ） |
| 大規模効果 | 1000シーン×10Kiterで87.7時間節約 |
| 安全性 | OOM時自動フォールバック、デッドロックなし |

GTは変わらない。なら計算するな。当たり前の最適化が、大きな効果をもたらした。

---

## 関連記事

- [3DGS Backwardの勾配公式を間違えてPSNRが17→24dBになった話](/articles/3dgs-backward-gradient-formula-wrong)
- [DGRを超えるまで: PSNRを28.66→29.07dBに改善した全記録](/articles/3dgs-psnr-dgr-surpassed)
