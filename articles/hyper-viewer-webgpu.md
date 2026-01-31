---
title: "WebGPU対応3DGSビューア「HyperViewer」を公開した"
emoji: "🌐"
type: "tech"
topics: ["WebGPU", "3DGS", "TypeScript", "ビューア", "OSS"]
published: true
published_at: "2026-02-14 12:00"
---

# 結論から言う

**3D Gaussian Splatting（3DGS）をブラウザで表示できるWebGPUビューアを作って公開した。**

- **デモ**: https://amabito.github.io/hyper-viewer/
- **GitHub**: https://github.com/amabito/hyper-viewer
- **ライセンス**: Apache 2.0（商用利用可）

PLYファイルをドラッグ&ドロップするだけで、ブラウザ上で3DGSモデルをリアルタイムレンダリングできる。

---

# なぜ作ったか

## 課題：3DGSの表示が面倒

3D Gaussian Splattingモデルを表示するには、通常以下が必要:

```
従来の方法:
├── Python環境構築
├── PyTorch + CUDA インストール
├── diff-gaussian-rasterizerビルド
└── ビューアスクリプト実行

→ 環境構築だけで1時間以上
→ GPUがないと動かない
→ 他人に見せるのが大変
```

## 解決：ブラウザだけで表示

```
HyperViewer:
├── URLにアクセス
├── PLYファイルをドロップ
└── 表示される

→ インストール不要
→ スマホでも動く
→ URLを送るだけで共有可能
```

---

# 技術スタック

## WebGPU

```
WebGPU:
├── 次世代Web GPU API
├── Vulkan/Metal/D3D12のラッパー
├── WebGLより高速
└── 2023年にChrome正式サポート
```

**なぜWebGPUか:**
- 3DGSは大量のGaussianをレンダリングする必要がある
- WebGLでは性能が足りない
- WebGPUならネイティブに近い性能が出る

## ベース: Visionary

[Visionary](https://github.com/grgv/visionary)というWebGPU 3DGSビューアをフォークして開発。

| 項目 | 内容 |
|------|------|
| ライセンス | Apache 2.0 |
| 言語 | TypeScript |
| ビルド | Vite |

## HyperViewerの追加機能

| 機能 | 説明 |
|------|------|
| 日本語UI | デフォルト日本語、英語切替可 |
| デザイン刷新 | HyperRasterizerファミリー統一デザイン |
| GitHub Pages | 自動デプロイ（CI/CD） |
| ドロップゾーン改善 | フルスクリーン対応 |

---

# 対応フォーマット

| 形式 | 説明 |
|------|------|
| `.ply` | 3D Gaussian Splatting標準形式 |
| `.splat` | 圧縮Splat形式 |

---

# 使い方

## 1. オンラインデモ

1. https://amabito.github.io/hyper-viewer/ にアクセス
2. PLYファイルをドラッグ&ドロップ
3. マウスで操作

### 操作方法

| 操作 | アクション |
|------|----------|
| 左ドラッグ | 回転 |
| 右ドラッグ | パン |
| スクロール | ズーム |
| ダブルクリック | リセット |

## 2. ローカル実行

```bash
git clone https://github.com/amabito/hyper-viewer.git
cd hyper-viewer
npm install
npm run dev
# → http://localhost:5000/demo/simple/
```

## 3. 自分のサイトに組み込む

```bash
npm install hyper-viewer
```

```typescript
import { createViewer } from 'hyper-viewer';

const viewer = createViewer({
  container: document.getElementById('viewer'),
  language: 'ja'
});

viewer.loadPly('/path/to/model.ply');
```

---

# 性能

## ベンチマーク

| モデル | Gaussians | FPS |
|--------|-----------|-----|
| 小規模 | 10K | 68 |
| 中規模 | 100K | 45 |
| 大規模 | 500K | 20 |

※Chrome 130, RTX 5090, 1920x1080

## WebGPU vs WebGL

| API | 100K Gaussians |
|-----|----------------|
| WebGL | 8-12 FPS |
| **WebGPU** | **45 FPS** |

**WebGPUで約4倍高速。**

---

# デザイン

## HyperRasterizerファミリー

HyperViewer は [HyperRasterizer](https://github.com/amabito/hyper-rasterizer) ファミリーの一員。

| プロダクト | 説明 |
|-----------|------|
| HyperRasterizer | CUDA 3DGSラスタライザ（4169 FPS） |
| HyperSplat | 学習フレームワーク |
| **HyperViewer** | **WebGPUビューア** |

## 統一デザイン

```css
カラースキーム:
├── Primary: #00D4FF（シアン）
├── Background: #0a0e14（ダークネイビー）
└── Accent: #00ff88（グリーン）
```

---

# ブラウザ対応

## WebGPU対応状況（2026年1月）

| ブラウザ | 対応 |
|---------|------|
| Chrome 113+ | ✅ |
| Edge 113+ | ✅ |
| Firefox Nightly | ⚠️ フラグ有効化 |
| Safari 18+ | ✅ |

## 非対応ブラウザ

```
WebGPUに非対応のブラウザでは:
├── 警告メッセージを表示
└── 最新ブラウザへの更新を案内
```

---

# 開発の裏話

## 国際化（i18n）実装

```typescript
// src/i18n.ts
const translations = {
  ja: { 'app.title': 'HyperViewer', ... },
  en: { 'app.title': 'HyperViewer', ... }
};

function t(key: string): string {
  return translations[currentLang][key] || key;
}
```

**日本語をデフォルトにした理由:**
- 日本のユーザーが使いやすいように
- 言語切替は設定で可能

## GitHub Actions自動デプロイ

```yaml
# .github/workflows/deploy.yml
name: Deploy to GitHub Pages
on:
  push:
    branches: [main]
jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci && npm run build:demo
      - uses: peaceiris/actions-gh-pages@v4
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./dist-demo
```

mainブランチにpushすると自動でデプロイされる。

---

# 今後の予定

| 機能 | 優先度 |
|------|--------|
| モバイル最適化 | 高 |
| VR/AR対応 | 中 |
| 複数モデル同時表示 | 中 |
| アニメーション対応 | 低 |

---

# まとめ

| 項目 | 内容 |
|------|------|
| 名前 | HyperViewer |
| 機能 | ブラウザで3DGS表示 |
| 技術 | WebGPU + TypeScript |
| ライセンス | Apache 2.0 |
| デモ | https://amabito.github.io/hyper-viewer/ |

**3DGSの民主化に貢献したい。誰でも簡単に3Dモデルを見られる世界へ。**

---

# 関連記事

## HyperRasterizerシリーズ
- [HyperRasterizer完全解説](https://zenn.dev/amabito/articles/hyper-rasterizer-zenn) - 4169 FPS達成
- [3DGSを商用利用したい人へ](https://zenn.dev/amabito/articles/3dgs-commercial-guide) - ライセンス問題

## 技術シリーズ
- [GPUプログラミング入門](https://zenn.dev/amabito/articles/gpu-programming-intro) - CUDA基礎
- [RTX 5090でCUDA最適化](https://zenn.dev/amabito/articles/rtx5090-cuda-optimization) - Blackwell対応

---

:::message
**HyperViewer** は Apache 2.0 ライセンスで公開しています。
商用利用も可能です。ぜひ使ってみてください！

GitHub: https://github.com/amabito/hyper-viewer
:::
