"""Plain text from stored item bodies, for extraction and quote checking."""

import html
import re
import unicodedata
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


MIN_QUOTE_CHARS = 15  # the extraction prompt asks for 15-300 characters

# Typographic variants a model tends to straighten (or curl) when it copies a quote.
_PUNCT = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
    "‹": "'", "›": "'", "ʼ": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"',
    "«": '"', "»": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-",
}


def _segments(s: str):
    """Yield (start, end) of each base character plus the combining marks after it."""
    start = 0
    for i in range(1, len(s) + 1):
        if i == len(s) or not unicodedata.combining(s[i]):
            yield start, i
            start = i


def _normalize(s: str) -> tuple[str, str, list[int], list[int]]:
    """Normalize `s` for quote matching, keeping a map back to the original offsets.

    Each segment is NFC-composed; typographic quotes and dashes become plain ones;
    whitespace runs (non-breaking spaces included) become one space. Returns the
    case-preserving form, a casefolded form of the same length, and for each normalized
    character the start and end offset of the original text it came from. A character
    whose casefold is longer than one character (e.g. 'ß') keeps its original form, so
    both forms stay aligned with the maps.
    """
    keep, folded, starts, ends = [], [], [], []
    prev_space = False
    for a, b in _segments(s):
        for ch in unicodedata.normalize("NFC", s[a:b]):
            ch = _PUNCT.get(ch, ch)
            if ch.isspace():
                if prev_space:
                    ends[-1] = b
                    continue
                ch, prev_space = " ", True
            else:
                prev_space = False
            cf = ch.casefold()
            keep.append(ch)
            folded.append(cf if len(cf) == 1 else ch)
            starts.append(a)
            ends.append(b)
    return "".join(keep), "".join(folded), starts, ends


def find_quote(text: str, quote: str) -> tuple[int, int] | None:
    """Offsets of `quote` in `text`, tolerant of whitespace, case, Unicode normalization
    (NFC/NFD), and curly versus straight quotes.

    Returns None when the quote is shorter than MIN_QUOTE_CHARS or not in the text: the
    extraction is then ungrounded.
    """
    q_keep, q_fold, _, _ = _normalize(quote)
    q_keep, q_fold = q_keep.strip(), q_fold.strip()
    if len(q_keep) < MIN_QUOTE_CHARS:
        return None
    stripped = quote.strip()
    i = text.find(stripped)
    if i >= 0:
        return i, i + len(stripped)
    h_keep, h_fold, starts, ends = _normalize(text)
    for hay, needle in ((h_keep, q_keep), (h_fold, q_fold)):
        j = hay.find(needle)
        if j >= 0:
            return starts[j], ends[j + len(needle) - 1]
    return None


def copied_span(text: str, s: str, window: int = 40) -> bool:
    """True when `s` repeats source text: all of it (at least MIN_QUOTE_CHARS) or any run
    of `window` normalized characters. Used to keep no-retain sources' words out of the
    derived fields."""
    if find_quote(text, s) is not None:
        return True
    needle = _normalize(s)[1].strip()
    if len(needle) < window:
        return False
    hay = _normalize(text)[1]
    return any(needle[i:i + window] in hay for i in range(len(needle) - window + 1))
