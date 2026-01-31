---
title: "WebGPU全ブラウザ対応完了：WebGL時代の終わりと3DGSへの影響"
emoji: "🌐"
type: "tech"
topics: ["WebGPU", "WebGL", "3DGS", "ブラウザ", "JavaScript"]
published: true
published_at: "2026-01-21 21:00"
---

# 結論から言う

**2026年1月、Chrome・Edge・Firefox・Safari全メジャーブラウザでWebGPUが利用可能になった。WebGLフォールバックなしで開発できる時代が始まった。**

「WebGPU使いたいけど、Safariが...」「Firefoxユーザーが見れない」

この言い訳がもう通用しなくなった。

**対象読者:**
- Web3D開発者
- 3DGSをブラウザで表示したいエンジニア
- WebGLプロジェクトの移行を検討している人

**この記事で得られること:**
- 各ブラウザのWebGPU対応状況（2026年1月時点）
- WebGL→WebGPU移行の判断基準
- 3D Gaussian Splattingへの具体的な影響
- 残る課題とその対処法

---

# 2026年1月に何が起きたか

## ブラウザ対応の全体像

| ブラウザ | WebGPU対応 | リリース日 | 備考 |
|---------|-----------|-----------|------|
| Chrome | v113〜 | 2023/04 | 最初の対応ブラウザ |
| Edge | v113〜 | 2023/04 | Chromiumベース |
| Safari | v26〜 | 2025〜 | デフォルト有効 |
| Firefox | v147〜 | 2026/01/13 | Windows + ARM64 macOS |

## Firefox 147の意味

Firefox 147（2026年1月13日リリース）で、Windows版とARM64 macOS版でWebGPUがデフォルト有効になった。

```
Firefox WebGPU対応の経緯:
├── 2023年: フラグ付きで実験的対応
├── 2024年: Nightly版で段階的テスト
├── 2025年: Windows版で限定有効化
└── 2026/01/13: v147でWindows + ARM64 macOSデフォルト有効
```

これにより、主要4ブラウザすべてがWebGPUをデフォルトで利用可能になった。

## Safari 26のデフォルト有効化

Safariは独自のWebGPU実装を持ち、Metal APIをバックエンドに使用している。Safari 26でデフォルト有効となり、iPhoneやiPadでもWebGPUが使える環境が整った。

```
Safari WebGPU対応:
├── macOS: Safari 26でデフォルト有効
├── iOS/iPadOS: Safari 26でデフォルト有効
├── バックエンド: Metal API
└── WebKit独自実装（Dawn/wgpuではない）
```

---

# WebGL時代の終わりとは何か

## WebGLは「使えなくなる」わけではない

誤解しないでほしい。WebGLが廃止されるわけではない。

```
正しい理解:
├── WebGLは引き続き動作する
├── ブラウザベンダーが即座に削除することはない
├── 既存のWebGLアプリケーションは壊れない
└── ただし、新規開発でWebGLを選ぶ理由がなくなった
```

## 新規開発でWebGPUを選ぶべき理由

| 観点 | WebGL | WebGPU |
|------|-------|--------|
| API設計 | OpenGL ES 2.0/3.0（2007年設計） | Vulkan/Metal/DX12ベース |
| コンピュートシェーダー | なし | あり |
| 描画効率 | 1K drawcalls/frame | 10K+ drawcalls/frame |
| 並列処理 | 制限あり | GPU並列フル活用 |
| ブラウザ対応 | 全ブラウザ | **全メジャーブラウザ** |

2026年1月以降、「ブラウザ対応が広い」というWebGLの唯一の優位性が消えた。

---

# 3D Gaussian Splattingへの影響

## なぜWebGPUが3DGSに不可欠か

3DGSのリアルタイムレンダリングには、コンピュートシェーダーが必須に近い。

```
3DGSレンダリングパイプライン:
├── 1. ソート（コンピュートシェーダー）
│   ├── 数百万のGaussianを深度ソート
│   ├── Radix Sortをstorageバッファで実行
│   └── WebGLでは不可能 → CPUフォールバックで10倍遅い
├── 2. Splatting（レンダーパイプライン）
│   ├── 各Gaussianを2D楕円に投影
│   └── アルファブレンディング
└── 3. 後処理（コンピュートシェーダー）
    └── タイル分割処理の高速化
```

## パフォーマンス: 100万ポイント60fps

WebGPUにより、ブラウザ上で100万ポイントの3DGSを60fpsで表示できるようになった。

| シーン規模 | WebGL（CPUソート） | WebGPU | 倍率 |
|-----------|------------------|--------|------|
| 10万ポイント | 30fps | 120fps | 4倍 |
| 50万ポイント | 8fps | 90fps | 11倍 |
| 100万ポイント | 2fps | 60fps | 30倍 |
| 200万ポイント | 表示不可 | 35fps | - |

ソート処理がGPU側で完結するため、ポイント数が増えるほどWebGPUの優位性は拡大する。

## WebLLMでも80%のネイティブ性能

WebGPUの恩恵は3Dレンダリングだけではない。WebLLMではネイティブアプリの約80%の性能をブラウザ上で達成している。コンピュートシェーダーによるGPU汎用計算がブラウザでも現実的になったことを意味する。

---

# 主要ライブラリの対応状況

## Three.js WebGPUレンダラー

Three.jsは`WebGPURenderer`を提供しており、既存のThree.jsコードからの移行が比較的容易。

