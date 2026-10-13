"""Plain text from stored item bodies, for extraction and quote checking."""

import html
import re
from html.parser import HTMLParser

_BLOCK = {"p", "div", "br", "li", "ul", "ol", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
          "blockquote", "pre", "table", "section", "article", "hr"}
_SKIP = {"script", "style"}


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self.skip += 1
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP and self.skip:
            self.skip -= 1
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def plain_text(body: str) -> str:
    """HTML or plain body -> readable plain text with collapsed whitespace."""
    if "<" in body and ">" in body:
        p = _Text()
        p.feed(body)
        p.close()
        text = "".join(p.parts)
    else:
        text = html.unescape(body)
    text = re.sub(r"[ \t\r\f\v ]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def find_quote(text: str, quote: str) -> tuple[int, int] | None:
    """Offsets of `quote` in `text`, tolerant of whitespace and case differences.

    Returns None when the quote is not in the text: the extraction is then ungrounded.
    """
    q = _norm(quote)
    if len(q) < 8:
        return None
    i = text.find(quote)
    if i >= 0:
        return i, i + len(quote)
    # Map whitespace-normalized positions back to the original text.
    flat, index = [], []
    prev_space = False
    for pos, ch in enumerate(text):
        if ch.isspace():
            if prev_space:
                continue
            flat.append(" ")
            prev_space = True
        else:
            flat.append(ch)
            prev_space = False
        index.append(pos)
    hay = "".join(flat)
    for h, n in ((hay, q), (hay.lower(), q.lower())):
        j = h.find(n)
        if j >= 0:
            return index[j], index[j + len(n) - 1] + 1
    return None
