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
    bt = sub.add_parser("backtest")
    bt.add_argument("--rules", required=True)
    sub.add_parser("run")
    sub.add_parser("status")
    adj = sub.add_parser("adjust")
    adj.add_argument("--shares")
    adj.add_argument("--reason")
    try:
        args, _extra = parser.parse_known_args(argv)
    except SystemExit:
        return 2

    if args.command in ("run", "backtest"):
        store = None
        try:
            config = load_config(args.config)
            if args.command == "backtest":
                _validate_backtest_config(config)
            db = _cfg_get(config.raw, "paths.database")
            if not isinstance(db, str) or not db:
                raise ConfigError("paths.database is required")
        except ConfigError as exc:
            err.write(f"error: {exc}\n")
            if args.command == "run" and notifier is not None:
                _safe_send(notifier, Notification(
                    kind="ERROR", trade_date=None, reason="CONFIG_ERROR",
                    text=str(exc)))
            return 2
        try:
            try:
                store = Store.open(db)
            except (RuntimeError, sqlite3.Error) as exc:
                err.write(f"error: {exc}\n")
                return 2
            if args.command == "backtest":
                try:
                    result = run_backtest(store, args.rules, config)
                except (ConfigError, DataImportError, ValueError,
                        OSError) as exc:
                    err.write(f"error: {exc}\n")
                    return 2
                out.write(json.dumps(result, default=str) + "\n")
                return 0

            class _NoopNotifier:
                def send(self, notification):
                    pass

            res = run_once(
                config, store, broker=broker,
                notifier=notifier if notifier is not None else _NoopNotifier(),
                now=now or dt.datetime.now(dt.timezone.utc),
                tz_loader=tz_loader)
            out.write(json.dumps({"exit_code": res.exit_code,
                                  "reasons": res.reasons,
                                  "orders_sent": res.orders_sent}) + "\n")
            return res.exit_code
        finally:
            if store is not None:
                store.close()

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


def _cfg_get(raw: dict, key: str):
    node = raw
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            raise ConfigError(f"{key} is required")
        node = node[part]
    return node


def _cfg_num(raw, key, *, gt=None, ge=None, le=None) -> Decimal:
    v = _cfg_get(raw, key)
    if isinstance(v, bool) or not isinstance(v, (int, Decimal)):
        raise ConfigError(f"{key} must be a number")
    d = Decimal(v)
    if not d.is_finite():
        raise ConfigError(f"{key} must be finite")
    if gt is not None and not d > gt:
        raise ConfigError(f"{key} must be > {gt}")
    if ge is not None and not d >= ge:
        raise ConfigError(f"{key} must be >= {ge}")
    if le is not None and not d <= le:
        raise ConfigError(f"{key} must be <= {le}")
    return d


def _cfg_int(raw, key, *, ge=None, le=None) -> int:
    v = _cfg_get(raw, key)
    if isinstance(v, bool) or not isinstance(v, int):
        raise ConfigError(f"{key} must be an integer")
    if ge is not None and v < ge:
        raise ConfigError(f"{key} must be >= {ge}")
    if le is not None and v > le:
        raise ConfigError(f"{key} must be <= {le}")
    return v


def _cfg_bool(raw, key) -> bool:
    v = _cfg_get(raw, key)
    if not isinstance(v, bool):
        raise ConfigError(f"{key} must be a boolean")
    return v


def _cfg_enum(raw, key, allowed) -> str:
    v = _cfg_get(raw, key)
    if not isinstance(v, str) or v not in allowed:
        raise ConfigError(f"{key} must be one of {sorted(allowed)}")
    return v


def _cfg_hhmm(raw, key) -> dt.time:
    v = _cfg_get(raw, key)
    if not isinstance(v, str):
        raise ConfigError(f"{key} must be HH:MM")
    try:
        return dt.datetime.strptime(v, "%H:%M").time()
    except ValueError as exc:
        raise ConfigError(f"{key} must be HH:MM") from exc


def _validate_deposit_schedule(raw) -> None:
    cycle = _cfg_enum(raw, "deposit.cycle", {"monthly", "every_n_trading_days"})
    if cycle == "monthly":
        _cfg_int(raw, "deposit.day", ge=1, le=31)
    else:
        _cfg_int(raw, "deposit.n", ge=1)


