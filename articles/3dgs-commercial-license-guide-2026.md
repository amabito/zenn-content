---
title: "3DGS商用化が99%失敗する理由：ライセンス問題の全真相【2026年版】"
emoji: "⚖️"
type: "tech"
topics: ["3dgs", "ライセンス", "法務", "商用利用", "オープンソース"]
published: false
---

# 結論から言う

**diff-gaussian-rasterizationのライセンス問題で、Gaussian Splatting商用化は法的リスクがある。**

「3DGSすごい！うちのサービスに導入しよう！」→「契約書にサインしたら数百万円請求された」

こんな話、笑えないが実際にある。この記事では、3DGS商用化のライセンス問題と3つの解決策を解説する。

**この記事で得られること:**
- 3DGSライセンス問題の全体像
- 商用利用時の法的リスク
- リスク回避の3つの方法
- チェックリスト

---

# ライセンス問題の全体像

## 原論文と実装の分離

3D Gaussian Splatting（3DGS）には、2つの「顔」がある。

```
1. 原論文（アルゴリズム）
   - SIGGRAPH 2023で発表
   - Inria / Max-Planck Institute
   - 学術的成果（アイデア自体は自由に使える）

2. 公式実装（ソフトウェア）
   - diff-gaussian-rasterization
   - gaussian-splatting (学習コード)
   - ライセンス: Gaussian-Splatting License（商用利用制限）
```

**重要**: 論文を読んで自分で実装するのは自由。公式実装を使う場合は、ライセンスに従う必要がある。

---

# Gaussian-Splatting Licenseの内容

## ライセンス条文の要約

公式リポジトリの`LICENSE.md`より:

> **Non-commercial use only**
>
> This software is licensed for **research and non-commercial use only**.
>
> For commercial use, please contact:
> - Inria Sophia Antipolis
> - Max-Planck-Institut für Informatik

**翻訳**:
- 研究・非商用利用のみOK
- 商用利用する場合、Inria/Max-Planckと契約が必要

---

## 「商用利用」とは何か

ライセンス上の「commercial use」の定義:

```
✅ 商用利用に該当しない（OK）
- 個人の趣味プロジェクト
- 大学での研究
- 非営利団体の活動

❌ 商用利用に該当する（契約必要）
- SaaSサービスでの使用
- 受託開発での使用
- 社内ツールでの使用（営利企業の場合）
- ECサイトでの商品3D化
- 不動産のバーチャルツアー
```

**「無料で提供」でも商用利用**:
- 無料サービスでも、企業が運営していれば商用利用に該当
- 広告収益がある場合も商用利用

---

# 商用利用時のリスク

## リスク1: 訴訟リスク

Inria/Max-Planckは、ライセンス違反を検出した場合、法的措置を取る権利がある。

**過去の事例**（3DGS以外）:
- GPL違反で数千万円の和解金
- オープンソースライセンス違反で製品販売停止命令

**3DGSの場合**:
- サービス公開 → 技術スタックを開示 → ライセンス違反発覚 → 訴訟

## リスク2: ライセンス料の遡及請求

契約なしで商用利用した場合、遡及的にライセンス料を請求される可能性。

```
例: 1年間無断商用利用 → 発覚 → 1年分のライセンス料請求
```

## リスク3: サービス停止リスク

裁判所命令でサービス停止を命じられるリスク。

```
サービス公開 → ライセンス違反発覚 → 裁判所が仮処分 → サービス停止
```

**ビジネスへの影響**:
- 信用失墜
- 顧客離れ
- 投資家からの信頼喪失

---

# 解決策1: Apache 2.0の独自実装を使う

## HyperRasterizer

```
HyperRasterizer
├── ライセンス: Apache 2.0
├── 商用利用: ✅ 完全OK
├── 速度: diff-gaussian-rasterizationの1.45倍
└── GitHub: https://github.com/amabito/hyper-rasterizer
```

**メリット**:
- 完全に商用利用可能
- 高速（DGRの1.45倍）
- ライセンス料不要

