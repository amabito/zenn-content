---
title: "3DGS Forward/BackwardのIndex semantics不一致で勾配が4887倍ロストした話"
emoji: "💀"
type: "tech"
topics: ["CUDA", "3DGS", "機械学習", "デバッグ", "GPU"]
published: false
published_at: "2026-02-27 21:00"
---

## コンパイルエラーなし。PSNRが謎に低い。

3DGS（3D Gaussian Splatting）のカスタムラスタライザーを書いていたとき、**コンパイルは通るしクラッシュもしないが、PSNRが期待より大幅に低い**という状況に何週間もはまった。

最終的に判明した原因は単純だった。**ForwardとBackwardで変数の「座標系」が違った**。

---

## 問題のコード

3DGSのforward passでは、各Gaussianに「番号」を振る処理がある。

```cpp
// forward: タイル内でのGaussianペアのインデックス
// BATCH_SIZE = 128

__global__ void forward_kernel(...) {
    int batch = blockIdx.x;
    int i = threadIdx.x;

    // last = このbatchの最後のペアインデックス（タイルローカル）
    int last = batch * BATCH_SIZE + i;  // ← タイルローカルインデックス

    // lastを使ってデータを保存
    pair_data[last] = compute_pair(...);
}
```

backward passでは同じ`last`変数を使って勾配を取り出す。

```cpp
// backward: forwardで保存したデータを取り出す

__global__ void backward_kernel(...) {
    int global_pair_idx = blockIdx.x * BATCH_SIZE + threadIdx.x;

    // lastはグローバルインデックスのつもりで使っている
    auto pair = pair_data[global_pair_idx];  // ← グローバルインデックス
    // forwardは pair_data[タイルローカルインデックス] に書き込んでいた
}
```

ForwardはタイルローカルインデックスでArrayに書き込み、BackwardはグローバルインデックスでArrayから読み出す。

---

## 何が起きているか

具体例で説明する。

```
シーン: 4タイル、各タイルにGaussian 100個

タイル0のGaussian:
  forward:  pair_data[0..99]  に書き込み（タイルローカル 0-99）
  backward: pair_data[0..99]  から読み出し → OK（偶然一致）

タイル1のGaussian（グローバルインデックス 100-199）:
  forward:  pair_data[0..99]  に書き込み（タイルローカル、また0から始まる！）
  backward: pair_data[100..199] から読み出し（グローバルインデックス）
  → タイル0のデータを勾配として使用！

タイル2のGaussian（グローバルインデックス 200-299）:
  forward:  pair_data[0..99]  に書き込み（また0から！）
  backward: pair_data[200..299] から読み出し
  → 未初期化メモリか別タイルのデータを使用！
```

タイル0のGaussianだけは「偶然」一致する。他のタイルはすべて間違ったデータを使う。

---

## なぜ4887倍なのか

この問題が引き起こす勾配フローの損失を計算すると：

```
正しい勾配フロー:
  全タイル × BATCH_SIZE = N_total ペアが正しい勾配を受け取る

誤った勾配フロー:
  タイル0のみ正しい勾配を受け取る（全体の 1/タイル数）
  タイル0以外は無関係なデータから勾配を計算

例: 4887タイルのシーン
  正しく計算されるGaussian = 1/4887 = 0.02%
  誤りの勾配フロー = 4887倍の損失
```

**4887タイルのシーンで実験した結果、勾配フローが4887倍ロストしていた。**

これは「タイル数 = 損失率」という関係だ。1280x720の画像を16x16タイルで分割すると：

```
タイル数 = (1280/16) × (720/16) = 80 × 45 = 3600タイル
```

3600倍の勾配ロスト。PSNRが低かったわけだ。

---

## なぜこれがわかりにくいのか

### 1. コンパイルエラーが出ない

配列アクセスはそもそもCUDAでは境界チェックがない。タイルローカルインデックス（0-127）でグローバル配列にアクセスしても、有効なメモリ内なら何も言われない。

### 2. タイル0では動く

タイル0のデータが正しいため、「部分的に動いている」状態になる。全体的に遅いが動いてはいる。

### 3. PSNRは少しずつ改善する

勾配がゼロではなく（タイル0の勾配が正しく流れる）、ノイズが多い状態。PSNR自体は訓練を続けると改善するが、ひどく遅い。

```
正常な学習: iter 1000で PSNR 25dB
バグあり:   iter 1000で PSNR 18dB（タイル0だけ学習している）
```

---

## 発見の経緯

デバッグに使ったアプローチ：

### 1. 勾配ノルムを可視化

```python
# 訓練中に各Gaussianの勾配ノルムを記録
for i, gaussian in enumerate(gaussians):
    grad_norm = gaussian.means.grad.norm().item()
    print(f"Gaussian {i}: grad_norm = {grad_norm:.6f}")
```

結果：