def _validate_run_config(config: Config) -> None:
    raw = config.raw
    if config.stage not in ("dry-run", "paper", "live"):
        raise ConfigError("stage must be one of dry-run, paper, live")
    if not isinstance(_cfg_get(raw, "paths.halt_file"), str):
        raise ConfigError("paths.halt_file must be a string")
    _cfg_num(raw, "limits.per_order_usd", gt=0)
    _cfg_num(raw, "limits.monthly_usd", gt=0)
    _cfg_num(raw, "costs.buy_fee_pct", ge=0, le=100)
    start = _cfg_hhmm(raw, "order_window.start")
    end = _cfg_hhmm(raw, "order_window.end")
    if not start < end:
        raise ConfigError("order_window.start must be before order_window.end")
    _cfg_num(raw, "order.limit_margin_pct", ge=0)
    _cfg_num(raw, "guard.abnormal_price_pct", gt=0)
    _cfg_bool(raw, "shares.fractional")
    rule_type = "baseline"
    if "operating_rule" in raw:
        rule_type = _cfg_enum(raw, "operating_rule.type",
                              {"baseline", "close_at_or_below"})
        if rule_type == "close_at_or_below":
            _cfg_num(raw, "operating_rule.threshold_usd", gt=0)
    if rule_type == "baseline":
        _validate_deposit_schedule(raw)
        if _cfg_get(raw, "deposit.cycle") == "every_n_trading_days":
            v = _cfg_get(raw, "deposit.anchor_date")
            try:
                dt.date.fromisoformat(v if isinstance(v, str) else str(v))
            except ValueError as exc:
                raise ConfigError("deposit.anchor_date must be a date") from exc


def _validate_backtest_config(config: Config) -> None:
    raw = config.raw
    _validate_deposit_schedule(raw)
    _cfg_num(raw, "deposit.amount", gt=0)
    _cfg_enum(raw, "deposit.currency", {"KRW", "USD"})
    for key in ("costs.buy_fee_pct", "costs.fx_cost_pct",
                "costs.dividend_withholding_pct"):
        _cfg_num(raw, key, ge=0, le=100)
    _cfg_num(raw, "order.limit_margin_pct", ge=0)
    _cfg_bool(raw, "shares.fractional")
    _cfg_int(raw, "adoption.holdout_years", ge=1)
    _cfg_int(raw, "adoption.rolling_window_years", ge=1)
    _cfg_num(raw, "adoption.min_outperformance_pct", ge=0)
    _cfg_num(raw, "adoption.min_rolling_ratio_pct", ge=0, le=100)