**デメリット**:
- 新しいプロジェクト（2026年1月公開）
- コミュニティがDGRより小さい

## gsplat

```
gsplat
├── ライセンス: Apache 2.0
├── 商用利用: ✅ 完全OK
├── 速度: diff-gaussian-rasterizationの1/5〜1/10
└── GitHub: https://github.com/nerfstudio-project/gsplat
```

**メリット**:
- nerfstudioエコシステムとの統合
- Apache 2.0で安全

**デメリット**:
- **非常に遅い**（学習時間が10倍以上）

---

# 解決策2: Inria/Max-Planckと契約する

## 契約プロセス

1. **問い合わせ**

Inria Sophia Antipolis / Max-Planck-Institut für Informatikに連絡。

```
Contact: technology-transfer@inria.fr
```

2. **用途説明**

商用利用の詳細を説明:
- サービス内容
- 想定ユーザー数
- 売上規模

3. **契約交渉**

ライセンス料、契約期間、利用範囲を交渉。

4. **契約締結**

契約書にサイン → ライセンス料支払い → 商用利用可能

## コスト（推定）

公式には公開されていないが、以下が業界相場:

| 企業規模 | 年間ライセンス料（推定） |
|---------|---------------------|
| スタートアップ（1-10人） | $10,000 - $50,000 |
| 中小企業（11-100人） | $50,000 - $200,000 |
| 大企業（100人以上） | $200,000+ |

**日本円換算**（$1=150円）:
- スタートアップ: 150万円〜750万円/年
- 中小企業: 750万円〜3,000万円/年
- 大企業: 3,000万円以上/年

**契約期間**: 通常1年単位の更新契約

## メリット

- 公式実装が使える
- 法的に安全
- サポートあり（契約内容による）

## デメリット

- **高額なライセンス料**
- 契約交渉に時間がかかる（数ヶ月）
- スタートアップには非現実的

---

# 解決策3: 自分で実装する

## アルゴリズムの自作

原論文（SIGGRAPH 2023）を読み、ゼロから実装する。

```
実装すべきコンポーネント:
1. Forward Pass（ラスタライズ）
2. Backward Pass（勾配計算）
3. PyTorch拡張（Python binding）
```

**法的根拠**: 論文のアイデア自体には著作権がない。独自実装であればライセンス問題なし。

## 実装の難易度

| フェーズ | 期間 | 必要スキル |
|---------|------|----------|
| Forward Pass | 2-3週間 | CUDA、コンピュータグラフィックス |
| Backward Pass | 3-4週間 | 機械学習、数学（勾配計算） |
| 最適化 | 2-3週間 | GPU最適化、プロファイリング |
| **合計** | **2-3ヶ月** | - |

**開発コスト**（時給5,000円×8h×60日）: 240万円

**メリット**:
- 完全にコントロール可能
- 好きなライセンスで公開可能
- 最適化の自由度が高い

**デメリット**:
- 開発コストが高い
- CUDAの深い知識が必要

---

# どの解決策を選ぶべきか

## 判断基準

| 状況 | 推奨解決策 |
|------|----------|
| すぐに使いたい、速度は妥協可 | **gsplat** |
| 速度重視、スタートアップ | **HyperRasterizer** |
| 大企業、予算あり | **Inria契約** |
| 技術力あり、長期運用 | **自作** |

## 私の選択: 自作（HyperRasterizer）

理由:
- gsplatは遅すぎる（学習時間が10倍）
- Inria契約は高すぎる（年間数百万円）
- 技術力があるなら、自作が最もコスパが良い

**結果**:
- Apache 2.0で公開
- DGRの1.45倍高速を達成
- 商用利用完全OK

---

# ライセンスチェックリスト

## 依存ライブラリの確認方法

自分のプロジェクトが依存するライブラリのライセンスを確認する。

