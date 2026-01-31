---
title: "【有料】GPU高速化実践ガイド：CUDA/PyTorchで実務を10倍速にする"
emoji: "🔥"
type: "tech"
topics: ["GPU", "CUDA", "PyTorch", "高速化", "機械学習"]
published: true
published_at: "2026-02-13 07:00"
price: 1480
---

# この記事で得られるもの

**実務で使えるGPU高速化のテクニック集。**

- CuPy/PyTorchの**実践的な最適化手法**
- **メモリ効率**を最大化するテクニック
- **プロファイリング**で ボトルネックを特定する方法
- 実際のプロジェクトでの**高速化事例**

**対象読者:** GPU入門を終えた人、実務で高速化したい人

---

# 無料記事のおさらい

- GPUは単純計算を大量に並列実行するのが得意
- CuPyを使えばNumPyコードを50-100倍高速化できる
- データ転送と同期を忘れずに

今回は**実務レベルの最適化テクニック**を解説する。

---

:::message
ここから有料パートです。
:::

# PyTorchでの高速化テクニック

## 1. DataLoaderの最適化

```python
# ❌ 遅い設定
loader = DataLoader(dataset, batch_size=32)

# ✅ 高速化設定
loader = DataLoader(
    dataset,
    batch_size=32,
    num_workers=4,          # 並列読み込み
    pin_memory=True,        # GPU転送を高速化
    prefetch_factor=2,      # 先読み
    persistent_workers=True # ワーカー再利用
)
```

**効果: データ読み込みが2-5倍高速化**

## 2. 混合精度（AMP）

```python
from torch.cuda.amp import autocast, GradScaler

scaler = GradScaler()

for data, target in loader:
    optimizer.zero_grad()

    # 混合精度で forward
    with autocast():
        output = model(data)
        loss = criterion(output, target)

    # スケールしてbackward
    scaler.scale(loss).backward()
    scaler.step(optimizer)
    scaler.update()
```

**効果: 学習速度1.5-2倍、メモリ使用量半減**

## 3. torch.compile（PyTorch 2.0+）

```python
# モデルをコンパイル
model = torch.compile(model, mode="reduce-overhead")

# 以降は普通に使う
output = model(input)
```

**効果: 推論速度1.2-2倍（モデルによる）**

## 4. チェックポインティング

```python
from torch.utils.checkpoint import checkpoint

class LargeModel(nn.Module):
    def forward(self, x):
        # メモリ節約のためチェックポイント
        x = checkpoint(self.layer1, x)
        x = checkpoint(self.layer2, x)
        x = checkpoint(self.layer3, x)
        return x
```

**効果: メモリ使用量を大幅削減（速度は少し低下）**

---

# CuPyの高級テクニック

## 1. カスタムカーネル

```python
import cupy as cp

# CUDAカーネルを直接書く
kernel = cp.RawKernel(r'''
extern "C" __global__
void custom_relu(const float* x, float* y, int n) {
    int tid = blockDim.x * blockIdx.x + threadIdx.x;
    if (tid < n) {
        y[tid] = x[tid] > 0 ? x[tid] : 0;
    }
}
''', 'custom_relu')

# 使用
x = cp.random.randn(1000000, dtype=cp.float32)
y = cp.empty_like(x)

block_size = 256
grid_size = (x.size + block_size - 1) // block_size
kernel((grid_size,), (block_size,), (x, y, x.size))
```

**効果: 特殊な処理で2-10倍高速化の可能性**

## 2. メモリプールの活用

```python
# メモリプールを取得
mempool = cp.get_default_memory_pool()
pinned_mempool = cp.get_default_pinned_memory_pool()

# 使用量確認
print(f"GPU Memory: {mempool.used_bytes() / 1e9:.2f} GB")

# 明示的解放（大きな処理の後）
mempool.free_all_blocks()
pinned_mempool.free_all_blocks()

# メモリ制限設定
mempool.set_limit(size=8 * 1024**3)  # 8GB上限
```

## 3. ストリームによる非同期処理

```python
# 2つのストリームを作成
stream1 = cp.cuda.Stream()
stream2 = cp.cuda.Stream()

# 並列実行
with stream1:
    result1 = cp.sin(data1)

with stream2:
    result2 = cp.cos(data2)

# 同期
stream1.synchronize()
stream2.synchronize()
```

**効果: 独立した処理を並列化して1.5-2倍高速化**

---

# プロファイリング

## PyTorch Profiler

```python
from torch.profiler import profile, record_function, ProfilerActivity

with profile(
    activities=[ProfilerActivity.CPU, ProfilerActivity.CUDA],
    record_shapes=True,
    profile_memory=True
) as prof:
    for i, (data, target) in enumerate(loader):
        if i >= 10:  # 10バッチだけ計測
            break
        with record_function("forward"):
            output = model(data)
        with record_function("loss"):
            loss = criterion(output, target)
        with record_function("backward"):
            loss.backward()

# 結果出力
print(prof.key_averages().table(
    sort_by="cuda_time_total",
    row_limit=10
))

# Chrome trace形式で出力
prof.export_chrome_trace("trace.json")
```

