# aikatsu-ime

アイカツ！シリーズのキャラクター名・声優名などを収録した、非公式のIME辞書です。

Microsoft IME / Google 日本語入力 (Mozc) / ATOK / macOS ユーザ辞書 に対応しています。

## ダウンロード

[Releases](https://github.com/aikatsukamen/aikatsu-ime/releases) から、使っているIME向けのzipを取得してください。

## 収録辞書

用途に応じて複数のバリエーションを用意しています。

| 辞書ID | 内容 |
| --- | --- |
| `names` | キャラクター名＋声優名。日常変換と衝突しやすい語は除外。**まずはこれを推奨** |
| `names-plus` | 上記＋姓のみ・短縮よみ |
| `characters` | キャラクター名のみ |
| `voice-actors` | 声優名のみ |
| `songs` | 楽曲名のみ |
| `full` | 全種別（衝突しやすい語は除外） |
| `full-all` | 全種別・全エントリ |
| `full-prefixed` | 全エントリのよみに `あか` を付けたもの。`あかほしみやいちご` のように打つ。日常変換を一切汚さないので、辞書のON/OFFができない環境向け |

## インストールと有効化・無効化

詳細な手順は [docs/install.md](docs/install.md) を参照してください。

**「執筆時だけ辞書を有効にしたい」** という用途については、IMEごとに事情が違います。

| IME | 辞書単位のON/OFF | 手順 |
| --- | --- | --- |
| Google 日本語入力 / Mozc | **できる** | 辞書ツールの一覧でユーザー辞書ごとにチェックを外す |
| ATOK | **できる** | 辞書ユーティリティで辞書セットから外す。変換モードに紐づけて切り替えることも可能 |
| Microsoft IME | 実質可能だが手間 | 使用するユーザー辞書ファイル(.dic)を設定画面で切り替える。ワンタッチではない |
| macOS ユーザ辞書 | **できない** | 一括削除しかない。`full-prefixed` の利用を推奨 |

ON/OFFの手軽さで言えば Google 日本語入力と ATOK が圧倒的に楽です。macOS や MS-IME で日常変換を汚したくない場合は、よみに接頭辞が付いた `full-prefixed` を入れておくのが実用的な回避策になります。

## データを追加・修正する

辞書の中身は `data/` 以下のCSVです。CSVを直せば辞書に反映されます。

```csv
reading,surface,pos,flags,note
ほしみやいちご,星宮いちご,person_full,,アイカツ！
```

| 列 | 内容 |
| --- | --- |
| `reading` | よみ。**ひらがなのみ**（MS-IMEがそれ以外を弾くため） |
| `surface` | 変換後の単語。記号や英数字を含んでよい |
| `pos` | 中間品詞。空欄ならカテゴリの既定値が使われる |
| `flags` | `;` 区切りのフラグ。辞書バリエーションの絞り込みに使う |
| `note` | 備考。Google 日本語入力のコメント欄に入る |

### 中間品詞

| 中間品詞 | Google | MS-IME | ATOK |
| --- | --- | --- | --- |
| `person_full` | 人名 | 人名 | 人名 |
| `person_last` | 姓 | 姓 | 姓 |
| `person_first` | 名 | 名 | 名 |
| `org` | 組織 | 組織 | 固有名詞 |
| `proper_noun` | 固有名詞 | 固有名詞 | 固有名詞 |
| `noun` | 名詞 | 名詞 | 名詞 |

対応表は `src/build.py` の `POS_MAP` 1か所にまとまっています。変換結果が気に入らなければここだけ直せば全形式に反映されます。

### フラグ

| フラグ | 意味 |
| --- | --- |
| `ambiguous` | 日常変換と衝突しやすい（`いちご`、`すみれ` など） |
| `alias` | 短縮よみ・略称 |
| `surname` | 姓のみのエントリ |

### 種別（カテゴリ）を追加する

1. `data/<新しい種別>.csv` を作る（ヘッダは既存と同じ）
2. `config/categories.json` に1エントリ追加する
3. 必要なら `config/dictionaries.json` に専用の辞書バリエーションを足す

`categories` に `["*"]` を指定している辞書（`full` など）には自動で含まれます。ビルドスクリプトの変更は不要です。

### 辞書バリエーションを追加する

`config/dictionaries.json` に追記するだけです。

```json
{
  "id": "songs-and-brands",
  "label": "楽曲・ブランド",
  "description": "楽曲名とブランド名のみ",
  "categories": ["songs", "brands"],
  "exclude_flags": ["ambiguous"]
}
```

## ローカルでビルドする

Python 3.10 以降。追加パッケージは不要です。

```bash
python src/validate.py            # データの検証
python src/build.py               # dist/ に全形式を出力
python src/build.py --dict full --format google   # 部分ビルド
```

## リリース

タグを打つと GitHub Actions が形式ごとのzipを作って Release に添付します。

```bash
git tag v0.1.0
git push origin v0.1.0
```

## 注意事項

- 初期データは動作確認用のサンプルです。網羅性・正確性は保証されません。誤りを見つけたら Issue か Pull Request をお願いします。
- ATOK の品詞名は製品バージョンによって受け付ける値が異なる可能性があります。取り込み時にエラーが出る場合は Issue で報告してください。
- ATOK 向けは Shift_JIS 版と UTF-8 版の両方を出力しています。片方で読めない場合はもう片方を試してください。

## ライセンス

コードおよび辞書データは [MIT License](LICENSE) です。

本リポジトリは非公式のファンプロジェクトであり、権利者とは一切関係ありません。作品および登場人物に関する権利は各権利者に帰属します。
