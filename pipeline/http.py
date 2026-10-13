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
import time
import urllib.robotparser
from pathlib import Path
from typing import Any

import httpx

from pipeline.db import ROOT

USER_AGENT = (
    "startup-ideas-generator/0.1 "
    "(+https://github.com/BoopyTheTurtle/startup-ideas-generator)"
)
FIXTURES = ROOT / "tests" / "fixtures"


class FixtureMissing(RuntimeError):
    pass


class RobotsDisallowed(RuntimeError):
    pass


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
        self._robots: dict[str, urllib.robotparser.RobotFileParser] = {}
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
                time.sleep(int(retry_after) if retry_after.isdigit() else 2 ** attempt * 2)
                continue
            return Response(str(r.url), r.status_code,
                            r.headers.get("content-type", ""), r.text)
        raise AssertionError("unreachable")

    def check_robots(self, url: str) -> None:
        """Raise RobotsDisallowed if the site's robots.txt forbids our user agent."""
        if self.mode == "replay":
            return
        origin = httpx.URL(url).copy_with(path="/", query=None, fragment=None)
        base = str(origin).rstrip("/")
        rp = self._robots.get(base)
        if rp is None:
            rp = urllib.robotparser.RobotFileParser()
            r = self._client.get(base + "/robots.txt")
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            self._robots[base] = rp
        if not rp.can_fetch(USER_AGENT, url):
            raise RobotsDisallowed(f"robots.txt at {base} disallows {url}")
