---
title: "WebGPU 2026最新動向：70%ブラウザサポート・15倍高速化の衝撃"
emoji: "🚀"
type: "tech"
topics: ["WebGPU", "WebGL", "3D", "GPU", "ブラウザ"]
published: true
---

# 結論から言う

**2026年、WebGPUはFirefox 147（1月13日）、Safari（iOS 26/macOS Tahoe）の対応により、全主要ブラウザで利用可能になった。** グローバルカバレッジ70%到達、15-30倍のパフォーマンス向上、コンピュートシェーダーによる新たなアルゴリズムの実現。WebGLの時代は終わった。

**対象読者:**
- Webで3Dグラフィックス・GPUコンピューティングを使う人
- Three.js・Babylon.js等のフレームワーク利用者
- WebGLから移行を検討している人

**この記事で得られること:**
- WebGPU 2026年のブラウザサポート状況
- WebGLとの具体的なパフォーマンス比較
- 移行の実装ポイントとハマりどころ

---

## WebGPUの2026年ブラウザサポート状況

### 主要ブラウザの対応状況

| ブラウザ | 対応バージョン | リリース日 | 対応OS |
|---------|--------------|----------|--------|
| **Chrome** | 113以降 | 2023年5月 | Windows, macOS, Linux, Android |
| **Edge** | 113以降 | 2023年5月 | Windows, macOS |
| **Firefox** | **147以降** | **2026年1月13日** | Windows, ARM64 macOS |
| **Safari** | **iOS 26/iPadOS 26/macOS Tahoe** | **2026年** | Apple製品全般 |

### グローバルカバレッジ

```
2024年10月: 約70%
2026年1月: 推定75-80%（Firefox・Safari対応後）
```

**内訳:**

- デスクトップ: 85-90%
- モバイル: 65-70%（Android優勢、iOSは2026年から）
- 中国: 低め（Chromiumベースブラウザの対応状況に依存）

---

## パフォーマンス比較：WebGPU vs WebGL

### ベンチマーク結果

| ベンチマーク | WebGL 2 | WebGPU | 倍率 |
|------------|---------|--------|------|
| **パーティクル（10万個）** | 5 FPS | 60+ FPS | **12倍** |
| **パーティクル（100万個）** | 不可能（クラッシュ） | 60+ FPS | **∞** |
| **物理シミュレーション** | 30 FPS | 60 FPS | **2倍** |
| **データ可視化（100万点）** | 10 FPS | 60+ FPS | **6倍** |
| **Compute（AI推論）** | 不可能 | 60+ FPS | **N/A** |

### Babylon.js Snapshot Rendering

```
通常レンダリング（WebGL）: 10 FPS
GPU Render Bundles（WebGPU）: 100+ FPS
```

**10倍高速化**を実現。

---

## WebGPUの3大アドバンテージ

### 1. Compute Shaders（計算シェーダー）

**WebGLとの決定的な違い:**

WebGLはグラフィックスAPI → 計算専用の処理が不可能

WebGPU は Graphics + **Compute** API → GPUを汎用計算に使える

**使用例:**

| 用途 | WebGL | WebGPU |
|------|-------|--------|
| **物理シミュレーション** | CPU or 疑似GPU | GPUで並列計算 |
| **AIモデル推論** | 不可能 | 可能（ONNX Runtime Web等） |
| **パーティクル更新** | JavaScript or VertexShader hack | ComputeShader |
| **画像処理（フィルタ等）** | FragmentShader hack | ComputeShader |

**実装例（パーティクル更新）:**

```javascript
// WebGL: JavaScript or 複雑なシェーダーハック
for (let i = 0; i < particles.length; i++) {
  particles[i].velocity += gravity * dt;
  particles[i].position += particles[i].velocity * dt;
}

// WebGPU: Compute Shader
// WGSL（WebGPU Shading Language）
@compute @workgroup_size(64)
fn update_particles(@builtin(global_invocation_id) id: vec3<u32>) {
  let idx = id.x;
  particles[idx].velocity += gravity * dt;
  particles[idx].position += particles[idx].velocity * dt;
}
```

GPUの並列実行で**100倍以上の高速化**。

---

### 2. モダンGPUアーキテクチャへの対応

