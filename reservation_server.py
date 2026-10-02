#!/usr/bin/env python3
"""Tiny standard-library reservation API for multi-user lottery deployments.

It stores only a normalized combination hash and an expiry time. Put this
behind HTTPS and a rate limiter before exposing it to the public internet.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


MAX_BODY = 4096
RESERVATION_TTL_SECONDS = 48 * 60 * 60


def combination_hash(draw_issue: str, game: str, combination: str) -> str:
    canonical = "\n".join((draw_issue.strip(), game.strip().lower(), " ".join(combination.split())))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def init_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                draw_issue TEXT NOT NULL,
                game TEXT NOT NULL,
                combination_hash TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                PRIMARY KEY (draw_issue, game, combination_hash)
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS reservations_expiry ON reservations (expires_at)")
        db.commit()


def reserve(path: Path, draw_issue: str, game: str, combination: str) -> tuple[bool, str]:
    now = int(time.time())
    expires = now + RESERVATION_TTL_SECONDS
    digest = combination_hash(draw_issue, game, combination)
    with sqlite3.connect(path) as db:
        db.execute("DELETE FROM reservations WHERE expires_at <= ?", (now,))
        cursor = db.execute(
            "INSERT OR IGNORE INTO reservations(draw_issue, game, combination_hash, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (draw_issue, game, digest, now, expires),
        )
        db.commit()
        return cursor.rowcount == 1, digest


class Handler(BaseHTTPRequestHandler):
    db_path: Path

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self.send_json(200, {"ok": True})
            return
        self.send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/reservations":
            self.send_json(404, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_BODY:
                raise ValueError("invalid body size")
            payload = json.loads(self.rfile.read(length))
            draw_issue = str(payload.get("draw_issue", "")).strip()
            game = str(payload.get("game", "")).strip().lower()
            combination = str(payload.get("combination", "")).strip()
            if not draw_issue or not game or not combination:
                raise ValueError("draw_issue, game, and combination are required")
            created, digest = reserve(self.db_path, draw_issue, game, combination)
            if not created:
                self.send_json(409, {"reserved": False, "combination_hash": digest})
                return
            self.send_json(201, {"reserved": True, "combination_hash": digest})
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_json(400, {"error": str(exc)})

    def log_message(self, _format: str, *_args: Any) -> None:
        return


def main() -> int:
    parser = argparse.ArgumentParser(description="Shared lottery combination reservation API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--db", default="./reservation.sqlite3")
    args = parser.parse_args()
    db_path = Path(args.db).expanduser().resolve()
    init_db(db_path)
    Handler.db_path = db_path
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"reservation service listening on http://{args.host}:{args.port}; db={db_path}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
