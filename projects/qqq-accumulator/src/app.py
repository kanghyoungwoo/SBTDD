"""Public API stubs. Behaviour is intentionally not implemented yet."""
from __future__ import annotations

import datetime as dt
import sqlite3
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
    raise NotImplementedError("main")


def load_config(path) -> Config:
    raise NotImplementedError("load_config")


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
        raise NotImplementedError("Store.list_bars")

    def snapshot_sha256(self, kind: str) -> str | None:
        """Recorded SHA-256 of the latest snapshot of `kind` ("calendar"/"bars"/"fx")."""
        raise NotImplementedError("Store.snapshot_sha256")

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None


def import_csv(store: Store, path) -> ImportResult:
    raise NotImplementedError("import_csv")


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
