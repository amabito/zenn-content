---
title: "CUDA warp同期で半日溶かした話：__shfl_xor_syncの罠"
emoji: "🪤"
type: "tech"
topics: ["CUDA", "GPU", "デバッグ", "並列処理", "NVIDIA"]
published: true
---

# 結論から言う

**`__shfl_xor_sync`を条件分岐の中で呼ぶな。デッドロックする。**

この記事では、CUDA warp同期プリミティブで半日ハマった経験を共有する。同じ罠にハマる人が減れば幸いだ。

---

# 何を作っていたか

3D Gaussian Splatting（3DGS）用のカスタムラスタライザを開発していた。Backward Pass（勾配計算）で、各ピクセルから各Gaussianへの勾配を集約する必要がある。

素朴に実装すると、こうなる:

```cuda
// 各スレッドが勾配を計算
float grad = compute_gradient(...);

// 全スレッドがatomicAdd
atomicAdd(&gaussian_grad[gid], grad);
```

問題: atomicAddが大量に発生し、パフォーマンスが悪い。

---

# Quad Reductionのアイデア

「4スレッド（2x2ピクセル）で勾配を集約してから、代表1スレッドだけがatomicAddすれば、atomic操作が4分の1になるのでは？」

これがQuad Reductionだ。

```cuda
// 4スレッドで集約（shuffle使用）
float quad_sum = grad;
quad_sum += __shfl_xor_sync(0xFFFFFFFF, quad_sum, 1);  // 隣と交換
quad_sum += __shfl_xor_sync(0xFFFFFFFF, quad_sum, 2);  // 2つ先と交換

// 4スレッド中1つだけがatomicAdd
if ((threadIdx.x & 3) == 0) {
    atomicAdd(&gaussian_grad[gid], quad_sum);
}
```

理論的には完璧。atomic操作が1/4になり、高速化するはず。

---

# 症状：カーネルがハングする

実装してビルド。テスト実行。

```
Running backward pass...
（無限に待機）
```

**ハングした。**

タイムアウト後にエラー:
```
CUDA error: an illegal memory access was encountered
```

---

# 原因の調査

## 仮説1: メモリアクセス違反

最初は普通のバグだと思った。インデックスの範囲チェック、ポインタの検証...問題なし。

## 仮説2: 競合状態

atomicAddの競合？いや、そもそもatomicAddに到達する前にハングしている。

## 仮説3: warp同期の問題

`__shfl_xor_sync`のドキュメントを読み直す:

> All threads in the warp specified by mask must execute the same __shfl_xor_sync() call.

**「maskで指定されたwarp内の全スレッドが、同じ`__shfl_xor_sync`を実行しなければならない」**

...待って。

---

# 問題の本質

私のコードには、こういう構造があった:

```cuda
for (int i = range.x; i < range.y; i++) {
    // ピクセルがこのGaussianに影響されるかチェック
    if (!is_inside_gaussian(px, py, gaussian[i])) {
        continue;  // ← ここでスキップ
    }

    // 勾配計算
    float grad = compute_gradient(...);

    // Quad Reduction
    float quad_sum = grad;
    quad_sum += __shfl_xor_sync(0xFFFFFFFF, quad_sum, 1);  // ← 危険！
    quad_sum += __shfl_xor_sync(0xFFFFFFFF, quad_sum, 2);

    if ((threadIdx.x & 3) == 0) {
        atomicAdd(&gaussian_grad[i], quad_sum);
    }
}
```

**問題**: warp内の32スレッドのうち、一部だけが`continue`でスキップし、残りが`__shfl_xor_sync`に到達する。

結果: shuffleに参加するスレッド数が不一致 → **デッドロック**

---

# なぜデッドロックするのか

`__shfl_xor_sync`の動作:

1. mask（`0xFFFFFFFF` = 全32スレッド）で指定されたスレッドが**全員集合するまで待つ**
2. 全員揃ったらデータ交換
3. 次へ進む

