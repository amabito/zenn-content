---
title: "WebGPU vs WebGL：3Dグラフィックスの次世代標準"
emoji: "🎮"
type: "tech"
topics: ["WebGPU", "WebGL", "3D", "JavaScript", "グラフィックス"]
published: true
published_at: "2026-02-22 07:00"
---

# 結論から言う

**WebGPUはWebGLの後継であり、パフォーマンスが最大10倍向上する。**

| 項目 | WebGL | WebGPU |
|------|-------|--------|
| API設計 | OpenGL ES 2.0/3.0ベース | Vulkan/Metal/DX12ベース |
| コンピュートシェーダー | ❌ なし | ✅ あり |
| マルチスレッド | ❌ 非対応 | ✅ 対応 |
| パフォーマンス | 基準 | 2-10倍高速 |

この記事では、WebGPUの特徴と移行のポイントを解説する。

---

# WebGLの限界

## 1. 古いAPI設計

```
WebGLの問題:
├── OpenGL ES 2.0ベース（2007年設計）
├── ステートマシン方式（グローバル状態管理）
├── ドライバ依存の挙動差
└── モダンGPUの機能を活かせない
```

## 2. コンピュートシェーダーがない

```
WebGLでの並列計算:
├── テクスチャにデータを格納
├── フラグメントシェーダーで計算
├── 結果をテクスチャに書き出し
└── 非効率、複雑、制限あり

結果:
├── 機械学習: 実用レベルで困難
├── 物理シミュレーション: 制限あり
└── ポストプロセス: 複雑な実装
```

## 3. CPU-GPUの同期問題

```
WebGLの描画ループ:
├── JSでコマンド発行
├── ドライバがバッファリング
├── GPUで実行
├── 同期ポイントで待機
└── CPUがアイドル状態に

問題:
├── CPUとGPUが交互に待機
├── 並列性が低い
└── レイテンシが大きい
```

---

# WebGPUの特徴

## 1. モダンなAPI設計

```
WebGPU:
├── Vulkan/Metal/DX12の概念をWeb向けに抽象化
├── 明示的なリソース管理
├── パイプライン事前コンパイル
├── 予測可能な挙動
└── クロスプラットフォーム統一API
```

## 2. コンピュートシェーダー

```wgsl
// WGSL（WebGPU Shading Language）
@compute @workgroup_size(256)
fn main(@builtin(global_invocation_id) id: vec3<u32>) {
    let index = id.x;
    output[index] = input[index] * 2.0;
}
```

**用途:**
- 機械学習推論（ブラウザでLLM実行）
- 物理シミュレーション
- 画像・動画処理
- 3D Gaussian Splattingレンダリング

## 3. コマンドバッファ

```javascript
// WebGPU: コマンドを事前に記録
const commandEncoder = device.createCommandEncoder();
const passEncoder = commandEncoder.beginRenderPass(renderPassDescriptor);
passEncoder.setPipeline(pipeline);
passEncoder.draw(3);
passEncoder.end();

// 一括でGPUに送信
device.queue.submit([commandEncoder.finish()]);
```

**効果:**
- CPU-GPU間の同期を最小化
- バッチ処理で効率向上
- 予測可能なパフォーマンス

---

# 比較: WebGL vs WebGPU

## コード比較: 三角形の描画

### WebGL

```javascript
// WebGL: 状態をグローバルに設定
const program = createProgram(gl, vertexShader, fragmentShader);
gl.useProgram(program);

const buffer = gl.createBuffer();
gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
gl.bufferData(gl.ARRAY_BUFFER, vertices, gl.STATIC_DRAW);

const positionLoc = gl.getAttribLocation(program, 'position');
gl.enableVertexAttribArray(positionLoc);
gl.vertexAttribPointer(positionLoc, 3, gl.FLOAT, false, 0, 0);

gl.drawArrays(gl.TRIANGLES, 0, 3);
```

### WebGPU

```javascript
// WebGPU: パイプラインとバインドグループで明示的に管理
const pipeline = device.createRenderPipeline({
  vertex: { module: shaderModule, entryPoint: 'vertexMain' },
  fragment: { module: shaderModule, entryPoint: 'fragmentMain' },
  // ... 他の設定
});

const vertexBuffer = device.createBuffer({
  size: vertices.byteLength,
  usage: GPUBufferUsage.VERTEX | GPUBufferUsage.COPY_DST,
});
device.queue.writeBuffer(vertexBuffer, 0, vertices);

// 描画コマンド
passEncoder.setPipeline(pipeline);
passEncoder.setVertexBuffer(0, vertexBuffer);
passEncoder.draw(3);
```