def _safe_send(notifier, notification: Notification) -> None:
    try:
        notifier.send(notification)
    except Exception:
        pass


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
        """CREATE TABLE IF NOT EXISTS position_ledger (
            id INTEGER PRIMARY KEY,
            kind TEXT NOT NULL,
            amount TEXT NOT NULL,
            order_id INTEGER UNIQUE,
            note TEXT,
            created_at TEXT
        ) STRICT""",
        """CREATE TABLE IF NOT EXISTS notifications_sent (
            trade_date TEXT NOT NULL,
            kind TEXT NOT NULL,
            reason TEXT NOT NULL,
            UNIQUE (trade_date, kind, reason)
        ) STRICT""",
        """CREATE TABLE IF NOT EXISTS run_log (
            id INTEGER PRIMARY KEY,
            at TEXT NOT NULL,
            exit_code INTEGER NOT NULL,
            reasons TEXT NOT NULL
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
        total = Decimal(0)
        rows = self._conn.execute(
            "SELECT kind, amount FROM position_ledger ORDER BY id").fetchall()
        for kind, amount in rows:
            a = Decimal(amount)
            if kind == "SPLIT":
                total = total * a
            else:
                total = total + a
        return total

    # -- internal helpers used by run_once --------------------------------
    def _orders_raw(self) -> list[dict]:
        cols = ("id", "trade_date", "rule_id", "status", "quantity",
                "limit_price", "client_order_id", "broker_order_id",
                "fill_price", "fill_cost")
        rows = self._conn.execute(
            "SELECT " + ", ".join(cols) + " FROM orders ORDER BY id"
        ).fetchall()
        return [dict(zip(cols, r)) for r in rows]

    def _set_order_status(self, order_id: int, status: str,
                          broker_order_id: str | None = None) -> None:
        if broker_order_id is None:
            self._conn.execute("UPDATE orders SET status = ? WHERE id = ?",
                               (status, order_id))
        else:
            self._conn.execute(
                "UPDATE orders SET status = ?, broker_order_id = ?"
                " WHERE id = ?", (status, broker_order_id, order_id))

    def _set_client_order_id(self, order_id: int, client_order_id: str) -> None:
        self._conn.execute(
            "UPDATE orders SET client_order_id = ? WHERE id = ?",
            (client_order_id, order_id))

    def _mark_filled(self, order_id: int, quantity: Decimal,
                     fill_price: Decimal, fill_cost: Decimal,
                     broker_order_id: str | None) -> None:
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            cur = conn.execute(
                "UPDATE orders SET status = 'FILLED', fill_price = ?,"
                " fill_cost = ?, broker_order_id = COALESCE(?, broker_order_id)"
                " WHERE id = ? AND status != 'FILLED'",
                (str(fill_price), str(fill_cost), broker_order_id, order_id))
            if cur.rowcount:
                conn.execute(
                    "INSERT OR IGNORE INTO position_ledger (kind, amount,"
                    " order_id, created_at) VALUES ('FILL', ?, ?, ?)",
                    (str(quantity), order_id,
                     dt.datetime.now(dt.timezone.utc).isoformat()))
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise

    def _first_notification(self, trade_date: dt.date, kind: str,
                            reason: str) -> bool:
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO notifications_sent (trade_date, kind,"
            " reason) VALUES (?, ?, ?)", (trade_date.isoformat(), kind, reason))
        return cur.rowcount > 0

    def _log_run(self, at: dt.datetime, exit_code: int,
                 reasons: list[str]) -> None:
        self._conn.execute(
            "INSERT INTO run_log (at, exit_code, reasons) VALUES (?, ?, ?)",
            (at.isoformat(), exit_code, ",".join(reasons)))

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


def _decide_amount(rule: Rule, bar: Bar, available: Decimal,
                   is_deposit: bool) -> Decimal:
    """Shared decision function for backtest and live runs."""
    zero = Decimal(0)
    if rule.type == "baseline":
        return available if is_deposit else zero
    if rule.type == "close_at_or_below":
        if (rule.threshold_usd is not None and bar.close <=
                rule.threshold_usd and available > 0):
            return available
        return zero
    raise ValueError(f"unknown rule type: {rule.type}")


def simulate(
    bars: list[Bar],
    rules: list[Rule],
    settings: BacktestSettings,
    fx_rates: dict[dt.date, Decimal] | None = None,
) -> SimulationResult:
    from decimal import ROUND_CEILING, ROUND_DOWN, ROUND_HALF_UP

    def q(value: Decimal, exp: str, mode) -> Decimal:
        return value.quantize(Decimal(exp), rounding=mode)

    def qty_round(value: Decimal) -> Decimal:
        if settings.fractional:
            return q(value, "0.000001", ROUND_DOWN)
        return q(value, "1", ROUND_DOWN)

    if not bars:
        raise ValueError("bars must not be empty")
    hundred = Decimal(100)
    one = Decimal(1)
    zero = Decimal(0)

    # deposit days
    deposit_days: set[int] = set()
    if settings.deposit_cycle == "every_n_trading_days":
        n = max(int(settings.deposit_n), 1)
        deposit_days = set(range(0, len(bars), n))
    elif settings.deposit_cycle == "monthly":
        months: dict[tuple[int, int], list[int]] = {}
        for i, b in enumerate(bars):
            months.setdefault((b.date.year, b.date.month), []).append(i)
        for idxs in months.values():
            chosen = idxs[-1]
            for i in idxs:
                if bars[i].date.day >= settings.deposit_day:
                    chosen = i
                    break
            deposit_days.add(chosen)
    else:
        raise ValueError(f"unknown deposit_cycle: {settings.deposit_cycle}")

    all_rules = [Rule("baseline", "baseline")] + list(rules)
    for r in all_rules[1:]:
        if r.type not in ("baseline", "close_at_or_below"):
            raise ValueError(f"unknown rule type: {r.type}")

    decide = _decide_amount

    states = {}
    for r in all_rules:
        states[r.id] = {
            "shares": zero, "cash": zero, "reserved": zero, "pending": None,
            "deposit": zero, "cost": zero, "unfilled": 0, "waiting": 0,
        }
    decisions: list[Decision] = []

    for idx, bar in enumerate(bars):
        is_deposit = idx in deposit_days
        deposit_usd = zero
        if is_deposit:
            if settings.currency == "KRW":
                rate = (fx_rates or {}).get(bar.date)
                if rate is None:
                    raise DataImportError(f"missing fx rate for {bar.date}")
                deposit_usd = q(
                    settings.deposit_amount / rate
                    * (one - settings.fx_cost_pct / hundred),
                    "0.01", ROUND_DOWN)
            else:
                deposit_usd = settings.deposit_amount
        for r in all_rules:
            st = states[r.id]
            # 1. split
            if bar.split_factor != 1:
                f = bar.split_factor
                st["shares"] = st["shares"] * f
                if not settings.fractional:
                    st["shares"] = q(st["shares"], "1", ROUND_DOWN)
                if st["pending"] is not None:
                    pq, pl = st["pending"]
                    pq = pq * f
                    if not settings.fractional:
                        pq = q(pq, "1", ROUND_DOWN)
                    st["pending"] = (pq, pl / f)
            # 2. settle
            if st["pending"] is not None:
                pq, pl = st["pending"]
                if bar.close <= pl:
                    cost = q(pq * bar.close, "0.01", ROUND_HALF_UP)
                    fee = q(cost * settings.buy_fee_pct / hundred, "0.01",
                            ROUND_CEILING)
                    st["cash"] -= cost + fee
                    st["cost"] += cost + fee
                    st["shares"] += pq
                else:
                    st["unfilled"] += 1
                st["pending"] = None
                st["reserved"] = zero
            # 3. dividend
            if bar.dividend > 0 and st["shares"] > 0:
                st["cash"] += q(
                    st["shares"] * bar.dividend
                    * (one - settings.withholding_pct / hundred),
                    "0.01", ROUND_DOWN)
            # 4. deposit
            if is_deposit:
                st["cash"] += deposit_usd
                st["deposit"] += deposit_usd
            # 6. decide
            available = st["cash"] - st["reserved"]
            amount = decide(r, bar, available, is_deposit)
            if amount > 0:
                limit = q(bar.close * (one + settings.limit_margin_pct
                                       / hundred), "0.01", ROUND_HALF_UP)
                qty = qty_round(
                    amount / (limit * (one + settings.buy_fee_pct / hundred)))
                if qty > 0:
                    decisions.append(Decision(bar.date, r.id, qty, limit))
                    st["pending"] = (qty, limit)
                    st["reserved"] = amount
            # 7. waiting
            if st["cash"] - st["reserved"] > 0:
                st["waiting"] += 1

    last_close = bars[-1].close
    raw = {}
    for r in all_rules:
        st = states[r.id]
        eq = q(st["shares"] + st["cash"] / last_close, "0.000001",
               ROUND_DOWN)
        avg = (q(st["cost"] / st["shares"], "0.0001", ROUND_HALF_UP)
               if st["shares"] > 0 else None)
        raw[r.id] = (st, eq, avg)
    base_shares = states["baseline"]["shares"]
    base_eq = raw["baseline"][1]
    metrics = {}
    for r in all_rules:
        st, eq, avg = raw[r.id]
        metrics[r.id] = RuleMetrics(
            final_shares=st["shares"],
            cash_usd=st["cash"],
            equivalent_shares=eq,
            total_deposit_usd=st["deposit"],
            average_cost_usd=avg,
            cash_waiting_days=st["waiting"],
            unfilled_count=st["unfilled"],
            final_shares_diff_vs_baseline=st["shares"] - base_shares,
            equivalent_shares_diff_vs_baseline=eq - base_eq,
        )
    decisions.sort(key=lambda d: d.date)
    return SimulationResult(metrics=metrics, decisions=decisions)


def evaluate_adoption(
    rule_eval_shares: Decimal,
    baseline_eval_shares: Decimal,
    rolling_pairs: list[tuple[Decimal, Decimal]],
    min_outperformance_pct: Decimal,
    min_rolling_ratio_pct: Decimal,
) -> AdoptionResult:
    hundred = Decimal(100)
    if baseline_eval_shares != 0:
        outperf = ((rule_eval_shares - baseline_eval_shares)
                   / baseline_eval_shares * hundred)
    else:
        outperf = None
    if rolling_pairs:
        ok = sum(1 for r, b in rolling_pairs if r >= b)
        ratio = Decimal(ok) / Decimal(len(rolling_pairs)) * hundred
    else:
        ratio = Decimal(0)
    if baseline_eval_shares == 0:
        outperf_ok = rule_eval_shares > 0
    else:
        outperf_ok = (rule_eval_shares > baseline_eval_shares
                      and outperf >= min_outperformance_pct)
    adopted = bool(outperf_ok and ratio >= min_rolling_ratio_pct)
    return AdoptionResult(adopted=adopted, outperformance_pct=outperf,
                          rolling_ratio_pct=ratio)


def _load_rules(path) -> list[Rule]:
    import json

    try:
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh, parse_float=Decimal)
    except (OSError, ValueError) as exc:
        raise ConfigError(f"cannot read rules: {exc}") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("rules"), list):
        raise ConfigError("rules file must contain a 'rules' list")
    rules: list[Rule] = []
    seen: set[str] = set()
    for item in doc["rules"]:
        if not isinstance(item, dict):
            raise ConfigError("rule must be an object")
        rid = item.get("id")
        if not isinstance(rid, str) or not rid or rid == "baseline" \
                or rid in seen:
            raise ConfigError(f"invalid or duplicate rule id: {rid!r}")
        seen.add(rid)
        if item.get("type") != "close_at_or_below":
            raise ConfigError(f"unknown rule type: {item.get('type')!r}")
        th = item.get("threshold_usd")
        if isinstance(th, bool) or not isinstance(th, (str, int, Decimal)):
            raise ConfigError("threshold_usd must be a number")
        try:
            thd = Decimal(th)
        except Exception as exc:
            raise ConfigError("threshold_usd must be a number") from exc
        if not thd.is_finite() or not thd > 0:
            raise ConfigError("threshold_usd must be positive")
        rules.append(Rule(rid, "close_at_or_below", thd))
    return rules


def _add_years(d: dt.date, n: int) -> dt.date:
    try:
        return d.replace(year=d.year + n)
    except ValueError:
        return d.replace(year=d.year + n, day=28)


def _backtest_settings(raw: dict) -> BacktestSettings:
    cycle = _cfg_get(raw, "deposit.cycle")
    return BacktestSettings(
        deposit_cycle=cycle,
        deposit_day=(_cfg_int(raw, "deposit.day") if cycle == "monthly" else 1),
        deposit_n=(_cfg_int(raw, "deposit.n")
                   if cycle == "every_n_trading_days" else 1),
        deposit_amount=_cfg_num(raw, "deposit.amount"),
        currency=_cfg_get(raw, "deposit.currency"),
        buy_fee_pct=_cfg_num(raw, "costs.buy_fee_pct"),
        fx_cost_pct=_cfg_num(raw, "costs.fx_cost_pct"),
        withholding_pct=_cfg_num(raw, "costs.dividend_withholding_pct"),
        limit_margin_pct=_cfg_num(raw, "order.limit_margin_pct"),
        fractional=_cfg_bool(raw, "shares.fractional"),
    )


def _load_fx(store: Store) -> dict[dt.date, Decimal]:
    rows = store._conn.execute("SELECT date, usd_krw FROM fx_rates").fetchall()
    return {dt.date.fromisoformat(d): Decimal(v) for d, v in rows}


def _metrics_dict(m: RuleMetrics) -> dict:
    out = {}
    for k, v in m.__dict__.items():
        out[k] = str(v) if isinstance(v, Decimal) else v
    return out


def run_backtest(store: Store, rules_path, config: Config) -> dict:
    raw = config.raw
    rules = _load_rules(rules_path)
    settings = _backtest_settings(raw)
    holdout = _cfg_int(raw, "adoption.holdout_years")
    window_years = _cfg_int(raw, "adoption.rolling_window_years")
    min_out = _cfg_num(raw, "adoption.min_outperformance_pct")
    min_ratio = _cfg_num(raw, "adoption.min_rolling_ratio_pct")

    bars = store.list_bars()
    if not bars:
        raise ConfigError("no bars imported")
    fx = _load_fx(store)
    one_day = dt.timedelta(days=1)
    last = bars[-1].date
    cut = _add_years(last, -holdout)
    tuning = [b for b in bars if b.date <= cut]
    evaluation = [b for b in bars if b.date > cut]
    if not tuning or not evaluation:
        raise ConfigError("holdout split leaves an empty segment")

    seg_out = {}
    sims = {}
    for name, seg, start, end in (
            ("tuning", tuning, tuning[0].date.isoformat(), cut.isoformat()),
            ("evaluation", evaluation, (cut + one_day).isoformat(),
             last.isoformat())):
        sim = simulate(seg, rules, settings, fx)
        sims[name] = sim
        seg_out[name] = {
            "start": start, "end": end,
            "rules": {rid: _metrics_dict(m) for rid, m in sim.metrics.items()},
        }

    pairs: dict[str, list[tuple[Decimal, Decimal]]] = {r.id: [] for r in rules}
    seen_months: set[tuple[int, int]] = set()
    window_count = 0
    for b in bars:
        key = (b.date.year, b.date.month)
        if key in seen_months:
            continue
        seen_months.add(key)
        bound = _add_years(b.date, window_years) - one_day
        if bound > last:
            continue
        window = [x for x in bars if b.date <= x.date <= bound]
        res = simulate(window, rules, settings, fx)
        window_count += 1
        base = res.metrics["baseline"].final_shares
        for r in rules:
            pairs[r.id].append((res.metrics[r.id].final_shares, base))
    if window_count == 0:
        raise ConfigError("no complete rolling windows")

    rolling = {}
    adoption = {}
    selected = "baseline"
    best = None
    ev = sims["evaluation"].metrics
    base_ev = ev["baseline"].final_shares
    for r in rules:
        ps = pairs[r.id]
        res = evaluate_adoption(ev[r.id].final_shares, base_ev, ps,
                                min_out, min_ratio)
        rolling[r.id] = {
            "windows": len(ps),
            "at_or_above_baseline": sum(1 for a, c in ps if a >= c),
            "ratio_pct": str(res.rolling_ratio_pct),
        }
        adoption[r.id] = {
            "adopted": res.adopted,
            "outperformance_pct": (None if res.outperformance_pct is None
                                   else str(res.outperformance_pct)),
            "rolling_ratio_pct": str(res.rolling_ratio_pct),
        }
        if res.adopted and (best is None or ev[r.id].final_shares > best):
            best = ev[r.id].final_shares
            selected = r.id

    return {
        "segments": seg_out,
        "rolling": rolling,
        "adoption": adoption,
        "selected_rule": selected,
        "data": {
            "bars_sha256": store.snapshot_sha256("bars"),
            "calendar_sha256": store.snapshot_sha256("calendar"),
            "fx_sha256": store.snapshot_sha256("fx"),
        },
    }


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
    from decimal import ROUND_DOWN, ROUND_HALF_UP

    hundred = Decimal(100)
    one = Decimal(1)
    limit_price = (prev_close * (one + limit_margin_pct / hundred)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    candidates = [
        ("RULE", rule_amount),
        ("CASH", orderable_cash),
        ("PER_ORDER_LIMIT", per_order_limit),
        ("MONTHLY_LIMIT", monthly_remaining),
    ]
    binding, amount = candidates[0]
    for name, value in candidates[1:]:
        if value < amount:
            binding, amount = name, value
    if amount < 0:
        amount = Decimal(0)
    unit = limit_price * (one + buy_fee_pct / hundred)
    raw = amount / unit if unit > 0 else Decimal(0)
    quantity = raw.quantize(
        Decimal("0.000001") if fractional else Decimal("1"), rounding=ROUND_DOWN
    )
    if quantity > 0:
        reason = None
    elif binding == "MONTHLY_LIMIT":
        reason = "MONTHLY_LIMIT_REACHED"
    else:
        reason = "INSUFFICIENT_CASH"
    return OrderPlan(
        limit_price=limit_price,
        quantity=quantity,
        amount=amount,
        binding=binding,
        reason=reason,
    )


def is_in_order_window(
    now: dt.datetime,
    window_start: dt.time,
    window_end: dt.time,
    close_time: dt.time,
    tz_loader: Callable[[str], dt.tzinfo] = zoneinfo.ZoneInfo,
) -> bool:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    local = now.astimezone(tz_loader("America/New_York"))
    base = dt.date(2000, 1, 1)
    shift = (dt.datetime.combine(base, dt.time(16, 0))
             - dt.datetime.combine(base, close_time))
    start = dt.datetime.combine(base, window_start) - shift
    end = dt.datetime.combine(base, window_end) - shift
    t = dt.datetime.combine(base, local.time().replace(tzinfo=None))
    return start <= t <= end


def run_once(
    config: Config,
    store: Store,
    *,
    broker: Broker | None,
    notifier: Notifier,
    now: dt.datetime,
    tz_loader: Callable[[str], dt.tzinfo] = zoneinfo.ZoneInfo,
) -> RunResult:
    try:
        tz = tz_loader("America/New_York")
    except Exception:
        _safe_send(notifier, Notification(
            kind="ERROR", trade_date=None, reason="TIMEZONE_UNAVAILABLE",
            text="America/New_York timezone is unavailable"))
        return RunResult(exit_code=2, reasons=["TIMEZONE_UNAVAILABLE"],
                         orders_sent=0)
    ny_date = now.astimezone(tz).date()
    try:
        _validate_run_config(config)
    except ConfigError as exc:
        _safe_send(notifier, Notification(
            kind="ERROR", trade_date=ny_date, reason="CONFIG_ERROR",
            text=str(exc)))
        return RunResult(exit_code=2, reasons=["CONFIG_ERROR"], orders_sent=0)
    return _run_once_body(config, store, broker, notifier, now, tz, ny_date)


def _q(value: Decimal, exp: str, mode) -> Decimal:
    return value.quantize(Decimal(exp), rounding=mode)


def _reconcile(store: Store, broker, config: Config, now, tz) -> None:
    from decimal import ROUND_CEILING, ROUND_HALF_UP

    linked: set[str] = set()
    fee_pct = _cfg_num(config.raw, "costs.buy_fee_pct")
    pending = [o for o in store._orders_raw()
               if o["status"] in ("SENT", "SENDING", "UNKNOWN")]
    cache: dict[str, list[BrokerOrder]] = {}
    for o in pending:
        td = o["trade_date"]
        if td not in cache:
            cache[td] = list(broker.list_orders(dt.date.fromisoformat(td)))
        match = None
        for b in cache[td]:
            if o["client_order_id"] and b.client_order_id == o["client_order_id"]:
                match = b
                break
        if match is None:
            used = {x["broker_order_id"] for x in store._orders_raw()
                    if x["broker_order_id"]} | linked
            for b in cache[td]:
                if (b.symbol == "QQQ" and b.side == "BUY"
                        and b.quantity == Decimal(o["quantity"])
                        and b.limit_price == Decimal(o["limit_price"])
                        and b.broker_order_id not in used):
                    match = b
                    break
        if match is not None:
            linked.add(match.broker_order_id)
        if match is None:
            if o["status"] not in ("SENDING", "UNKNOWN"):
                continue
            if o["status"] == "SENDING":
                store._set_order_status(o["id"], "UNKNOWN")
            row =store._conn.execute(
                "SELECT close_time FROM calendar WHERE date = ?", (td,)).fetchone()
            if row is not None and row[0]:
                close_t = dt.datetime.strptime(row[0], "%H:%M").time()
                close_dt = dt.datetime.combine(
                    dt.date.fromisoformat(td), close_t, tzinfo=tz)
                if (now.astimezone(tz) >= close_dt
                        and broker.get_position("QQQ") == store.holdings()):
                    store._set_order_status(o["id"], "NOT_PLACED")
            continue
        if match.status == "OPEN":
            if o["status"] != "SENT":
                store._set_order_status(o["id"], "SENT", match.broker_order_id)
        elif match.status == "FILLED" and match.fill_price is not None:
            qty = Decimal(o["quantity"])
            cost = _q(qty * match.fill_price, "0.01", ROUND_HALF_UP)
            fee = _q(cost * fee_pct / Decimal(100), "0.01", ROUND_CEILING)
            store._mark_filled(o["id"], qty, match.fill_price, cost + fee,
                               match.broker_order_id)
        elif match.status == "UNFILLED":
            store._set_order_status(o["id"], "UNFILLED", match.broker_order_id)
        elif match.status == "REJECTED":
            store._set_order_status(o["id"], "REJECTED", match.broker_order_id)


def _run_once_body(config, store, broker, notifier, now, tz, ny_date):
    from decimal import ROUND_CEILING  # noqa: F401

    raw = config.raw
    reasons: list[str] = []
    state = {"sent": 0}

    def finish(code: int, reason: str | None = None) -> RunResult:
        if reason is not None:
            reasons.append(reason)
        if code == 1 and reasons:
            r = reasons[-1]
            if store._first_notification(ny_date, "SAFETY", r):
                _safe_send(notifier, Notification(
                    kind="SAFETY", trade_date=ny_date, reason=r, text=r))
        elif code == 2 and reasons:
            r = reasons[-1]
            _safe_send(notifier, Notification(
                kind="ERROR", trade_date=ny_date, reason=r, text=r))
        try:
            store._log_run(now, code, reasons)
        except sqlite3.Error:
            pass
        return RunResult(exit_code=code, reasons=list(reasons),
                         orders_sent=state["sent"])

    def warn(reason: str) -> None:
        if store._first_notification(ny_date, "WARNING", reason):
            _safe_send(notifier, Notification(
                kind="WARNING", trade_date=ny_date, reason=reason, text=reason))

    if config.stage == "live":
        return finish(2, "STAGE_NOT_SUPPORTED")
    if broker is None:
        return finish(2, "NO_BROKER_ADAPTER")

    try:
        _reconcile(store, broker, config, now, tz)
        position = broker.get_position("QQQ")
    except BrokerError:
        return finish(2, "BROKER_ERROR")
    if position != store.holdings():
        return finish(1, "POSITION_MISMATCH")
    if any(o["status"] in ("SENDING", "UNKNOWN") for o in store._orders_raw()):
        return finish(1, "UNRESOLVED_ORDER")
    if Path(_cfg_get(raw, "paths.halt_file")).exists():
        return finish(1, "HALT_FILE")

    conn = store._conn
    row = conn.execute("SELECT is_open, close_time FROM calendar WHERE date = ?",
                       (ny_date.isoformat(),)).fetchone()
    if row is None:
        return finish(1, "CALENDAR_MISSING")
    if not row[0]:
        return finish(0, "MARKET_CLOSED")
    close_time = dt.datetime.strptime(row[1], "%H:%M").time()
    if not is_in_order_window(
            now, _cfg_hhmm(raw, "order_window.start"),
            _cfg_hhmm(raw, "order_window.end"), close_time,
            tz_loader=lambda _name: tz):
        return finish(0, "OUTSIDE_WINDOW")

    if "operating_rule" in raw and \
            _cfg_get(raw, "operating_rule.type") == "close_at_or_below":
        threshold = _cfg_num(raw, "operating_rule.threshold_usd")
        rule = Rule(f"le{threshold.normalize():f}", "close_at_or_below",
                    threshold)
    else:
        rule = Rule("baseline", "baseline")

    orders = store._orders_raw()
    if any(o["trade_date"] == ny_date.isoformat() and o["rule_id"] == rule.id
           for o in orders):
        return finish(0, "ALREADY_ORDERED")

    bars = [b for b in store.list_bars() if b.date < ny_date]
    prev_row = conn.execute(
        "SELECT MAX(date) FROM calendar WHERE is_open = 1 AND date < ?",
        (ny_date.isoformat(),)).fetchone()
    if not bars or prev_row[0] is None or \
            bars[-1].date != dt.date.fromisoformat(prev_row[0]):
        return finish(1, "STALE_BAR")
    bar = bars[-1]
    if len(bars) >= 2:
        prev_close = bars[-2].close / bar.split_factor
        change = abs(bar.close - prev_close) / prev_close * Decimal(100)
        if change > _cfg_num(raw, "guard.abnormal_price_pct"):
            return finish(1, "ABNORMAL_PRICE")

    try:
        cash = broker.get_orderable_cash_usd()
    except BrokerError:
        return finish(2, "BROKER_ERROR")

    if rule.type == "baseline":
        is_deposit = _is_deposit_day(conn, raw, ny_date)
    else:
        is_deposit = False
    amount = _decide_amount(rule, bar, cash, is_deposit)
    if amount <= 0:
        return finish(0, "NO_SIGNAL")

    month_prefix = ny_date.strftime("%Y-%m-")
    used = Decimal(0)
    for o in orders:
        if not o["trade_date"].startswith(month_prefix):
            continue
        if o["status"] == "FILLED" and o["fill_cost"] is not None:
            used += Decimal(o["fill_cost"])
        elif o["status"] in ("SENDING", "SENT", "UNKNOWN"):
            used += Decimal(o["quantity"]) * Decimal(o["limit_price"])
    monthly_remaining = _cfg_num(raw, "limits.monthly_usd") - used

    plan = compute_order(
        bar.close, _cfg_num(raw, "order.limit_margin_pct"), amount, cash,
        _cfg_num(raw, "limits.per_order_usd"), monthly_remaining,
        _cfg_num(raw, "costs.buy_fee_pct"), _cfg_bool(raw, "shares.fractional"))
    if plan.quantity <= 0:
        if plan.reason == "MONTHLY_LIMIT_REACHED":
            return finish(1, "MONTHLY_LIMIT_REACHED")
        warn("INSUFFICIENT_CASH")
        return finish(0, "INSUFFICIENT_CASH")
    if plan.binding == "PER_ORDER_LIMIT":
        reasons.append("PER_ORDER_LIMIT_APPLIED")
        warn("PER_ORDER_LIMIT_APPLIED")

    if config.stage == "dry-run":
        store.insert_order_intent(ny_date, rule.id, plan.quantity,
                                  plan.limit_price, "DRY_RUN")
        return finish(0, "DRY_RUN_RECORDED")

    client_id = f"{ny_date.isoformat()}-{rule.id}"
    try:
        order_id = store.insert_order_intent(
            ny_date, rule.id, plan.quantity, plan.limit_price, "SENDING")
    except DuplicateOrderError:
        return finish(0, "ALREADY_ORDERED")
    store._set_client_order_id(order_id, client_id)
    try:
        broker_id = broker.place_loc_buy(OrderRequest(
            client_id, "QQQ", ny_date, plan.quantity, plan.limit_price))
    except BrokerTimeout:
        return finish(2, "BROKER_TIMEOUT")
    except BrokerRejected:
        store._set_order_status(order_id, "REJECTED")
        return finish(2, "BROKER_ERROR")
    except BrokerError:
        return finish(2, "BROKER_ERROR")
    store._set_order_status(order_id, "SENT", broker_id)
    state["sent"] = 1
    return finish(0, "ORDER_SENT")


def _is_deposit_day(conn, raw, d: dt.date) -> bool:
    cycle = _cfg_get(raw, "deposit.cycle")
    days = [dt.date.fromisoformat(r[0]) for r in conn.execute(
        "SELECT date FROM calendar WHERE is_open = 1 ORDER BY date")]
    if d not in days:
        return False
    if cycle == "monthly":
        dd = _cfg_get(raw, "deposit.day")
        month = [x for x in days if (x.year, x.month) == (d.year, d.month)]
        chosen = month[-1]
        for x in month:
            if x.day >= dd:
                chosen = x
                break
        return chosen == d
    n = _cfg_get(raw, "deposit.n")
    anchor = _cfg_get(raw, "deposit.anchor_date")
    anchor = dt.date.fromisoformat(anchor if isinstance(anchor, str)
                                   else str(anchor))
    if d < anchor:
        return False
    idx = sum(1 for x in days if anchor <= x < d)
    return idx % n == 0


def get_status(store: Store) -> dict:
    raise NotImplementedError("get_status")


def record_adjustment(store: Store, shares: Decimal, reason: str) -> None:
    raise NotImplementedError("record_adjustment")


class FakeBroker:
    """In-memory, buy-only broker for tests (no network)."""

    def __init__(self, orderable_cash: Decimal, position: Decimal) -> None:
        self._orderable_cash = Decimal(orderable_cash)
        self._position = Decimal(position)
        self._orders: list[BrokerOrder] = []
        self._next_id = 1
        self._fail_mode: str | None = None
        self.place_calls = 0

    def get_orderable_cash_usd(self) -> Decimal:
        return self._orderable_cash

    def get_position(self, symbol: str) -> Decimal:
        return self._position

    def place_loc_buy(self, request: OrderRequest) -> str:
        self.place_calls += 1
        mode, self._fail_mode = self._fail_mode, None
        if mode in ("timeout", "timeout_before_accept"):
            raise BrokerTimeout("timeout")
        if mode == "reject":
            raise BrokerRejected("rejected")
        if mode == "error":
            raise BrokerError("error")
        bid = f"FB-{self._next_id}"
        self._next_id += 1
        self._orderable_cash -= request.quantity * request.limit_price
        self._orders.append(BrokerOrder(
            bid, request.client_order_id, request.symbol, "BUY",
            request.quantity, request.limit_price, request.trade_date, "OPEN"))
        if mode == "timeout_after_accept":
            raise BrokerTimeout("timeout after accept")
        return bid

    def list_orders(self, trade_date: dt.date) -> list[BrokerOrder]:
        return [o for o in self._orders if o.trade_date == trade_date]

    def settle_close(self, trade_date: dt.date, close: Decimal) -> None:
        import dataclasses
        from decimal import ROUND_HALF_UP

        close = Decimal(close)
        for i, o in enumerate(self._orders):
            if o.trade_date != trade_date or o.status != "OPEN":
                continue
            reserved = o.quantity * o.limit_price
            if close <= o.limit_price:
                cost = _q(o.quantity * close, "0.01", ROUND_HALF_UP)
                self._position += o.quantity
                self._orderable_cash += reserved - cost
                self._orders[i] = dataclasses.replace(
                    o, status="FILLED", fill_price=close)
            else:
                self._orderable_cash += reserved
                self._orders[i] = dataclasses.replace(o, status="UNFILLED")

    def set_position(self, qty: Decimal) -> None:
        self._position = Decimal(qty)

    def set_orderable_cash(self, amount: Decimal) -> None:
        self._orderable_cash = Decimal(amount)

    def fail_next_place(self, mode: str) -> None:
        self._fail_mode = mode


class FakeNotifier:
    """Records notifications in `messages`; raises on send when `fail`."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.messages: list[Notification] = []

    def send(self, notification: Notification) -> None:
        if self.fail:
            raise RuntimeError("notifier failure")
        self.messages.append(notification)
