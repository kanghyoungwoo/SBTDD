"""Plain data types, exceptions and protocols of the public API."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol


class ConfigError(Exception):
    """Configuration file or key is missing or malformed."""


class DataImportError(Exception):
    """A CSV snapshot was rejected."""


class DuplicateOrderError(Exception):
    """An order for the same (trade_date, rule_id) already exists."""


class BrokerError(Exception):
    """Generic broker failure."""


class BrokerTimeout(BrokerError):
    """The broker call timed out; the result is unknown."""


class BrokerRejected(BrokerError):
    """The broker rejected the order."""


@dataclass
class Config:
    stage: str = "dry-run"
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Bar:
    date: dt.date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    split_factor: Decimal
    dividend: Decimal


@dataclass(frozen=True)
class Rule:
    id: str
    type: str
    threshold_usd: Decimal | None = None


@dataclass(frozen=True)
class BacktestSettings:
    deposit_cycle: str
    deposit_day: int
    deposit_n: int
    deposit_amount: Decimal
    currency: str
    buy_fee_pct: Decimal
    fx_cost_pct: Decimal
    withholding_pct: Decimal
    limit_margin_pct: Decimal
    fractional: bool


@dataclass(frozen=True)
class Decision:
    date: dt.date
    rule_id: str
    quantity: Decimal
    limit_price: Decimal


@dataclass(frozen=True)
class RuleMetrics:
    final_shares: Decimal
    cash_usd: Decimal
    equivalent_shares: Decimal
    total_deposit_usd: Decimal
    average_cost_usd: Decimal | None
    cash_waiting_days: int
    unfilled_count: int
    final_shares_diff_vs_baseline: Decimal
    equivalent_shares_diff_vs_baseline: Decimal


@dataclass
class SimulationResult:
    metrics: dict[str, RuleMetrics] = field(default_factory=dict)
    decisions: list[Decision] = field(default_factory=list)


@dataclass(frozen=True)
class AdoptionResult:
    adopted: bool
    outperformance_pct: Decimal | None
    rolling_ratio_pct: Decimal


@dataclass(frozen=True)
class OrderPlan:
    limit_price: Decimal
    quantity: Decimal
    amount: Decimal
    binding: str
    reason: str | None


@dataclass(frozen=True)
class ImportResult:
    kind: str
    rows: int
    sha256: str


@dataclass(frozen=True)
class OrderRecord:
    trade_date: dt.date
    rule_id: str
    status: str
    quantity: Decimal
    limit_price: Decimal
    broker_order_id: str | None
    fill_price: Decimal | None
    fill_cost: Decimal | None


@dataclass
class RunResult:
    exit_code: int
    reasons: list[str] = field(default_factory=list)
    orders_sent: int = 0


@dataclass(frozen=True)
class OrderRequest:
    client_order_id: str
    symbol: str
    trade_date: dt.date
    quantity: Decimal
    limit_price: Decimal


@dataclass(frozen=True)
class BrokerOrder:
    broker_order_id: str
    client_order_id: str
    symbol: str
    side: str
    quantity: Decimal
    limit_price: Decimal
    trade_date: dt.date
    status: str  # "OPEN" | "FILLED" | "UNFILLED" | "REJECTED"
    fill_price: Decimal | None = None


@dataclass(frozen=True)
class Notification:
    kind: str  # "DAILY_SUMMARY" | "WARNING" | "SAFETY" | "ERROR"
    trade_date: dt.date | None
    reason: str
    text: str


class Broker(Protocol):
    def get_orderable_cash_usd(self) -> Decimal: ...

    def get_position(self, symbol: str) -> Decimal: ...

    def place_loc_buy(self, request: OrderRequest) -> str: ...

    def list_orders(self, trade_date: dt.date) -> list[BrokerOrder]: ...


class Notifier(Protocol):
    def send(self, notification: Notification) -> None: ...
