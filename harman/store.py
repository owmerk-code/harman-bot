"""Tek dosyalık SQLite deposu (Docker/sunucu yok). Her şey burada: anahtar-değer durum, gözlemler, defter, olaylar."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS snapshots (
    ts_ms INTEGER NOT NULL, code TEXT NOT NULL, inst TEXT NOT NULL, side INTEGER NOT NULL,
    open_ms INTEGER NOT NULL, lever REAL, open_px REAL, sub_id TEXT NOT NULL,
    PRIMARY KEY (ts_ms, sub_id)
);
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ledger TEXT NOT NULL, inst TEXT NOT NULL, side INTEGER NOT NULL,
    qty REAL NOT NULL, entry_px REAL NOT NULL, entry_ms INTEGER NOT NULL, stop_px REAL NOT NULL,
    tp_px REAL NOT NULL, backers TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
    exit_px REAL, exit_ms INTEGER, exit_reason TEXT, fees REAL NOT NULL DEFAULT 0, pnl REAL, note TEXT
);
CREATE TABLE IF NOT EXISTS equity (ledger TEXT NOT NULL, ts_ms INTEGER NOT NULL, equity REAL NOT NULL,
    PRIMARY KEY (ledger, ts_ms));
CREATE TABLE IF NOT EXISTS events (ts_ms INTEGER NOT NULL, ledger TEXT, kind TEXT NOT NULL, text TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS pos_ledger ON positions(ledger, status);
"""


class Store:
    def __init__(self, path: Path | str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()

    # --- anahtar-değer ---
    def get(self, key: str, default: Any = None) -> Any:
        row = self.db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def put(self, key: str, value: Any) -> None:
        self.db.execute("INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (key, json.dumps(value, ensure_ascii=False)))
        self.db.commit()

    # --- günlük ---
    def log(self, ts_ms: int, kind: str, text: str, ledger: str | None = None) -> None:
        self.db.execute("INSERT INTO events(ts_ms,ledger,kind,text) VALUES(?,?,?,?)", (ts_ms, ledger, kind, text[:4000]))
        self.db.commit()

    def snapshot(self, ts_ms: int, rows: list[dict[str, Any]]) -> None:
        self.db.executemany(
            "INSERT OR IGNORE INTO snapshots(ts_ms,code,inst,side,open_ms,lever,open_px,sub_id) VALUES(?,?,?,?,?,?,?,?)",
            [(ts_ms, r["code"], r["inst"], r["side"], r["open_ms"], r.get("lever"), r.get("open_px"), r["sub_id"])
             for r in rows])
        self.db.commit()

    # --- defter ---
    def open_positions(self, ledger: str) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM positions WHERE ledger=? AND status='open' ORDER BY id", (ledger,)).fetchall()

    def closed_positions(self, ledger: str, since_ms: int = 0) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM positions WHERE ledger=? AND status='closed' AND exit_ms>=? ORDER BY exit_ms",
                               (ledger, since_ms)).fetchall()

    def insert_position(self, **f: Any) -> int:
        cols = ",".join(f)
        cur = self.db.execute(f"INSERT INTO positions({cols}) VALUES({','.join('?' * len(f))})", tuple(f.values()))
        self.db.commit()
        return int(cur.lastrowid)

    def close_position(self, pid: int, *, exit_px: float, exit_ms: int, reason: str, fees: float, pnl: float) -> None:
        self.db.execute("UPDATE positions SET status='closed', exit_px=?, exit_ms=?, exit_reason=?, fees=?, pnl=? WHERE id=?",
                        (exit_px, exit_ms, reason, fees, pnl, pid))
        self.db.commit()

    def record_equity(self, ledger: str, ts_ms: int, equity: float) -> None:
        self.db.execute("INSERT OR REPLACE INTO equity(ledger,ts_ms,equity) VALUES(?,?,?)", (ledger, ts_ms, equity))
        self.db.commit()

    def equity_series(self, ledger: str) -> list[tuple[int, float]]:
        return [(r["ts_ms"], r["equity"]) for r in
                self.db.execute("SELECT ts_ms,equity FROM equity WHERE ledger=? ORDER BY ts_ms", (ledger,))]