## パフォーマンス比較

| シナリオ | WebGL | WebGPU | 差 |
|---------|-------|--------|-----|
| 大量オブジェクト描画 | 10K objects | 100K objects | 10倍 |
| コンピュート処理 | 不可 | 高速 | - |
| GPU並列処理 | 制限あり | フル活用 | 5-10倍 |
| ドローコール | 1000回/frame | 10000回/frame | 10倍 |

---

# 移行ガイド

## 1. 段階的な移行

```
推奨アプローチ:
├── 新規プロジェクト → WebGPU優先
├── 既存プロジェクト → 機能追加時にWebGPU検討
├── コンピュート処理 → WebGPU一択
└── 広範なブラウザ対応が必要 → WebGL維持
```

## 2. フォールバック実装

```javascript
async function initGraphics() {
  if (navigator.gpu) {
    // WebGPU対応ブラウザ
    const adapter = await navigator.gpu.requestAdapter();
    const device = await adapter.requestDevice();
    return new WebGPURenderer(device);
  } else {
    // WebGLにフォールバック
    const canvas = document.querySelector('canvas');
    const gl = canvas.getContext('webgl2');
    return new WebGLRenderer(gl);
  }
}
```

## 3. ライブラリの選択

| ライブラリ | WebGL | WebGPU |
|-----------|-------|--------|
| Three.js | ✅ 安定 | ✅ 実験的対応 |
| Babylon.js | ✅ 安定 | ✅ 正式対応 |
| PlayCanvas | ✅ 安定 | ✅ 対応中 |
| wgpu (Rust) | - | ✅ ネイティブ対応 |

---

# ブラウザ対応状況

## 2026年1月現在

| ブラウザ | WebGL 2.0 | WebGPU |
|---------|-----------|--------|
| Chrome | ✅ | ✅ デフォルト有効 |
| Edge | ✅ | ✅ デフォルト有効 |
| Firefox | ✅ | ✅ フラグで有効 |
| Safari | ✅ | ✅ macOS 14+, iOS 17+ |

## 注意点

```
WebGPU非対応環境:
├── 古いブラウザ
├── 一部のモバイルデバイス
├── 仮想環境（GPU未割り当て）
└── WebView（アプリ内ブラウザ）

対策:
├── WebGLフォールバック
├── 機能検出で分岐
└── プログレッシブエンハンスメント
```

---

# ユースケース別推奨

| ユースケース | 推奨 | 理由 |
|-------------|------|------|
| ゲーム（新規） | WebGPU | パフォーマンス重視 |
| ゲーム（既存） | WebGL | 移行コスト考慮 |
| データ可視化 | WebGL/WebGPU | 規模による |
| 機械学習（ブラウザ） | WebGPU | コンピュートシェーダー必須 |
| 3DGSビューア | WebGPU | 大量のGaussian処理 |
| 広範な互換性重視 | WebGL | 対応ブラウザ多い |

---

# まとめ

| 項目 | WebGL | WebGPU |
|------|-------|--------|
| API設計 | OpenGL ESベース | Vulkan/Metal/DX12ベース |
| コンピュートシェーダー | ❌ | ✅ |
| パフォーマンス | 基準 | 2-10倍高速 |
| ブラウザ対応 | 広い | 主要ブラウザ対応済み |
| 推奨シナリオ | 互換性重視 | パフォーマンス重視 |

**新規プロジェクトはWebGPU、既存はフォールバック付きで段階移行。**

---

# 関連記事

## 3DGSシリーズ
- [HyperViewer](https://zenn.dev/amabito/articles/hyper-viewer-webgpu) - WebGPUで3DGS表示
- [3DGSとは？](https://zenn.dev/amabito/articles/3dgs-business-guide) - 経営者向け解説

## 技術シリーズ
- [RTX 5090 CUDA最適化](https://zenn.dev/amabito/articles/rtx5090-cuda-optimization) - GPU最適化

---

:::message
WebGPUはまだ進化中の技術です。最新の仕様は[WebGPU Specification](https://www.w3.org/TR/webgpu/)を確認してください。
:::