```
Gaussian 0-127:    grad_norm = 0.014532  ← タイル0のGaussian（正常）
Gaussian 128-255:  grad_norm = 0.000003  ← タイル1（1/4887）
Gaussian 256-383:  grad_norm = 0.000003  ← タイル2（同様）
...
```

タイル0のGaussianだけ勾配が大きかった。

### 2. 単純シーンでの検証

タイルが1つだけになるほど小さい画像（16x16ピクセル）でテスト：

```python
# 16x16画像 → 1タイルのみ
image = torch.zeros(3, 16, 16)
loss = render(gaussians, image)
loss.backward()
# → すべてのGaussianが正しい勾配を受け取る（1タイルだけなので偶然一致）
```

このテストがパスした。次に32x32：

```python
image = torch.zeros(3, 32, 32)  # 4タイル
# → 勾配が4分の1になる
```

「タイル数が増えると勾配が減る」パターンが確認できた。

### 3. コードの変数名を追跡

```cpp
// grep で 'last' 変数の使用場所を全検索
// forward.cu: int last = batch * BATCH_SIZE + i;  ← タイルローカル
// backward.cu: pair_data[last]  ← なぜlastを使っている？
```

backwardコードのコメントに「globalインデックス」と書いてあるが、実際にはforwardから受け継いだタイルローカルインデックスだった。

---

## 修正

```cpp
// Before: 変数名が座標系を示していない
int last = batch * BATCH_SIZE + i;

// After: 座標系を変数名に明記
int tile_local_pair_idx = batch * BATCH_SIZE + i;    // forward用
int global_pair_idx = tile_id * TILE_CAPACITY + tile_local_pair_idx;  // backward用

// backwardでは常にglobal_pair_idxを使う
pair_data[global_pair_idx] = compute_pair(...);  // ← 変更
```

```cpp
// backward
int global_pair_idx = blockIdx.x * TILE_CAPACITY + threadIdx.x;
auto pair = pair_data[global_pair_idx];  // forwardと一致
```

修正後のPSNR：

```
before: 17.63 dB（4887倍の勾配ロスト）
after:  24.16 dB（+6.53 dB）
```

---

## 鉄則：座標系を変数名に明記する

このバグから学んだ最大の教訓：

```cpp
// NG: 何のインデックスかわからない
int last = batch * BATCH_SIZE + i;
int idx = ...;
int pos = ...;

// OK: 座標系が明確
int tile_local_pair_idx = batch * BATCH_SIZE + i;
int global_gaussian_idx = tile_id * MAX_GAUSSIANS_PER_TILE + local_idx;
int screen_pixel_x = threadIdx.x + blockIdx.x * TILE_W;
```

**インデックスには必ず「何の座標系か」を明記する。**

座標系の種類：
- `tile_local_*`: タイル内でのローカルインデックス（0 〜 BATCH_SIZE-1）
- `global_*`: 全タイルを通じたグローバルインデックス
- `screen_*`: スクリーン座標（ピクセル単位）
- `camera_*`: カメラ座標系
- `world_*`: ワールド座標系

---

## CUDAデバッグのためのチェックリスト

この経験から作ったチェックリスト：

```
ForwardとBackwardでデータを受け渡す時：
[ ] 同じインデックス計算式を使っているか？
[ ] 変数名で座標系が明示されているか？
[ ] 単一タイルのテストケースを作ったか？
[ ] 勾配ノルムを可視化して不均一性を確認したか？
[ ] コメントと実際のコードが一致しているか？

境界チェック（デバッグビルド推奨）：
[ ] assert(idx >= 0 && idx < ARRAY_SIZE) を追加したか？
[ ] cuda-memcheckで実行したか？
```

```cpp
// デバッグ用境界チェック（Releaseビルドでは自動無効化）
#ifdef DEBUG
    assert(global_pair_idx >= 0 && global_pair_idx < total_pairs);
#endif
```

---

## まとめ

| 観点 | 内容 |
|------|------|
| バグの本質 | Forward=タイルローカルインデックス、Backward=グローバルインデックス |
| 影響 | 勾配フロー 4887分の1（タイル数に比例） |
| PSNRへの影響 | 17.63 dB → 修正後 24.16 dB（+6.53 dB） |
| 発見方法 | 勾配ノルムの可視化 + 単純シーンでの検証 |
| 修正 | 変数名に座標系を明記、インデックス計算を統一 |
| 予防 | 命名規則の徹底、デバッグビルドでの境界チェック |

コンパイルが通ることは「正しさ」の証明にならない。特にCUDAのインデックス計算は。

---

## 関連記事

- [DGRを超えるまで: 3DGS PSNRを28.66→29.07dBに改善した全記録](/articles/3dgs-psnr-dgr-surpassed)
- [block_reduce.h 2D blockのthreadIdx.xバグで勾配が8倍になった話](/articles/cuda-block-reduce-2d-threadidx-bug)
- [3DGS Backwardの勾配公式を間違えてPSNRが17→24dBになった話](/articles/3dgs-backward-gradient-formula-wrong)
