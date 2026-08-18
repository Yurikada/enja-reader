# Why Reading in English Feels Hard

Reading a foreign language is not one skill but two skills stacked on top of each other. You must decode each sentence, and you must also hold the overall argument of the document in your head. When both tasks compete for attention, comprehension collapses.

## The core hypothesis

If the surrounding context is presented in your native language, the cost of understanding the document as a whole drops sharply. You can then spend your full attention on a single English sentence at a time. This is exactly how training wheels work: they remove one degree of freedom so you can practice the other.

Blended reading makes this trade-off adjustable. A learner starts with most sentences in Japanese and only a few in English. As reading becomes comfortable, the learner turns the knob and the ratio of English sentences increases. Eventually the document is entirely English, and the training wheels are gone.

## What the tool does

- It splits a document into sentences and translates each one locally.
- A slider controls how many sentences are displayed in Japanese.
- Clicking any sentence toggles its language instantly.

```python
ratio = 0.3  # 30% of sentences shown in Japanese
show_ja = sentence_hash(s) < ratio
```

> The goal is not translation. The goal is to lower the threshold between reading Japanese and reading English until the difference disappears.

Nobody learns to read English by avoiding English. But nobody enjoys reading when every sentence is a wall. The right difficulty is somewhere in between, and it is different for every reader and every document. That is why the ratio must be a knob, not a constant.
