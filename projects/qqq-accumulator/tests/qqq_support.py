"""Shared helpers for the scenario tests (standard library only)."""
import hashlib
import io
import json
import os
import shutil
import tempfile
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from src.app import (
    BacktestSettings,
    Bar,
    FakeBroker,
    FakeNotifier,
    Store,
    import_csv,
    load_config,
    main,
    run_once,
)

DB_NAME = "qqq.db"


def d(text):
    return date.fromisoformat(text)


def et(month, day, hour=0, minute=0, year=2026):
    return datetime(year, month, day, hour, minute, tzinfo=ZoneInfo("America/New_York"))


def write_text(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path


def sha256_file(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def all_days(start, end):
    out = []
    cur = start
    while cur <= end:
        out.append(cur)
        cur += timedelta(days=1)
    return out


def open_days(start, end, closed=()):
    return [x for x in all_days(start, end) if x.weekday() < 5 and x not in closed]


def new_root(case):
    root = tempfile.mkdtemp(prefix="qqq-")
    case.addCleanup(shutil.rmtree, root, True)
    return root


def db_path(root):
    return os.path.join(root, DB_NAME)


def new_store(case, root=None):
    root = root or new_root(case)
    store = Store.open(db_path(root))
    case.addCleanup(store.close)
    return root, store


def write_calendar(path, start, end, closed=(), early=None):
    early = early or {}
    lines = ["date,is_open,close_time"]
    for day in all_days(start, end):
        if day.weekday() >= 5 or day in closed:
            lines.append("%s,false," % day.isoformat())
        else:
            lines.append("%s,true,%s" % (day.isoformat(), early.get(day, "16:00")))
    return write_text(path, "\n".join(lines) + "\n")


def write_bars(path, dates, closes=None, overrides=None):
    """Write a daily-bar CSV. `closes` maps date->close text, `overrides` maps
    date->dict of column overrides. Dates may repeat (duplicate-row tests)."""
    closes = closes or {}
    overrides = overrides or {}
    lines = ["date,open,high,low,close,volume,split_factor,dividend"]
    for day in dates:
        c = closes.get(day, "100")
        row = {
            "open": c, "high": c, "low": c, "close": c,
            "volume": "1000", "split_factor": "1", "dividend": "0",
        }
        row.update(overrides.get(day, {}))
        lines.append(",".join([
            day.isoformat(), row["open"], row["high"], row["low"], row["close"],
            row["volume"], row["split_factor"], row["dividend"],
        ]))
    return write_text(path, "\n".join(lines) + "\n")


def write_rules(path, items):
    return write_text(path, json.dumps({"rules": items}))


CONFIG_DEFAULTS = [
    ("deposit.cycle", '"monthly"'),
    ("deposit.day", "1"),
    ("deposit.n", "2"),
    ("deposit.anchor_date", '"2026-10-01"'),
    ("deposit.amount", "100"),
    ("deposit.currency", '"USD"'),
    ("limits.per_order_usd", "1000"),
    ("limits.monthly_usd", "5000"),
    ("costs.buy_fee_pct", "0"),
    ("costs.fx_cost_pct", "0"),
    ("costs.dividend_withholding_pct", "0"),
    ("order_window.start", '"15:00"'),
    ("order_window.end", '"15:45"'),
    ("order.limit_margin_pct", "2"),
    ("guard.abnormal_price_pct", "10"),
    ("shares.fractional", "false"),
    ("adoption.holdout_years", "1"),
    ("adoption.rolling_window_years", "1"),
    ("adoption.min_outperformance_pct", "0"),
    ("adoption.min_rolling_ratio_pct", "50"),
    ("paper.clean_days_required", "3"),
    ("operating_rule.type", '"close_at_or_below"'),
    ("operating_rule.threshold_usd", "200"),
]


def write_config(path, database, halt_file, *, stage="paper", overrides=None, omit=()):
    """Write a TOML config. `overrides` maps "section.key" -> TOML literal."""
    table = {
        "paths.database": json.dumps(database),
        "paths.halt_file": json.dumps(halt_file),
    }
    table.update(CONFIG_DEFAULTS)
    table.update(overrides or {})
    for key in omit:
        table.pop(key, None)
    sections = {}
    for key, literal in table.items():
        section, name = key.split(".", 1)
        sections.setdefault(section, []).append((name, literal))
    lines = []
    if stage is not None:
        lines.append("stage = %s" % json.dumps(stage))
    for section, items in sections.items():
        lines.append("[%s]" % section)
        for name, literal in items:
            lines.append("%s = %s" % (name, literal))
    return write_text(path, "\n".join(lines) + "\n")


CAL_START = date(2026, 10, 1)
CAL_END = date(2026, 12, 31)
CLOSED = (date(2026, 11, 26),)
EARLY = {date(2026, 11, 27): "13:00"}


class FixtureF:
    """Common operating fixture F (design section 11)."""

    def __init__(self, case, *, stage="paper", overrides=None, omit=(),
                 bars_until=date(2026, 11, 4), closes=None, bar_overrides=None,
                 cash="500", position="0", notifier_fail=False, halt=False):
        self.root = new_root(case)
        self.db_path = db_path(self.root)
        self.halt_path = os.path.join(self.root, "HALT")
        self.config_path = os.path.join(self.root, "config.toml")
        self.calendar_path = os.path.join(self.root, "calendar.csv")
        self.bars_path = os.path.join(self.root, "bars.csv")
        self._closes = closes
        self._bar_overrides = bar_overrides
        write_calendar(self.calendar_path, CAL_START, CAL_END, CLOSED, EARLY)
        write_bars(self.bars_path, open_days(CAL_START, bars_until, CLOSED),
                   closes, bar_overrides)
        write_config(self.config_path, self.db_path, self.halt_path,
                     stage=stage, overrides=overrides, omit=omit)
        if halt:
            write_text(self.halt_path, "")
        self.store = Store.open(self.db_path)
        case.addCleanup(self.store.close)
        import_csv(self.store, self.calendar_path)
        import_csv(self.store, self.bars_path)
        self.config = load_config(self.config_path)
        self.broker = FakeBroker(Decimal(cash), Decimal(position))
        self.notifier = FakeNotifier(fail=notifier_fail)

    def run(self, now, **kw):
        return run_once(self.config, self.store, broker=self.broker,
                        notifier=self.notifier, now=now, **kw)

    def cli(self, *args, **kw):
        out, err = io.StringIO(), io.StringIO()
        code = main(["--config", self.config_path, *args],
                    stdout=out, stderr=err, **kw)
        return code, out.getvalue(), err.getvalue()

    def reimport_bars(self, until):
        path = os.path.join(self.root, "bars_%s.csv" % until.isoformat())
        write_bars(path, open_days(CAL_START, until, CLOSED),
                   self._closes, self._bar_overrides)
        return import_csv(self.store, path)

    def order_on(self, day):
        rows = [o for o in self.store.list_orders() if o.trade_date == day]
        return rows[0] if rows else None


def notes(notifier, kind=None, reason=None, trade_date=None):
    return [
        m for m in notifier.messages
        if (kind is None or m.kind == kind)
        and (reason is None or m.reason == reason)
        and (trade_date is None or m.trade_date == trade_date)
    ]


def week_store(case):
    """Fresh DB with the calendar 2026-11-02..2026-11-06 (weekdays open) imported."""
    root, store = new_store(case)
    cal = write_calendar(os.path.join(root, "calendar.csv"),
                         date(2026, 11, 2), date(2026, 11, 6))
    import_csv(store, cal)
    return root, store


WEEK = open_days(date(2026, 11, 2), date(2026, 11, 6))


def backtest_setup(case, rule_items):
    """DB with 2024-2025 calendar and flat bars (close 100), config and rules."""
    root, store = new_store(case)
    start, end = date(2024, 1, 1), date(2025, 12, 31)
    cal = write_calendar(os.path.join(root, "calendar.csv"), start, end)
    bars = write_bars(os.path.join(root, "bars.csv"), open_days(start, end))
    import_csv(store, cal)
    import_csv(store, bars)
    cfg = write_config(
        os.path.join(root, "config.toml"), db_path(root), os.path.join(root, "HALT"),
        overrides={"order.limit_margin_pct": "0", "shares.fractional": "true"},
    )
    rules = write_rules(os.path.join(root, "rules.json"), rule_items)
    return SimpleNamespace(root=root, store=store, config=cfg, rules=rules,
                           bars_sha=sha256_file(bars))


def make_bars(closes, start=date(2026, 3, 2), splits=None, dividends=None):
    """Consecutive weekday bars with OHLC == close. splits/dividends keyed by 0-based index."""
    splits = splits or {}
    dividends = dividends or {}
    days = []
    cur = start
    while len(days) < len(closes):
        if cur.weekday() < 5:
            days.append(cur)
        cur += timedelta(days=1)
    bars = []
    for i, (day, close) in enumerate(zip(days, closes)):
        c = Decimal(str(close))
        bars.append(Bar(
            date=day, open=c, high=c, low=c, close=c, volume=1000,
            split_factor=Decimal(str(splits.get(i, 1))),
            dividend=Decimal(str(dividends.get(i, 0))),
        ))
    return bars


def make_settings(**kw):
    base = dict(
        deposit_cycle="every_n_trading_days", deposit_day=1, deposit_n=2,
        deposit_amount=Decimal("100"), currency="USD",
        buy_fee_pct=Decimal("0"), fx_cost_pct=Decimal("0"),
        withholding_pct=Decimal("0"), limit_margin_pct=Decimal("0"),
        fractional=True,
    )
    base.update(kw)
    return BacktestSettings(**base)


def decisions_of(result, rule_id):
    return [(x.date, x.quantity, x.limit_price)
            for x in result.decisions if x.rule_id == rule_id]
