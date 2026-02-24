---
title: "HackerNewsカルマを安全に育てる戦略（低カルマアカウント向け）"
emoji: "📈"
type: "idea"
topics: ["hackernews", "コミュニティ", "英語", "ライティング"]
published: true
published_at: "2026-03-01 21:00"
---

## HNに存在する静かな壁

HackerNewsには公式には書いていないルールがある。

低カルマアカウントのコメントは、他のユーザーに見えないことがある。「shadowban」と呼ばれる状態で、自分では気づきにくい。

ログアウトして自分のコメントを確認する。表示されていなければshadowbanned。

---

## shadowbanのトリガー（推測）

明文化されていないが、経験則で分かっていること：

- 政治的トピックへの初コメント
- 新規アカウントでのアップボート集中
- 「Great point!」「Interesting!」系の薄いコメント
- 24時間以内に大量コメント
- ドメイン名ベアラー（自分のサービスへのリンク連投）

逆に安全なのは：
- 技術的な具体性があるコメント
- 個人的な経験に基づく話
- 反論でも根拠があるもの

---

## カルマが育つコメントの特徴

HNで伸びるコメントには共通パターンがある。

### パターン1: 「私もそれで詰まった」型

```
I spent three days debugging the same issue.
The key was [specific technical detail].
Ended up using [alternative approach] which was
significantly faster in our case.
```

「詰まった → 解決策 → 定量的な結果」の構造。

### パターン2: 「業界の内側から」型

```
Having worked on this for ~5 years, the thing
that's rarely discussed is [specific insight].
[Concrete example].
```

年数はざっくりでいい。「~5 years」「a few years」。断言しすぎない。

### パターン3: 反論だが建設的型

```
This assumes [specific assumption], but in
[edge case], the opposite is true.
[Concrete example or data].
```

反論は歓迎されるが、「You're wrong」だけでは死ぬ。根拠が必要。

---

## 「AI感ゼロ」コメントの書き方

AIが書いたコメントはHNで即死する。レーダーに引っかかる特徴：

- 完璧な文法と構造
- 「Furthermore,」「In conclusion,」の多用
- 感情がない、個人的体験がない
- 箇条書きが多い

人間らしくする技術：

```
# NG（AI感あり）
This is an excellent article. The approach described
demonstrates several key advantages:
- Improved performance
- Better maintainability
- Enhanced security

# OK（人間感あり）
yeah this is basically what we ended up with after
trying [alternative] for six months. the maintenance
overhead wasn't worth it. though I'd argue [nuance].
```

ポイント：
- 小文字で始めることもある
- 「yeah」「honestly」「tbh」は自然
- 曖昧な数字（「six months」「a few dozen」）の方が信頼される
- 完全な文じゃなくていい

---

## スレッド選びの基準

コメントするスレッドを選ぶ基準：

**コメントに向いているスレッド:**
- コメント数20〜50（競争が少なく埋もれにくい）
- 技術的なトピック（CUDAとか、言語設計とか）
- 投稿から1〜3時間以内（ピーク前）

**避けた方がいいスレッド:**
- コメント数300以上（埋もれる）
- 政治・AI倫理・労働問題（地雷原）
- 「Show HN」の本人が即レスしている（プレッシャーがある）

---

## 投稿タイミング

HNは米国西海岸時間で動いている。

**ベストタイム:** 平日8〜9時PST = 日本時間 深夜0〜1時（翌日）

深夜に投稿して、起きたらアメリカ昼が盛り上がっている状態にする。

---

## 記事を投稿する場合

自分の記事を投稿するのは基本的に大丈夫だが：

- タイトルをそのまま使わず、HN向けに調整する
- 「Show HN:」プレフィックスはデモがある場合のみ
- コメントで自分が著者であることを最初に書く（「I wrote this. Happy to answer questions.」）

clickbait感のあるタイトルは即死。

```
# NG
I Made $100K Using This Simple AI Trick

# OK
Optimizing 3DGS rendering with CUDA shared memory tricks
```

---

## カルマが100を超えるまで

低カルマ期（〜100）は特に慎重に。

ルール：
- 1日3コメントまで
- 政治・AI倫理スレッドは無視
- 反論するときは具体的な技術的根拠をつける
- 「Great post」「Interesting perspective」は絶対言わない

100を超えると少し余裕が出る。shadowbanリスクが下がる。

---

## 実際にやって効いた例

3DGSのレンダリング最適化についての記事が出たとき、こういうコメントをした：

```
We hit a similar wall with tile-based culling.
The key insight was that sorting by (tile, depth)
rather than just depth cuts the cache miss rate
significantly - in our case from ~40% to ~8%.

Main tradeoff is you need to sort per-frame, but
with a counting sort on the tile dimension it's
fast enough at 1080p.
```

具体的な数字、個人的な経験、トレードオフへの言及。これが伸びる。

「タイルベースのカリングでも同じ壁にあたった」という書き出しが重要。「私も」という共感から入る。

---

## 諦めていいこと

HNで伸びなくても、それは内容が悪いわけじゃない。

- タイミングが悪かった（深夜や週末）
- スレッドがすでに盛り上がっていた
- アルゴリズムの気まぐれ

一つのコメントに執着せず、続けることが大事。

カルマは徐々に積み上がる。急がない。

---

## まとめ

- shadowbanは実在する。ログアウトして自分のコメントを定期確認
- 技術的・個人的経験ベースのコメントが安全
- AI感はすぐバレる。構造を崩し、曖昧な数字を使い、個人的体験を入れる
- スレッドは20〜50コメントの技術系を狙う
- 投稿時間：平日8〜9時PST（日本時間深夜〜翌朝）
- 低カルマ期は1日3コメントまで、政治スレッド回避
