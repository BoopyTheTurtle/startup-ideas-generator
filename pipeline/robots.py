"""robots.txt matching per RFC 9309, including * and $ in paths.

urllib.robotparser ignores wildcards inside paths (it reads `Disallow: /*/rss/*` as a
literal prefix), so it reports blocked URLs as allowed.
"""

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

# Characters RFC 3986 calls unreserved; their percent-encodings are equivalent to them.
_UNRESERVED = re.compile(r"%([0-9A-Fa-f]{2})")


def _normalize(path: str) -> str:
    """Decode percent-encoded unreserved characters so /%7Ejoe matches /~joe."""
    def sub(m: re.Match) -> str:
        ch = chr(int(m.group(1), 16))
        return ch if ch.isalnum() or ch in "-._~" else m.group(0).upper()
    return _UNRESERVED.sub(sub, path)


@dataclass
class Group:
    agents: list[str] = field(default_factory=list)
    rules: list[tuple[bool, str]] = field(default_factory=list)  # (allow, pattern)


def parse(text: str) -> list[Group]:
    groups: list[Group] = []
    current: Group | None = None
    last_was_agent = False
    text = text.lstrip("﻿")
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = (p.strip() for p in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if current is None or not last_was_agent:
                current = Group()
                groups.append(current)
            current.agents.append(value.lower())
            last_was_agent = True
        elif key in ("allow", "disallow"):
            last_was_agent = False
            if current is None or not value:
                continue  # rules before any user-agent, or empty Disallow: ignore
            current.rules.append((key == "allow", _normalize(value)))
        # Other keys (Crawl-delay, Sitemap, ...) neither end nor start a group.
    return groups


def _pattern_regex(pattern: str) -> re.Pattern:
    anchored = pattern.endswith("$")
    body = pattern[:-1] if anchored else pattern
    regex = ".*".join(re.escape(part) for part in body.split("*"))
    return re.compile(regex + ("$" if anchored else ""))


def allowed(groups: list[Group], product: str, url: str) -> bool:
    """True if `product` (our user-agent token) may fetch `url`."""
    parts = urlsplit(url)
    path = _normalize((parts.path or "/") + (f"?{parts.query}" if parts.query else ""))
    if parts.path == "/robots.txt":
        return True
    product = product.lower()
    # Agent names match our product token exactly (case-insensitive), not as substrings.
    ours = [g for g in groups if product in g.agents]
    rules = [r for g in (ours or [g for g in groups if "*" in g.agents]) for r in g.rules]
    best: tuple[int, bool] | None = None  # (pattern length, allow)
    for allow, pattern in rules:
        if _pattern_regex(pattern).match(path):
            cand = (len(pattern), allow)
            # Longest match wins; on a tie, allow wins.
            if best is None or cand[0] > best[0] or (cand[0] == best[0] and allow):
                best = cand
    return True if best is None else best[1]
