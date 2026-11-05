"""Public API stubs. Behaviour is intentionally not implemented yet."""
from __future__ import annotations

import datetime as dt
import sqlite3
import sys
import zoneinfo
from pathlib import Path
from decimal import Decimal
from typing import Callable

from .models import (
    AdoptionResult,
    BacktestSettings,
    Bar,
    Broker,
    BrokerError,
    BrokerOrder,
    BrokerRejected,
    BrokerTimeout,
    Config,
    ConfigError,
    DataImportError,
    Decision,
    DuplicateOrderError,
    ImportResult,
    Notification,
    Notifier,
    OrderPlan,
    OrderRecord,
    OrderRequest,
    Rule,
    RuleMetrics,
    RunResult,
    SimulationResult,
)

__all__ = [
    "AdoptionResult", "BacktestSettings", "Bar", "Broker", "BrokerError",
    "BrokerOrder", "BrokerRejected", "BrokerTimeout", "Config", "ConfigError",
    "DataImportError", "Decision", "DuplicateOrderError", "FakeBroker",
    "FakeNotifier", "ImportResult", "Notification", "Notifier", "OrderPlan",
    "OrderRecord", "OrderRequest", "Rule", "RuleMetrics", "RunResult",
    "SimulationResult", "Store", "compute_order", "evaluate_adoption",
    "get_status", "import_csv", "is_in_order_window", "load_config", "main",
    "record_adjustment", "run_backtest", "run_once", "simulate",
]


def main(
    argv: list[str],
    *,
    broker: Broker | None = None,
    notifier: Notifier | None = None,
    now: dt.datetime | None = None,
    tz_loader: Callable[[str], dt.tzinfo] = zoneinfo.ZoneInfo,
    stdout=None,
    stderr=None,
) -> int:
    import argparse
    import json

    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr

    parser = argparse.ArgumentParser(prog="qqq-accumulator")
    parser.add_argument("--config", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    imp = sub.add_parser("import-data")
    imp.add_argument("--file", required=True)
    for name in ("backtest", "run", "status", "adjust"):
        sub.add_parser(name)
    try:
        args, _extra = parser.parse_known_args(argv)
    except SystemExit:
        return 2

    if args.command != "import-data":
        raise NotImplementedError("main")

    store = None
    try:
        config = load_config(args.config)
        db = (config.raw.get("paths") or {}).get("database")
        if not isinstance(db, str) or not db:
            raise ConfigError("paths.database is required")
        try:
            store = Store.open(db)
        except (RuntimeError, sqlite3.Error) as exc:
            err.write(f"error: {exc}\n")
            return 2
        result = import_csv(store, args.file)
        out.write(json.dumps({"kind": result.kind, "rows": result.rows,
                              "sha256": result.sha256}) + "\n")
        return 0
    except (ConfigError, DataImportError, OSError) as exc:
        err.write(f"error: {exc}\n")
        return 2
    finally:
        if store is not None:
            store.close()


def load_config(path) -> Config:
    import tomllib

    try:
        with open(path, "rb") as fh:
            raw = tomllib.load(fh, parse_float=Decimal)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"cannot read config: {exc}") from exc
    return Config(stage=raw.get("stage", "dry-run"), raw=raw)