| 機能 | WebGL | WebGPU |
|------|-------|--------|
| **Vulkan/Metal/DirectX12対応** | ❌ | ✅ |
| **バインドレステクスチャ** | 限定的 | ✅ |
| **非同期コンピュート** | ❌ | ✅ |
| **メモリバリア制御** | ❌ | ✅ |

**実世界の影響:**

- RTX 4090・RTX 5090の性能を引き出せる
- Apple Silicon（M1/M2/M3）の統合メモリを活用
- AMD RDNA3の並列実行ユニットを活用

---

### 3. API設計の明快さ

**WebGLの悪名高い問題:**

```javascript
// WebGL: 状態機械（state machine）地獄
gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
gl.bindTexture(gl.TEXTURE_2D, texture);
gl.activeTexture(gl.TEXTURE0);
gl.bindBuffer(gl.ARRAY_BUFFER, vbo);
// どのバッファが何にバインドされているか把握困難
```

**WebGPUの解決:**

```javascript
// WebGPU: 明示的なオブジェクト管理
const renderPass = encoder.beginRenderPass({
  colorAttachments: [{
    view: texture.createView(),
    loadOp: 'clear',
    storeOp: 'store'
  }]
});
renderPass.setPipeline(pipeline);
renderPass.setBindGroup(0, bindGroup);
renderPass.draw(vertexCount);
```

**利点:**

- デバッグが容易
- マルチスレッド対応（複数のエンコーダーを並列作成可能）
- エラーが明示的

---

## 移行のポイント：Three.jsの場合

### 2行で移行完了

```javascript
// WebGL（従来）
import * as THREE from 'three';
const renderer = new THREE.WebGLRenderer();

// WebGPU（2行変更）
import * as THREE from 'three';
import WebGPU from 'three/addons/capabilities/WebGPU.js';
import WebGPURenderer from 'three/addons/renderers/webgpu/WebGPURenderer.js';

const renderer = new WebGPURenderer();
```

**自動フォールバック:**

```javascript
// WebGPU非対応ブラウザ → 自動的にWebGL 2
const renderer = WebGPU.isAvailable()
  ? new WebGPURenderer()
  : new THREE.WebGLRenderer();
```

### Three.jsの対応状況

| バージョン | WebGPU対応 |
|----------|-----------|
| **r171以降** | ✅ 正式サポート |
| r160-r170 | 実験的サポート |
| r159以前 | ❌ 未対応 |

**週間ダウンロード数:** 270万（2026年1月時点）

---

## 実世界のユースケース

### 1. 大規模パーティクルシステム

**Before（WebGL）:**

```
10万パーティクル → 15 FPS（ギリギリ）
100万パーティクル → クラッシュ
```

**After（WebGPU）:**

```
100万パーティクル → 60 FPS
1000万パーティクル → 30 FPS
```

**実装例:**

```javascript
// Compute Shaderでパーティクル更新
const computePipeline = device.createComputePipeline({
  compute: {
    module: shaderModule,
    entryPoint: 'update_particles'
  }
});

// 毎フレーム実行
const encoder = device.createCommandEncoder();
const pass = encoder.beginComputePass();
pass.setPipeline(computePipeline);
pass.dispatchWorkgroups(Math.ceil(particleCount / 64));
pass.end();
```

---

### 2. リアルタイム物理シミュレーション

**流体シミュレーション（SPH）:**

WebGLでは不可能だった流体シミュレーションが、WebGPUのComputeShaderで実現。

```javascript
// 密度計算 → 圧力計算 → 力計算 → 位置更新
// 全てComputeShaderで並列実行
```

**事例:**

- 建設シミュレーション（水流・土砂）
- ゲーム（水・煙・爆発）
- 教育コンテンツ（物理演示）

---

### 3. AI/ML推論

**ONNX Runtime Web + WebGPU:**

```javascript
// 画像分類モデル（ResNet-50）
const session = await ort.InferenceSession.create(
  'resnet50.onnx',
  { executionProviders: ['webgpu'] }
);

// WebGL: 200ms/画像
// WebGPU: 50ms/画像（4倍高速）
```

**用途:**

- リアルタイム物体検出
- 画像生成（Stable Diffusion on Web）
- 音声認識

