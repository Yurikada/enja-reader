# enja-reader

英語ドキュメントを**文単位で英語/日本語切替可能**なHTMLに変換するツール。

仮説: 文脈把握の負担を母語(日本語)側に逃がすことで、一文単位では英語を英語のまま理解する練習ができ、日本語読解と英語読解の間の敷居が下がる。

## 構成

- 翻訳は**ビルド時に一度だけ**、ローカルLLM (Ollama) で文単位に実行し、SQLiteにキャッシュする。
- 混成比率は出力HTML内の**ノブ(スライダー)でリアルタイム切替**。LLM呼び出しは発生しない。
- 文の日英選択は文ハッシュのしきい値方式。ノブを上げると日本語文が単調に増え、表示が安定する。
- 文クリックで個別トグル、ホバーで対訳ツールチップ。

## 使い方

```
ollama serve   # 起動していなければ
python -m enja_reader build samples/attention.md -o out/attention.html --model gemma2 --ratio 30 --select difficulty
```

- `--model`: Ollamaモデル名 (既定 `gemma2`)
- `--ratio`: 初期日本語比率 0-100 (既定 30)
- `--select`: どの文から日本語化するか。`hash`=安定ランダム(既定) / `difficulty`=難しい文から
- `--cache`: 翻訳キャッシュのパス (既定 `.cache/translations.sqlite`)

対応入力: Markdown / プレーンテキスト / HTML (`.html`/`.htm` は自動判別)。コードブロックは翻訳対象外。

## テスト

```
python tests/test_core.py
```

Ollama不要のオフラインテスト(パーサ・文選択・引用符処理)。

## モデル・プロンプト評価 (`eval/compare.py`)

```
python eval/compare.py --configs gemma2:base gemma2:fewshot2 qwen2.5:7b:fewshot2
```

サンプル26文を各構成で翻訳し、です・ます混入率 / 英語残り / メタ文 / 非日本語文字混入 / 長さ外れ値 / 速度を計測して `eval/report.html` に対訳表を出力する。

2026-08-18 の結果 (RTX 4060 Ti 8GB):

| 構成 | です・ます混入 | 非日本語文字 | 速度 | 備考 |
|---|---|---|---|---|
| gemma2:9b + few-shot | **0%** | **0%** | 0.31文/s | **既定に採用** |
| qwen2.5:7b + few-shot | 3.8% | 7.7% (ロシア語) | 0.36文/s | 意訳過多・混入あり |

few-shot例(特に「X, not Y」構文)の追加で両モデルとも否定構文の誤訳が解消。見出しは体言止めヒントをプロンプトに付与する。

## Chrome拡張 (`extension/`)

任意の英語ページを、その場で文単位の英日混成表示にする。

**導入**: `chrome://extensions` → デベロッパーモードON → 「パッケージ化されていない拡張機能を読み込む」で `extension/` を選択。ツールバーのアイコンをクリックで有効化、再クリックで解除(元のページに完全復元)。

**翻訳バックエンド** (自動選択):

1. **Chrome内蔵 Translator API** (既定、Chrome 138+) — オンデバイス翻訳。セットアップ不要・ほぼ瞬時。初回のみ言語パックが自動DLされる
2. **Ollama** (品質モード) — だ・である統一のLLM翻訳。`OLLAMA_ORIGINS=chrome-extension://*` を環境変数に設定して `ollama serve` を起動しておく

`chrome.storage.sync` の `backend` (`auto`/`chrome`/`ollama`)、`select` (`hash`/`difficulty`)、`ratio`、`model` で挙動を変更できる(設定UIは今後)。

**ロジック検証**: `extension/test/harness.html` をHTTPサーバ経由で開くと、モックTranslatorでcontent scriptの全動作(抽出・分割・混成・トグル・復元)を確認できる。

## ロードマップ

1. ~~v0.1: ローカルMarkdown → 自己完結HTMLビューア~~
2. ~~v0.2: HTML入力、難易度ベースの文選択、ビューアJS/CSSの分離~~
3. ~~v0.3: 訳質向上 — few-shotプロンプト・見出し体言止め・モデル比較ハーネス~~
4. **v1.0 (今ここ)**: Chrome拡張 — Chrome内蔵Translator API既定+Ollama品質モードのハイブリッド
5. 今後: 設定ポップアップUI、訳キャッシュ永続化、用語集、PDF入力

## 依存

- Python 3.10+ / `pysbd` (文分割)
- Ollama (localhost:11434)