class Store:
    _SCHEMA = (
        """CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY,
            trade_date TEXT NOT NULL,
            rule_id TEXT NOT NULL,
            status TEXT NOT NULL,
            quantity TEXT NOT NULL,
            limit_price TEXT NOT NULL,
            client_order_id TEXT,
            broker_order_id TEXT,
            fill_price TEXT,
            fill_cost TEXT,
            created_at TEXT,
            UNIQUE (trade_date, rule_id)
        ) STRICT""",
        """CREATE TABLE IF NOT EXISTS calendar (
            date TEXT PRIMARY KEY,
            is_open INTEGER NOT NULL,
            close_time TEXT
        ) STRICT""",
        """CREATE TABLE IF NOT EXISTS bars (
            date TEXT PRIMARY KEY,
            open TEXT NOT NULL,
            high TEXT NOT NULL,
            low TEXT NOT NULL,
            close TEXT NOT NULL,
            volume INTEGER NOT NULL,
            split_factor TEXT NOT NULL,
            dividend TEXT NOT NULL
        ) STRICT""",
        """CREATE TABLE IF NOT EXISTS fx_rates (
            date TEXT PRIMARY KEY,
            usd_krw TEXT NOT NULL
        ) STRICT""",
        """CREATE TABLE IF NOT EXISTS snapshots (
            kind TEXT PRIMARY KEY,
            sha256 TEXT NOT NULL,
            rows INTEGER NOT NULL,
            imported_at TEXT NOT NULL
        ) STRICT""",
    )

    def __init__(self, path, conn: sqlite3.Connection | None = None) -> None:
        self.path = path
        self._conn = conn

    @classmethod
    def open(cls, path) -> "Store":
        if sqlite3.sqlite_version_info < (3, 37, 0):
            raise RuntimeError("SQLite >= 3.37 is required for STRICT tables")
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(p), isolation_level=None)
        mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        if str(mode).lower() != "wal":
            conn.close()
            raise RuntimeError("could not enable WAL mode")
        conn.execute("PRAGMA foreign_keys=ON")
        for ddl in cls._SCHEMA:
            conn.execute(ddl)
        return cls(path, conn)

    def insert_order_intent(
        self,
        trade_date: dt.date,
        rule_id: str,
        quantity: Decimal,
        limit_price: Decimal,
        status: str,
    ) -> int:
        try:
            cur = self._conn.execute(
                "INSERT INTO orders (trade_date, rule_id, status, quantity,"
                " limit_price, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    trade_date.isoformat(),
                    rule_id,
                    status,
                    str(quantity),
                    str(limit_price),
                    dt.datetime.now(dt.timezone.utc).isoformat(),
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise DuplicateOrderError(
                f"order already exists for {trade_date.isoformat()}/{rule_id}"
            ) from exc
        return cur.lastrowid

    def list_orders(self) -> list[OrderRecord]:
        rows = self._conn.execute(
            "SELECT trade_date, rule_id, status, quantity, limit_price,"
            " broker_order_id, fill_price, fill_cost FROM orders"
            " ORDER BY trade_date DESC, id DESC"
        ).fetchall()

        def dec(v):
            return None if v is None else Decimal(v)

        return [
            OrderRecord(
                trade_date=dt.date.fromisoformat(r[0]),
                rule_id=r[1],
                status=r[2],
                quantity=Decimal(r[3]),
                limit_price=Decimal(r[4]),
                broker_order_id=r[5],
                fill_price=dec(r[6]),
                fill_cost=dec(r[7]),
            )
            for r in rows
        ]

    def holdings(self) -> Decimal:
        raise NotImplementedError("Store.holdings")

    def list_bars(self) -> list[Bar]:
        """Stored daily bars in date order (query helper)."""
        rows = self._conn.execute(
            "SELECT date, open, high, low, close, volume, split_factor,"
            " dividend FROM bars ORDER BY date"
        ).fetchall()
        return [
            Bar(
                date=dt.date.fromisoformat(r[0]),
                open=Decimal(r[1]),
                high=Decimal(r[2]),
                low=Decimal(r[3]),
                close=Decimal(r[4]),
                volume=int(r[5]),
                split_factor=Decimal(r[6]),
                dividend=Decimal(r[7]),
            )
            for r in rows
        ]

    def snapshot_sha256(self, kind: str) -> str | None:
        """Recorded SHA-256 of the latest snapshot of `kind` ("calendar"/"bars"/"fx")."""
        row = self._conn.execute(
            "SELECT sha256 FROM snapshots WHERE kind = ?", (kind,)
        ).fetchone()
        return None if row is None else row[0]

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None


_HEADERS = {
    ("date", "is_open", "close_time"): "calendar",
    ("date", "open", "high", "low", "close", "volume", "split_factor",
     "dividend"): "bars",
    ("date", "usd_krw"): "fx",
}


def _p_date(text: str) -> dt.date:
    try:
        return dt.date.fromisoformat(text.strip())
    except ValueError as exc:
        raise DataImportError(f"invalid date: {text!r}") from exc


def _p_dec(text: str, name: str) -> Decimal:
    try:
        v = Decimal(text.strip())
    except Exception as exc:
        raise DataImportError(f"invalid {name}: {text!r}") from exc
    if not v.is_finite():
        raise DataImportError(f"invalid {name}: {text!r}")
    return v


def _parse_csv(data: bytes):
    import csv
    import io

    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DataImportError("file is not valid UTF-8") from exc
    rows = [r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]
    if not rows:
        raise DataImportError("empty file")
    kind = _HEADERS.get(tuple(c.strip() for c in rows[0]))
    if kind is None:
        raise DataImportError("unrecognised header")
    body = rows[1:]
    width = len(rows[0])
    for r in body:
        if len(r) != width:
            raise DataImportError(f"wrong column count: {r!r}")
    if not body:
        raise DataImportError("no data rows")
    return kind, body


def import_csv(store: Store, path) -> ImportResult:
    data = Path(path).read_bytes()
    digest = __import__("hashlib").sha256(data).hexdigest()
    kind, body = _parse_csv(data)
    conn = store._conn
    seen: set[dt.date] = set()
    out: list[tuple] = []

    if kind == "calendar":
        for r in body:
            d = _p_date(r[0])
            if d in seen:
                raise DataImportError(f"duplicate date: {d}")
            seen.add(d)
            flag = r[1].strip()
            ct = r[2].strip()
            if flag == "true":
                try:
                    dt.datetime.strptime(ct, "%H:%M")
                except ValueError as exc:
                    raise DataImportError(f"invalid close_time: {ct!r}") from exc
                out.append((d.isoformat(), 1, ct))
            elif flag == "false":
                if ct:
                    raise DataImportError("close_time must be empty when closed")
                out.append((d.isoformat(), 0, None))
            else:
                raise DataImportError(f"invalid is_open: {flag!r}")
        sql = "INSERT INTO calendar (date, is_open, close_time) VALUES (?, ?, ?)"
    elif kind == "fx":
        for r in body:
            d = _p_date(r[0])
            if d in seen:
                raise DataImportError(f"duplicate date: {d}")
            seen.add(d)
            v = _p_dec(r[1], "usd_krw")
            if v <= 0:
                raise DataImportError("usd_krw must be positive")
            out.append((d.isoformat(), str(v)))
        sql = "INSERT INTO fx_rates (date, usd_krw) VALUES (?, ?)"
    else:
        for r in body:
            d = _p_date(r[0])
            if d in seen:
                raise DataImportError(f"duplicate date: {d}")
            seen.add(d)
            o, h, lo, c = (_p_dec(r[i], n) for i, n in
                           ((1, "open"), (2, "high"), (3, "low"), (4, "close")))
            if min(o, h, lo, c) <= 0:
                raise DataImportError(f"non-positive price on {d}")
            try:
                vol = int(r[5].strip())
            except ValueError as exc:
                raise DataImportError(f"invalid volume: {r[5]!r}") from exc
            if vol < 0:
                raise DataImportError("volume must be non-negative")
            sf = _p_dec(r[6], "split_factor")
            if sf <= 0:
                raise DataImportError("split_factor must be positive")
            dv = _p_dec(r[7], "dividend")
            if dv < 0:
                raise DataImportError("dividend must be non-negative")
            out.append((d.isoformat(), str(o), str(h), str(lo), str(c), vol,
                        str(sf), str(dv)))
        cal = {
            dt.date.fromisoformat(a): bool(b)
            for a, b in conn.execute("SELECT date, is_open FROM calendar")
        }
        if not cal:
            raise DataImportError("calendar has not been imported")
        for d in seen:
            if not cal.get(d, False):
                raise DataImportError(f"{d} is not an open calendar day")
        first, last = min(seen), max(seen)
        for d, is_open in cal.items():
            if is_open and first <= d <= last and d not in seen:
                raise DataImportError(f"missing bar for trading day {d}")
        sql = ("INSERT INTO bars (date, open, high, low, close, volume,"
               " split_factor, dividend) VALUES (?, ?, ?, ?, ?, ?, ?, ?)")

    table = {"calendar": "calendar", "bars": "bars", "fx": "fx_rates"}[kind]
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(f"DELETE FROM {table}")
            conn.executemany(sql, out)
            conn.execute(
                "INSERT OR REPLACE INTO snapshots (kind, sha256, rows,"
                " imported_at) VALUES (?, ?, ?, ?)",
                (kind, digest, len(out),
                 dt.datetime.now(dt.timezone.utc).isoformat()),
            )
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
    except sqlite3.Error as exc:
        raise DataImportError(f"database error: {exc}") from exc
    return ImportResult(kind=kind, rows=len(out), sha256=digest)


def simulate(
    bars: list[Bar],
    rules: list[Rule],
    settings: BacktestSettings,
    fx_rates: dict[dt.date, Decimal] | None = None,
) -> SimulationResult:
    raise NotImplementedError("simulate")


def evaluate_adoption(
    rule_eval_shares: Decimal,
    baseline_eval_shares: Decimal,
    rolling_pairs: list[tuple[Decimal, Decimal]],
    min_outperformance_pct: Decimal,
    min_rolling_ratio_pct: Decimal,
) -> AdoptionResult:
    raise NotImplementedError("evaluate_adoption")


def run_backtest(store: Store, rules_path, config: Config) -> dict:
    raise NotImplementedError("run_backtest")


def compute_order(
    prev_close: Decimal,
    limit_margin_pct: Decimal,
    rule_amount: Decimal,
    orderable_cash: Decimal,
    per_order_limit: Decimal,
    monthly_remaining: Decimal,
    buy_fee_pct: Decimal,
    fractional: bool,
) -> OrderPlan:
    raise NotImplementedError("compute_order")


def is_in_order_window(
    now: dt.datetime,
    window_start: dt.time,
    window_end: dt.time,
    close_time: dt.time,
    tz_loader: Callable[[str], dt.tzinfo] = zoneinfo.ZoneInfo,
) -> bool:
    raise NotImplementedError("is_in_order_window")


def run_once(
    config: Config,
    store: Store,
    *,
    broker: Broker | None,
    notifier: Notifier,
    now: dt.datetime,
    tz_loader: Callable[[str], dt.tzinfo] = zoneinfo.ZoneInfo,
) -> RunResult:
    raise NotImplementedError("run_once")


def get_status(store: Store) -> dict:
    raise NotImplementedError("get_status")


def record_adjustment(store: Store, shares: Decimal, reason: str) -> None:
    raise NotImplementedError("record_adjustment")


class FakeBroker:
    """In-memory, buy-only broker for tests (no network)."""

    def __init__(self, orderable_cash: Decimal, position: Decimal) -> None:
        self._orderable_cash = orderable_cash
        self._position = position
        self.place_calls = 0

    def get_orderable_cash_usd(self) -> Decimal:
        raise NotImplementedError("FakeBroker.get_orderable_cash_usd")

    def get_position(self, symbol: str) -> Decimal:
        raise NotImplementedError("FakeBroker.get_position")

    def place_loc_buy(self, request: OrderRequest) -> str:
        raise NotImplementedError("FakeBroker.place_loc_buy")

    def list_orders(self, trade_date: dt.date) -> list[BrokerOrder]:
        raise NotImplementedError("FakeBroker.list_orders")

    def settle_close(self, trade_date: dt.date, close: Decimal) -> None:
        raise NotImplementedError("FakeBroker.settle_close")

    def set_position(self, qty: Decimal) -> None:
        raise NotImplementedError("FakeBroker.set_position")

    def set_orderable_cash(self, amount: Decimal) -> None:
        raise NotImplementedError("FakeBroker.set_orderable_cash")

    def fail_next_place(self, mode: str) -> None:
        raise NotImplementedError("FakeBroker.fail_next_place")


class FakeNotifier:
    """Records notifications in `messages`; raises on send when `fail`."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.messages: list[Notification] = []

    def send(self, notification: Notification) -> None:
        raise NotImplementedError("FakeNotifier.send")