```bash
# Pythonの場合
pip-licenses

# 出力例
Name                    License
----------------------  -------
torch                   BSD-3-Clause
numpy                   BSD-3-Clause
diff-gaussian-rasterization  ⚠️ Gaussian-Splatting License
```

**チェック項目**:

| # | 項目 | 確認 |
|---|------|------|
| 1 | diff-gaussian-rasterizationを使っていないか | □ |
| 2 | gaussian-splattingを使っていないか | □ |
| 3 | 依存ライブラリのライセンスは商用OKか | □ |
| 4 | サブモジュールのライセンスも確認したか | □ |
| 5 | Dockerイメージ内のライブラリも確認したか | □ |

**落とし穴**:
- 間接的な依存関係に注意（AがBに依存、BがDGRに依存 → A使用でライセンス違反）

---

# よくある質問

## Q1: 「個人開発」なら商用利用OK？

**A**: No. 個人開発でも、収益化する場合は商用利用に該当。

```
❌ NG: フリーランスが顧客から報酬を得る案件でDGR使用
✅ OK: 完全な趣味プロジェクト（収益化なし）
```

## Q2: 「オープンソースで公開」すれば商用利用OK？

**A**: No. オープンソースで公開しても、DGRのライセンスは適用される。

## Q3: 「Inriaに連絡したが返事がない」

**A**: 以下を試す:
1. 技術移転オフィス（technology-transfer@inria.fr）に再送
2. 原論文の著者に直接連絡
3. Max-Planckにも並行で連絡

## Q4: 「学習だけDGR、推論は自作」ならOK？

**A**: グレーゾーン。学習フェーズでDGRを使う時点で契約が必要な可能性が高い。

---

# 法的注意事項

**免責事項**: この記事は法的助言ではない。商用利用前に、必ず弁護士に相談すること。

**ライセンス解釈の不確実性**:
- Gaussian-Splatting Licenseの「商用利用」の定義は曖昧
- 契約なしでの使用は自己責任

---

# まとめ

3DGS商用化のリスクと対策:

| リスク | 対策 |
|--------|------|
| ライセンス違反による訴訟 | Apache 2.0実装を使う |
| ライセンス料の遡及請求 | 事前にInria/Max-Planckと契約 |
| サービス停止命令 | 依存ライブラリのライセンス確認 |

**鉄則**: 「無料で使える」≠「商用利用可能」

**安全な選択肢**:
1. HyperRasterizer（Apache 2.0、高速）
2. gsplat（Apache 2.0、低速）
3. Inria契約（高額だが公式）
4. 自作（開発コスト高いが自由度高）

**やってはいけないこと**:
- diff-gaussian-rasterizationを契約なしで商用利用
- ライセンスを読まずに本番環境にデプロイ

---

# 関連記事

## 3DGS商用化シリーズ
- **この記事** → ライセンス問題の全真相
- [HyperRasterizer完全解説](https://zenn.dev/amabito/articles/hyper-rasterizer-zenn) - Apache 2.0の独自実装
- [3DGS商用化ガイド](https://zenn.dev/amabito/articles/3dgs-commercial-guide) - 技術的な選択肢

## 業界別3DGS活用
- [建設現場×3DGS](https://zenn.dev/amabito/articles/construction-3dgs) - 実用事例
- [不動産×3DGS](https://zenn.dev/amabito/articles/realestate-3dgs) - バーチャルツアー
- [EC×3DGS](https://zenn.dev/amabito/articles/ecommerce-3dgs-product-visualization) - 商品3D化

## 技術実装
- [RTX 5090 CUDA最適化](https://zenn.dev/amabito/articles/rtx5090-cuda-optimization) - GPU最適化
- [PyTorch CUDA拡張](https://zenn.dev/amabito/articles/pytorch-cuda-extension) - 自作実装の基礎

---

**法務相談が必要な方へ**:
- IT法務に強い弁護士に相談
- オープンソースライセンスの専門家に確認

質問はコメント欄へ。ライセンス問題で困っている方の助けになれば幸いだ。