---

## ハマりどころと対策

### 1. Safari（iOS）の制限

| 制限 | 詳細 | 回避策 |
|------|------|--------|
| **ストレージ制限** | バッファサイズ上限が小さい | 分割処理 |
| **ComputeShader制限** | 一部の機能が未実装 | フィーチャー検出 |
| **デバッグツール** | Chrome DevToolsより貧弱 | 外部デバッガー使用 |

---

### 2. シェーダー言語の違い

| 言語 | API | 学習曲線 |
|------|-----|----------|
| **GLSL** | WebGL | 低（資料多い） |
| **WGSL** | WebGPU | 中（資料少ない） |

**移行ツール:**

- Tint（Google製GLSL→WGSL変換器）
- Three.jsの自動変換

---

### 3. 非同期API

WebGPUは**完全非同期**。

```javascript
// WebGL: 同期
const texture = gl.createTexture();
gl.bindTexture(gl.TEXTURE_2D, texture);

// WebGPU: 非同期
const texture = await device.createTexture({...});
```

**対策:**

```javascript
async function init() {
  const adapter = await navigator.gpu.requestAdapter();
  const device = await adapter.requestDevice();
  // 以降の処理
}
```

---

## 誰に影響があるか

| ユースケース | 影響度 | 理由 |
|------------|--------|------|
| **3Dゲーム（Web）** | 最高 | パフォーマンス2-10倍 |
| **データ可視化** | 最高 | 100万点以上の表示が可能に |
| **CAD・BIM（Web）** | 高 | 複雑なモデルの表示高速化 |
| **AI/ML推論** | 高 | ブラウザでGPU推論が実用的に |
| **教育コンテンツ** | 中 | 物理シミュレーション等 |

---

## WebGLはいつまで使えるか

### 現実的な判断

```
2026年: WebGPU本格普及開始
2027-2028年: 新規プロジェクトはWebGPU推奨
2030年以降: WebGL非推奨化の可能性
```

**移行タイミング:**

| プロジェクト | 推奨行動 |
|------------|---------|
| **新規** | WebGPU一択（WebGLフォールバック付き） |
| **既存（小〜中規模）** | 2026-2027年に移行 |
| **既存（大規模）** | 段階的移行（新機能のみWebGPU） |
| **レガシー** | WebGLのまま（メンテナンスモード） |

---

## まとめ

| 項目 | 詳細 |
|------|------|
| **ブラウザサポート** | Chrome/Edge/Firefox/Safari全対応（2026年） |
| **パフォーマンス** | WebGL比で2-30倍高速化 |
| **新機能** | ComputeShader、モダンGPU対応 |
| **移行コスト** | Three.js等では数行（ゼロから書く場合は学習コスト中） |
| **推奨開始時期** | 今すぐ（2026年） |

WebGPUの時代が来た。Webで「ネイティブアプリ並み」のグラフィックスとGPUコンピューティングが現実になる。

---

## 関連記事

- [無料] [HyperViewer：WebGPU 3DGSビューア実装](https://zenn.dev/amabito/articles/hyper-viewer-webgpu) - WebGPU実装例
- [無料] [WebGPU vs WebGL比較](https://zenn.dev/amabito/articles/webgpu-vs-webgl) - 詳細な技術比較
- [無料] [3DGSストリーミング配信](https://zenn.dev/amabito/articles/3dgs-streaming) - Web配信の実践
- [無料] [Three.js 2026最新動向](https://www.utsubo.com/blog/threejs-2026-what-changed) - Three.jsのWebGPU対応

---

## 参考

- [WebGPU API - MDN](https://developer.mozilla.org/en-US/docs/Web/API/WebGPU_API) - 公式リファレンス
- [WebGPU Supported in Major Browsers](https://web.dev/blog/webgpu-supported-major-browsers) - Google発表
- [Firefox 147 WebGPU対応](https://videocardz.com/newz/webgpu-is-now-supported-by-all-major-browsers) - リリース情報
- [Three.js WebGPU Examples](https://threejs.org/examples/?q=webgpu) - 実装例
- [WebGPU Fundamentals](https://webgpufundamentals.org/) - 学習リソース

---

ご質問・ご相談はコメント欄へ。