## nsys（NVIDIA Nsight Systems）

```bash
# プロファイリング実行
nsys profile -o profile python train.py

# 結果をGUIで確認
nsys-ui profile.qdrep
```

## ボトルネックの見つけ方

```
1. CPU時間 >> GPU時間
   → データ読み込み/前処理がボトルネック
   → DataLoaderのnum_workers増やす

2. GPU時間が長い特定の関数
   → その関数を最適化
   → 混合精度、カーネル融合を検討

3. メモリ転送が多い
   → データをGPUに置いたままにする
   → pin_memoryを使う
```

---

# 実践的な高速化事例

## 事例1: 画像前処理パイプライン

**Before（CPU）: 50 images/sec**

```python
# CPU版
def preprocess_cpu(images):
    results = []
    for img in images:
        img = cv2.resize(img, (224, 224))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = img.astype(np.float32) / 255.0
        img = (img - mean) / std
        results.append(img)
    return np.stack(results)
```

**After（GPU）: 500 images/sec（10倍）**

```python
import cupy as cp
from cupyx.scipy import ndimage

def preprocess_gpu(images_gpu):
    # バッチでリサイズ（GPU）
    batch = cp.stack([
        ndimage.zoom(img, (224/img.shape[0], 224/img.shape[1], 1))
        for img in images_gpu
    ])
    # 正規化（GPU）
    batch = batch.astype(cp.float32) / 255.0
    batch = (batch - mean_gpu) / std_gpu
    return batch
```

## 事例2: 特徴量計算

**Before: 10秒/バッチ**

```python
# 逐次処理
features = []
for item in batch:
    f1 = compute_feature1(item)
    f2 = compute_feature2(item)
    features.append(np.concatenate([f1, f2]))
```

**After: 0.5秒/バッチ（20倍）**

```python
# バッチ処理 + GPU
batch_gpu = cp.asarray(batch)
f1 = compute_feature1_gpu(batch_gpu)  # バッチ対応
f2 = compute_feature2_gpu(batch_gpu)  # バッチ対応
features = cp.concatenate([f1, f2], axis=1)
```

## 事例3: 機械学習推論

**Before: 100 samples/sec**

```python
# 1サンプルずつ推論
for sample in samples:
    output = model(sample.unsqueeze(0))
```

**After: 2000 samples/sec（20倍）**

```python
# バッチ推論 + 最適化
model = torch.compile(model)
model.eval()

with torch.no_grad(), torch.cuda.amp.autocast():
    for batch in DataLoader(samples, batch_size=64):
        output = model(batch)
```

---

# GPUメモリの最適化

## メモリ使用量の削減

```python
# 1. 勾配を保持しない（推論時）
with torch.no_grad():
    output = model(input)

# 2. 不要なテンソルを削除
del intermediate_tensor
torch.cuda.empty_cache()

# 3. in-place操作
x.relu_()  # 新しいテンソルを作らない
x.add_(1)  # 同上

# 4. 勾配の蓄積を防ぐ
optimizer.zero_grad(set_to_none=True)  # メモリ効率が良い
```

## 大きなモデルの扱い

```python
# 勾配チェックポイント
from torch.utils.checkpoint import checkpoint_sequential

# 層を分割してチェックポイント
modules = list(model.children())
output = checkpoint_sequential(modules, 4, input)  # 4分割

# メモリ使用量: 1/4 程度に削減
```

---

# チェックリスト

## 高速化の優先順位

```
1. [ ] データ読み込みの最適化（num_workers, pin_memory）
2. [ ] バッチサイズの最大化（GPU使用率を上げる）
3. [ ] 混合精度（AMP）の導入
4. [ ] torch.compile の適用
5. [ ] 不要な計算の削除（eval(), no_grad()）
6. [ ] プロファイリングでボトルネック特定
7. [ ] カスタムカーネル（必要な場合のみ）
```

## よくある高速化ミス

```
❌ GPUが遊んでいる（データ読み込み律速）
❌ 小さすぎるバッチサイズ
❌ CPU-GPU転送が頻繁
❌ 同期が多すぎる
❌ メモリ不足でスワップ発生
```

---

# まとめ

| テクニック | 効果 | 難易度 |
|-----------|------|--------|
| DataLoader最適化 | 2-5倍 | 低 |
| 混合精度（AMP） | 1.5-2倍 | 低 |
| torch.compile | 1.2-2倍 | 低 |
| バッチ処理化 | 5-20倍 | 中 |
| カスタムカーネル | 2-10倍 | 高 |

**GPU高速化は「低コストで効果が高い」ものから順に試す。**

---

# 関連記事

- [GPUプログラミング入門](https://zenn.dev/amabito/articles/gpu-programming-intro) - 無料版
- [RTX 5090 CUDA最適化](https://zenn.dev/amabito/articles/rtx5090-cuda-optimization) - 最新GPU
- [3DGSを商用利用したい人へ](https://zenn.dev/amabito/articles/hyper-rasterizer-zenn) - GPU活用実例
