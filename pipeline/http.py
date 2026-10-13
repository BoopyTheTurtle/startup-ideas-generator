"""HTTP for collectors: polite defaults, retries, robots.txt, and record/replay.

SIG_HTTP selects the mode:
  live   (default) real requests
  record real requests, each response saved under tests/fixtures/<collector>/
  replay responses served from those fixtures; a missing fixture is an error

Tests run in replay mode, so the suite never touches the network.
"""

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx

from pipeline import robots
from pipeline.db import ROOT

PRODUCT = "startup-ideas-generator"
USER_AGENT = (
    f"{PRODUCT}/0.1 "
    "(+https://github.com/BoopyTheTurtle/startup-ideas-generator)"
)
FIXTURES = ROOT / "tests" / "fixtures"


class FixtureMissing(RuntimeError):
    pass


class RobotsDisallowed(RuntimeError):
    pass


class RateLimited(RuntimeError):
    """The source asked us to wait longer than one run can afford."""


MAX_RETRY_AFTER_S = 120


class Response:
    """The subset of a response collectors use; identical in live and replay."""

    def __init__(self, url: str, status: int, content_type: str, text: str):
        self.url = url
        self.status_code = status
        self.content_type = content_type
        self.text = text

    def json(self) -> Any:
        return json.loads(self.text)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code} for {self.url}",
                request=httpx.Request("GET", self.url),
                response=httpx.Response(self.status_code),
            )


_XML_DECL = re.compile(rb"""^\s*<\?xml[^>]*encoding=["']([A-Za-z0-9._-]+)["']""")


def _decode(r: httpx.Response) -> str:
    """Text of a response. Without a charset in Content-Type, httpx falls back to UTF-8,
    which garbles feeds declared as e.g. ISO-8859-1; honour the XML declaration then."""
    if "charset=" not in r.headers.get("content-type", "").lower():
        m = _XML_DECL.match(r.content[:200])
        if m:
            try:
                return r.content.decode(m.group(1).decode(), errors="replace")
            except LookupError:
                pass
    return r.text


def _key(method: str, url: str, params: dict | None, body: Any) -> str:
    raw = json.dumps([method.upper(), url, sorted((params or {}).items()), body],
                     sort_keys=True, default=str)
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


class Http:
    def __init__(self, collector: str, min_interval: float = 1.0,
                 mode: str | None = None, fixtures: Path = FIXTURES):
        self.collector = collector
        self.min_interval = min_interval
        self.mode = mode or os.environ.get("SIG_HTTP", "live")
        self.dir = fixtures / collector
        self._last = 0.0
        self._robots: dict[str, list[robots.Group] | None] = {}
        self._client = None if self.mode == "replay" else httpx.Client(
            headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True)

    def close(self) -> None:
        if self._client:
            self._client.close()

    def get(self, url: str, params: dict | None = None,
            headers: dict | None = None) -> Response:
        return self.request("GET", url, params=params, headers=headers)

    def post(self, url: str, json_body: Any = None, params: dict | None = None,
             headers: dict | None = None) -> Response:
        return self.request("POST", url, params=params, json_body=json_body, headers=headers)

    def request(self, method: str, url: str, params: dict | None = None,
                json_body: Any = None, headers: dict | None = None) -> Response:
        key = _key(method, url, params, json_body)
        path = self.dir / f"{key}.json"
        if self.mode == "replay":
            if not path.exists():
                raise FixtureMissing(f"{self.collector}: no fixture for {method} {url} {params}")
            d = json.loads(path.read_text(encoding="utf-8"))
            return Response(d["url"], d["status"], d["content_type"], d["text"])

        # Every live URL is checked; robots.txt is fetched once per origin per run.
        self.check_robots(str(httpx.URL(url, params=params)))
        resp = self._send(method, url, params, json_body, headers)
        if self.mode == "record":
            self.dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({
                "method": method, "url": resp.url, "params": params, "status": resp.status_code,
                "content_type": resp.content_type, "text": resp.text,
            }, ensure_ascii=False, indent=1), encoding="utf-8")
        return resp

    def _send(self, method, url, params, json_body, headers) -> Response:
        for attempt in range(4):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                r = self._client.request(method, url, params=params, json=json_body,
                                         headers=headers)
            except httpx.TransportError:
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt * 2)
                continue
            if r.status_code in (429, 500, 502, 503, 504) and attempt < 3:
                retry_after = r.headers.get("retry-after", "")
                wait_s = int(retry_after) if retry_after.isdigit() else 2 ** attempt * 2
                if wait_s > MAX_RETRY_AFTER_S:
                    raise RateLimited(f"{url}: Retry-After {wait_s}s exceeds {MAX_RETRY_AFTER_S}s")
                time.sleep(wait_s)
                continue
            return Response(str(r.url), r.status_code,
                            r.headers.get("content-type", ""), _decode(r))
        raise AssertionError("unreachable")

    def check_robots(self, url: str) -> None:
        """Raise RobotsDisallowed if the site's robots.txt forbids our user agent."""
        if self.mode == "replay":
            return
        origin = httpx.URL(url).copy_with(path="/", query=None, fragment=None)
        base = str(origin).rstrip("/")
        if base not in self._robots:
            # RFC 9309: 4xx means no restrictions; 5xx or unreachable means full disallow.
            # _send retries transient failures first, so one blip doesn't block a week.
            try:
                r = self._send("GET", base + "/robots.txt", None, None, None)
                if r.status_code >= 500 or r.status_code == 429:
                    self._robots[base] = None
                elif r.status_code >= 400:
                    self._robots[base] = []
                else:
                    self._robots[base] = robots.parse(r.text)
            except (httpx.TransportError, RateLimited):
                self._robots[base] = None
        groups = self._robots[base]
        if groups is None:
            raise RobotsDisallowed(f"robots.txt at {base} unreachable; treating as disallowed")
        if not robots.allowed(groups, PRODUCT, url):
            raise RobotsDisallowed(f"robots.txt at {base} disallows {url}")
