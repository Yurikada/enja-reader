"""Offline unit tests (no Ollama needed): parsers, selection, quote stripping."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from enja_reader.__main__ import resolve_output
from enja_reader.parse import parse_html, parse_markdown
from enja_reader.select import assign_thresholds, difficulty_score
from enja_reader.translate import _strip_wrapping_quotes


def test_fence_length():
    md = "````\ncode with ``` inside\nstill code\n````\nafter"
    blocks = parse_markdown(md)
    assert blocks[0].kind == "code"
    assert "``` inside" in blocks[0].text
    assert blocks[1].kind == "paragraph" and blocks[1].text == "after"


def test_ordered_list():
    md = "1. first item\n2. second item\n- bullet"
    blocks = parse_markdown(md)
    assert [b.ordered for b in blocks] == [True, True, False]
    assert [b.number for b in blocks] == [1, 2, 0]
    assert all(b.kind == "list_item" for b in blocks)


def test_nested_list_levels():
    md = "1. parent one\n  - child bullet\n2. parent two\n3. parent three"
    blocks = parse_markdown(md)
    assert [(b.level, b.ordered, b.number) for b in blocks] == [
        (0, True, 1), (1, False, 0), (0, True, 2), (0, True, 3)]


def test_html_parse():
    html_doc = """
    <html><head><title>t</title><script>ignored()</script></head><body>
    <nav><p>skip me</p></nav>
    <h2>Heading</h2>
    <p>One sentence. Two sentences.</p>
    <ol><li>Ordered item</li></ol>
    <ul><li>Bullet item</li></ul>
    <blockquote><p>Quoted text.</p></blockquote>
    <pre>x = 1</pre>
    </body></html>
    """
    blocks = parse_html(html_doc)
    kinds = [(b.kind, b.text) for b in blocks]
    assert ("heading", "Heading") in kinds
    assert ("paragraph", "One sentence. Two sentences.") in kinds
    assert not any("skip me" in t for _, t in kinds)
    assert not any("ignored" in t for _, t in kinds)
    # head/title content must not leak into the document
    assert not any(t == "t" for _, t in kinds)
    ordered = [b for b in blocks if b.kind == "list_item"]
    assert [b.ordered for b in ordered] == [True, False]
    assert ("quote", "Quoted text.") in kinds
    assert ("code", "x = 1") in kinds


def test_html_block_boundaries():
    blocks = parse_html("<body><div>First.</div><div>Second.</div>"
                        "<blockquote>Direct quote text.</blockquote></body>")
    kinds = [(b.kind, b.text) for b in blocks]
    assert ("paragraph", "First.") in kinds
    assert ("paragraph", "Second.") in kinds
    assert not any("First.Second" in t.replace(" ", "") for _, t in kinds)
    assert ("quote", "Direct quote text.") in kinds


def test_output_collision():
    src = Path("doc.html")
    assert resolve_output(src, None).name == "doc.enja.html"
    assert resolve_output(src, "out/x.html").name == "x.html"
    try:
        resolve_output(src, "doc.html")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_strip_wrapping_quotes():
    assert _strip_wrapping_quotes("「こんにちは。」") == "こんにちは。"
    assert _strip_wrapping_quotes('"訳文です。"') == "訳文です。"
    # quotes that belong to the sentence must survive
    s = "「こんにちは」と彼は言った。"
    assert _strip_wrapping_quotes(s) == s


def test_thresholds():
    sents = ["The cat sat.", "Epistemological considerations notwithstanding, "
             "the phenomenological interpretation remains contentious."]
    h_hash = assign_thresholds(sents, "hash")
    assert all(0 <= h < 1 for h in h_hash)
    h_diff = assign_thresholds(sents, "difficulty")
    assert h_diff[1] < h_diff[0]  # harder sentence flips to JA first
    assert difficulty_score(sents[1]) > difficulty_score(sents[0])


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok {name}")
    print("all tests passed")