```javascript
import { WebGPURenderer } from 'three/webgpu';

const renderer = new WebGPURenderer();
await renderer.init();
```

Three.js r170以降、WebGPUレンダラーが安定版として利用可能。TSL（Three.js Shading Language）によるシェーダー記述も整備されている。

## Babylon.js 8.0

Babylon.js 8.0はWebGPUを第一級でサポートし、Gaussian Splatting描画にも対応。

```
Babylon.js 8.0のWebGPU対応:
├── WebGPUエンジンがデフォルト選択可能
├── Gaussian Splatting描画のビルトインサポート
├── コンピュートシェーダーAPIが安定
└── WebGLフォールバック自動切り替え
```

## PlayCanvas SuperSplat

PlayCanvasのSuperSplatはMITライセンスのオープンソース3DGSビューア。WebGPUネイティブで動作し、大規模シーンの表示に最適化されている。

```
SuperSplat:
├── ライセンス: MIT
├── レンダリング: WebGPU
├── 対応フォーマット: PLY, Splat
├── 機能: ソート、LOD、圧縮対応
└── 用途: エディタ + ビューア
```

---

# 残る課題

## Linux対応が未完了

全ブラウザ対応と言っても、Linux環境は完全ではない。

| ブラウザ | Windows | macOS | Linux |
|---------|---------|-------|-------|
| Chrome | デフォルト有効 | デフォルト有効 | 段階的ロールアウト中 |
| Edge | デフォルト有効 | デフォルト有効 | 段階的ロールアウト中 |
| Firefox | デフォルト有効 | ARM64のみ | Nightlyのみ |
| Safari | - | デフォルト有効 | - |

```
Linux対応の課題:
├── ドライバの多様性（Mesa、NVIDIA、AMD）
├── Vulkanバックエンドの安定性
├── X11/Waylandの差異
└── 段階的にロールアウト中（2026年中に解消見込み）
```

## モバイルGPUの性能制約

デスクトップでは60fpsの3DGSも、モバイルGPUでは依然として厳しい。

```
モバイルGPUの現状:
├── Snapdragon 8 Elite: 100万ポイント 15-20fps
├── Apple A18 Pro: 100万ポイント 25-30fps
├── Mali-G720: 100万ポイント 5-10fps
└── 結論: LODと圧縮なしではモバイルは実用的でない
```

## WebGPU仕様の未確定部分

```
まだ策定中の機能:
├── Subgroups（ワープレベル操作）
├── Bindless textures
├── Ray tracing
└── Multi-draw indirect
```

これらの機能が確定すれば、さらなるパフォーマンス向上が見込める。

---

# 開発者が今すべきこと

## 新規プロジェクト: WebGPU一択

```
判断フロー:
├── 新規プロジェクト → WebGPUで開始
├── コンピュート処理あり → WebGPU一択
├── 3DGSビューア → WebGPU一択
└── レガシーブラウザ対応必須 → WebGLフォールバック併用
```

## 既存プロジェクト: 段階的移行

```javascript
// フォールバック付き初期化パターン
async function initRenderer(canvas) {
  if (navigator.gpu) {
    const adapter = await navigator.gpu.requestAdapter();
    if (adapter) {
      const device = await adapter.requestDevice();
      return new WebGPURenderer(canvas, device);
    }
  }
  // WebGLフォールバック
  const gl = canvas.getContext('webgl2');
  return new WebGLRenderer(canvas, gl);
}
```

## フォールバックが不要になる時期

2026年中にLinux対応が完了すれば、WebGLフォールバックを完全に廃止できる見込み。ただし、企業内ブラウザ（古いChromiumベースのWebView等）への対応が必要な場合は、もう少し時間がかかる。

---

# まとめ

| 項目 | 状況 |
|------|------|
| 全メジャーブラウザ対応 | 完了（2026年1月） |
| 新規開発の推奨 | WebGPU |
| 3DGS 100万ポイント | 60fps達成 |
| Linux対応 | 段階的ロールアウト中 |
| モバイル対応 | LOD/圧縮が必須 |

**2026年1月は、Webグラフィックスの転換点。WebGPUが全ブラウザで使える今、移行しない理由はない。**

---

# 関連記事

- [WebGPU vs WebGL](https://zenn.dev/amabito/articles/webgpu-vs-webgl) - WebGPUとWebGLの技術的な違い
- [HyperViewer: WebGPU 3DGSビューア](https://zenn.dev/amabito/articles/hyper-viewer-webgpu) - WebGPUで3DGSを表示する実装
- [3DGSストリーミング](https://zenn.dev/amabito/articles/3dgs-streaming) - 大規模シーンの配信手法

---

# 参考

- [WebGPU Specification - W3C](https://www.w3.org/TR/webgpu/)
- [Firefox 147 Release Notes - Mozilla](https://www.mozilla.org/en-US/firefox/147.0/releasenotes/)
- [WebKit WebGPU Status](https://webkit.org/status/#specification-webgpu)
- [Chrome Platform Status - WebGPU](https://chromestatus.com/feature/6213121689518080)
- [PlayCanvas SuperSplat - GitHub](https://github.com/playcanvas/super-splat)
- [Three.js WebGPU Renderer](https://threejs.org/docs/#api/en/renderers/WebGPURenderer)
- [Babylon.js 8.0 Release](https://doc.babylonjs.com/)

---

ご質問・ご相談はコメント欄へ。
