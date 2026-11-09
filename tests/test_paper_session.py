"""Session-level regression tests for the bugs that suppressed trading."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent),
)

from platform_core.analytics.atr_tracker import (  # noqa: E402
    ATRTracker,
)

from platform_core.backtesting.historical_replay import (  # noqa: E402
    HistoricalReplayFeed,
)

from platform_core.intelligence.rolling_bias import (  # noqa: E402
    RollingBiasTracker,
)

from platform_core.paper_trading.paper_session import (  # noqa: E402
    PaperSession,
    SessionConfig,
)

from platform_core.paper_trading.trade_logger import (  # noqa: E402
    TradeLogger,
)


DATA = "data/banknifty_real.csv"


class Bar:

    def __init__(self, high, low, close, timestamp=None):

        self.symbol = "BANKNIFTY"
        self.timeframe = "MIN_1"
        self.open_price = close
        self.high_price = high
        self.low_price = low
        self.close_price = close
        self.volume = 0.0
        self.start_timestamp = (
            timestamp
            or datetime(2026, 8, 10, 10, 0)
        )
        self.end_timestamp = (
            timestamp
            or datetime(2026, 8, 10, 10, 0)
        )


def session_for(tmp_path) -> PaperSession:

    config = SessionConfig()

    return PaperSession(
        config=config,
        trade_logger=TradeLogger(
            log_path=str(tmp_path / "trades.csv")
        ),
    )


def test_atr_is_causal_and_excludes_the_current_bar():
    """Feeding a bar's own range in as its average made every regime NORMAL."""

    tracker = ATRTracker(window=5)

    assert tracker.update(bar=Bar(110, 90, 100)) is None

    second = tracker.update(bar=Bar(105, 95, 100))

    assert second == pytest.approx(20.0)


def test_rolling_bias_reports_neutral_until_warm():
    """An unseeded timeframe must not cast a directional vote."""

    tracker = RollingBiasTracker()

    tracker.update(bar=Bar(101, 99, 100))

    assert tracker.biases() == {
        "m15_bias": "NEUTRAL",
        "h1_bias": "NEUTRAL",
        "h4_bias": "NEUTRAL",
        "daily_bias": "NEUTRAL",
    }


def test_rolling_bias_turns_directional_with_history():

    tracker = RollingBiasTracker()

    for index in range(20):

        price = 100.0 + index

        tracker.update(bar=Bar(price + 1, price - 1, price))

    assert tracker.biases()["m15_bias"] == "BULLISH"


def test_rolling_bias_detects_downtrend():

    tracker = RollingBiasTracker()

    for index in range(20):

        price = 100.0 - index

        tracker.update(bar=Bar(price + 1, price - 1, price))

    assert tracker.biases()["m15_bias"] == "BEARISH"


def test_replay_completes_round_trips(tmp_path):
    """The core regression: signals must produce *closed* trades."""

    session = session_for(tmp_path)

    bars = HistoricalReplayFeed().load_csv(
        path=DATA,
        symbol="BANKNIFTY",
    )

    for bar in bars:

        session.process_bar(live_bar=bar)

    session.force_flat(live_bar=bars[-1])

    summary = session.summary()

    assert summary.total_trades > 0
    assert (
        summary.winning_trades
        + summary.losing_trades
        == summary.total_trades
    )


def test_replay_is_deterministic(tmp_path):

    bars = HistoricalReplayFeed().load_csv(
        path=DATA,
        symbol="BANKNIFTY",
    )

    results = []

    for run in range(2):

        session = session_for(
            tmp_path / f"run{run}"
        )

        for bar in bars:

            session.process_bar(live_bar=bar)

        session.force_flat(live_bar=bars[-1])

        results.append(
            session.summary().total_pnl
        )

    assert results[0] == results[1]


def test_no_position_survives_the_session(tmp_path):
    """Every position must be closed by an exit path, not left dangling."""

    session = session_for(tmp_path)

    bars = HistoricalReplayFeed().load_csv(
        path=DATA,
        symbol="BANKNIFTY",
    )

    for bar in bars:

        session.process_bar(live_bar=bar)

    session.force_flat(live_bar=bars[-1])

    assert session.paper_broker.positions == {}


def test_session_rollover_resets_daily_risk_state(tmp_path):
    """A session halt must not latch into the following trading day."""

    session = session_for(tmp_path)

    session.process_bar(
        live_bar=Bar(
            101,
            99,
            100,
            datetime(2026, 8, 10, 10, 0),
        )
    )

    session.realized_pnl_day = -5000.0
    session.consecutive_losses = 6

    session.process_bar(
        live_bar=Bar(
            101,
            99,
            100,
            datetime(2026, 8, 11, 9, 20),
        )
    )

    assert session.realized_pnl_day == 0.0
    assert session.consecutive_losses == 0


def test_trades_span_every_active_day(tmp_path):
    """Regression for state bleeding across days and killing later sessions."""

    session = session_for(tmp_path)

    bars = HistoricalReplayFeed().load_csv(
        path=DATA,
        symbol="BANKNIFTY",
    )

    for bar in bars:

        session.process_bar(live_bar=bar)

    session.force_flat(live_bar=bars[-1])

    trade_days = {
        trade.entry_timestamp.date()
        for trade in (
            session.paper_broker
            .completed_trades
        )
    }

    assert len(trade_days) > 1


def test_logger_refuses_to_clobber_populated_legacy_log(tmp_path):

    legacy = tmp_path / "old.csv"

    legacy.write_text(
        "symbol,direction,entry_price,exit_price,quantity,pnl\n"
        "BANKNIFTY,LONG,100,110,35,350\n"
    )

    with pytest.raises(RuntimeError):

        TradeLogger(log_path=str(legacy))


def test_logger_upgrades_empty_legacy_log(tmp_path):

    legacy = tmp_path / "empty.csv"

    legacy.write_text(
        "symbol,direction,entry_price,exit_price,quantity,pnl\n"
    )

    TradeLogger(log_path=str(legacy))

    assert (
        legacy.read_text().startswith(
            "symbol,direction,entry_timestamp"
        )
    )
