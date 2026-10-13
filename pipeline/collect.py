"""Run stream collectors: store items, track health, log metrics."""

import hashlib
import json
import secrets
import sqlite3
import time
import traceback
from collections import Counter
from dataclasses import dataclass

from pipeline import runs
from pipeline.collectors import discover
from pipeline.collectors.base import Collector, Item, SchemaDrift, State
from pipeline.db import db_path
from pipeline.http import Http, RateLimited, RobotsDisallowed

NOW = "strftime('%Y-%m-%dT%H:%M:%fZ','now')"
COMMIT_EVERY = 50


def _salt() -> bytes:
    """Per-install salt so author hashes can't be reversed by hashing known names."""
    path = db_path().parent / ".author_salt"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_hex(16), encoding="utf-8")
    return path.read_text(encoding="utf-8").strip().encode()


def author_hash(salt: bytes, source: str, author: str | None) -> str | None:
    if not author:
        return None
    return hashlib.sha256(salt + f"{source}:{author}".encode()).hexdigest()[:16]


def content_hash(item: Item) -> str:
    return hashlib.sha256(f"{item.title or ''}\n{item.body}".encode()).hexdigest()


@dataclass
class Result:
    source: str
    status: str
    fetched: int = 0
    new: int = 0
    error: str | None = None


def _load_state(conn: sqlite3.Connection, source: str) -> State:
    rows = conn.execute("SELECT key, value FROM collector_state WHERE source = ?", (source,))
    return State({r["key"]: r["value"] for r in rows})


def _save_state(conn: sqlite3.Connection, source: str, state: State) -> None:
    conn.executemany(
        "INSERT INTO collector_state (source, key, value) VALUES (?, ?, ?)"
        " ON CONFLICT (source, key) DO UPDATE SET value = excluded.value",
        [(source, k, v) for k, v in state.values.items()],
    )


def run_collector(conn: sqlite3.Connection, run_id: int, cls: type[Collector],
                  max_items: int, http_mode: str | None = None) -> Result:
    collector = cls(max_items=max_items)
    src = cls.name
    salt = _salt()
    state = _load_state(conn, src)
    http = Http(src, min_interval=cls.min_interval, mode=http_mode)
    start = time.monotonic()
    fetched = new = 0
    authors: set[str] = set()
    by_country: Counter[str] = Counter()
    by_lang: Counter[str] = Counter()
    status, error = "ok", None
    try:
        # Drain the generator: collectors may save cursors after their loop. Items past
        # max_items are still stored, since their cursor has already moved past them;
        # the over-cap metric flags the collector bug instead.
        for item in collector.fetch(http, state):
            fetched += 1
            ah = author_hash(salt, src, item.author)
            cur = conn.execute(
                "INSERT OR IGNORE INTO raw_item (source, source_id, url, author_hash,"
                " created_at, title, body, lang, country, metrics_json, extra_json,"
                " content_hash, license, tos_class, run_id)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (src, str(item.source_id), item.url, ah, item.created_at, item.title,
                 item.body, item.lang, item.country,
                 json.dumps(item.metrics, ensure_ascii=False),
                 json.dumps(item.extra, ensure_ascii=False), content_hash(item),
                 item.license or cls.license, item.tos_class or cls.tos_class, run_id),
            )
            if cur.rowcount:
                new += 1
                if ah:
                    authors.add(ah)
                by_country[item.country or "unknown"] += 1
                by_lang[item.lang or "unknown"] += 1
            if fetched % COMMIT_EVERY == 0:
                conn.commit()  # short write transactions: the app may write meanwhile
        conn.commit()
    except SchemaDrift as e:
        status, error = "schema_drift", str(e)
    except RobotsDisallowed as e:
        status, error = "blocked", str(e)
    except RateLimited as e:
        status, error = "rate_limited", str(e)
    except Exception as e:  # noqa: BLE001 — one broken source must not stop the others
        status, error = "failed", f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}"
    finally:
        http.close()
        conn.commit()  # keep items stored before a failure; dedup makes re-fetch safe

    with conn:
        if status == "ok":
            _save_state(conn, src, state)
        conn.execute(
            f"INSERT INTO collector_health (source, last_attempt_at, last_success_at,"
            f" last_status, last_error, consecutive_failures, items_last_run)"
            f" VALUES (?, {NOW}, CASE WHEN ? = 'ok' THEN {NOW} END, ?, ?,"
            f"  CASE WHEN ? = 'ok' THEN 0 ELSE 1 END, ?)"
            f" ON CONFLICT (source) DO UPDATE SET"
            f"  last_attempt_at = excluded.last_attempt_at,"
            f"  last_success_at = COALESCE(excluded.last_success_at, last_success_at),"
            f"  last_status = excluded.last_status, last_error = excluded.last_error,"
            f"  consecutive_failures = CASE WHEN excluded.last_status = 'ok' THEN 0"
            f"   ELSE consecutive_failures + 1 END,"
            f"  items_last_run = excluded.items_last_run",
            (src, status, status, error, status, new),
        )

    log = lambda name, value, subject=src, layer="sources": runs.log_metric(  # noqa: E731
        conn, run_id, layer, name, value, subject)
    log("ok", 1.0 if status == "ok" else 0.0)
    log("items_fetched", fetched)
    log("items_new", new)
    log("distinct_authors_new", len(authors))
    log("duration_s", round(time.monotonic() - start, 2))
    for country, n in by_country.items():
        log("items_new_by_country", n, f"{src}:{country}", "coverage")
    for lang, n in by_lang.items():
        log("items_new_by_lang", n, f"{src}:{lang}", "coverage")
    if fetched > max_items:
        log("items_over_cap", fetched - max_items)
    return Result(src, status, fetched, new, error)


def collect(conn: sqlite3.Connection, only: list[str] | None = None,
            max_items: int = 500, http_mode: str | None = None) -> list[Result]:
    available = discover()
    unknown = set(only or []) - set(available)
    if unknown:
        raise SystemExit(f"unknown collectors: {sorted(unknown)}; have {sorted(available)}")
    # Restricted sources (terms or robots.txt forbid collection) run only when named.
    chosen = {k: v for k, v in available.items()
              if (k in only if only else v.tos_class != "restricted")}
    results = []
    with runs.run(conn, "collect", note=",".join(chosen)) as run_id:
        for cls in chosen.values():
            results.append(run_collector(conn, run_id, cls, max_items, http_mode))
    return results
