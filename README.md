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

## ロードマップ

1. ~~v0.1: ローカルMarkdown → 自己完結HTMLビューア~~
2. **v0.2 (今ここ)**: HTML入力、難易度ベースの文選択、ビューアJS/CSSの分離(拡張移植準備)
3. v0.3: 訳質向上(モデル比較・用語集・文体一貫性)、PDF入力
4. v1.0: Chrome拡張 — content scriptでページ本文を文分割し、localhostのOllamaへ翻訳リクエスト(`OLLAMA_ORIGINS`でCORS許可)。`enja_reader/assets/viewer.js` のロジックをそのまま移植

## 依存

- Python 3.10+ / `pysbd` (文分割)
- Ollama (localhost:11434)