一部のスレッドが`continue`でループを進めると:
- 進んだスレッド: 次のイテレーションの`__shfl_xor_sync`で待機
- 残ったスレッド: 現在のイテレーションの`__shfl_xor_sync`で待機

**永遠に揃わない。デッドロック。**

---

# 解決策

## 方法1: 条件分岐の外でshuffle

```cuda
for (int i = range.x; i < range.y; i++) {
    // 全スレッドが参加（条件分岐なし）
    float grad = 0.0f;
    bool valid = is_inside_gaussian(px, py, gaussian[i]);

    if (valid) {
        grad = compute_gradient(...);
    }

    // 全スレッドがshuffleに参加
    float quad_sum = grad;
    quad_sum += __shfl_xor_sync(0xFFFFFFFF, quad_sum, 1);
    quad_sum += __shfl_xor_sync(0xFFFFFFFF, quad_sum, 2);

    // 有効なスレッドだけがatomicAdd
    if (valid && (threadIdx.x & 3) == 0) {
        atomicAdd(&gaussian_grad[i], quad_sum);
    }
}
```

ポイント:
- `continue`を使わない
- 全スレッドがshuffleに参加
- 無効なスレッドは`grad = 0`を渡す（集約に影響しない）

## 方法2: maskを動的に設定

```cuda
// 有効なスレッドだけでmaskを作成
unsigned int active_mask = __ballot_sync(0xFFFFFFFF, valid);
float quad_sum = grad;
quad_sum += __shfl_xor_sync(active_mask, quad_sum, 1);
quad_sum += __shfl_xor_sync(active_mask, quad_sum, 2);
```

この方法は複雑になるので、方法1を推奨。

---

# 修正後の結果

| 項目 | Before | After |
|------|--------|-------|
| Backward Pass | ハング | 正常動作 |
| atomic操作 | 100% | 25% |
| 効果 | - | **4x削減** |

---

# 教訓

## 1. warp同期プリミティブは条件分岐に注意

`__shfl_*_sync`, `__ballot_sync`, `__any_sync`, `__all_sync` などのwarpレベル命令は、**mask内の全スレッドが同じ命令を実行しなければならない**。

## 2. エラーメッセージは嘘をつく

「illegal memory access」と言われたが、実際はデッドロックだった。CUDAのエラーメッセージは、根本原因を示さないことがある。

## 3. ドキュメントは読め

NVIDIAのドキュメントにはちゃんと書いてある:

> If the executing thread is active and its corresponding bit in mask is not set, the behavior is undefined.

「未定義動作」と書かれたら、何が起きても文句は言えない。

---

# まとめ

| やること | やらないこと |
|---------|------------|
| 全スレッドでshuffle | 条件分岐内でshuffle |
| 無効スレッドは0を渡す | continueでスキップ |
| maskを正しく設定 | 0xFFFFFFFFを盲目的に使う |

**warp同期は強力だが、使い方を間違えるとデッドロックする。**

この記事が誰かの半日を救えれば幸いだ。

---

完全な実装コード、ベンチマーク、他のwarp同期の罠は有料記事で解説しています。

https://zenn.dev/amabito/articles/cuda-warp-sync-trap-paid

---

# 関連記事

## CUDA開発シリーズ
- [CUDAメモリ管理の罠](https://zenn.dev/amabito/articles/cuda-memory-management) - first-frame bug、73GB問題
- [RTX 5090 CUDA最適化](https://zenn.dev/amabito/articles/rtx5090-cuda-optimization) - Blackwell世代の最適化
- [PyTorch CUDA拡張](https://zenn.dev/amabito/articles/pytorch-cuda-extension) - Windowsビルドの罠

## 3DGSシリーズ
- [HyperRasterizer完全解説](https://zenn.dev/amabito/articles/hyper-rasterizer-zenn) - 4169FPS達成の独自ラスタライザ
- [3DGS商用化ガイド](https://zenn.dev/amabito/articles/3dgs-commercial-guide) - ライセンス問題の整理
