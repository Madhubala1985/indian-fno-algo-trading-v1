"""Exit-path regression tests.

Before these paths existed, a position could only be closed by an opposite
structure event, so protective exits were untested by construction.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent),
)

from platform_core.paper_trading.exit_engine import (  # noqa: E402
    ExitEngine,
    ExitEngineConfig,
)

from platform_core.paper_trading.paper_broker import (  # noqa: E402
    PaperBroker,
    PaperPosition,
)


@dataclass
class Bar:

    open_price: float
    high_price: float
    low_price: float
    close_price: float
    end_timestamp: datetime


def make_position(
    *,
    direction: str = "LONG",
    entry: float = 100.0,
    stop: float = 90.0,
    target: float = 120.0,
    bar_index: int = 0,
) -> PaperPosition:

    return PaperPosition(
        symbol="BANKNIFTY",
        direction=direction,
        entry_price=entry,
        quantity=35,
        entry_timestamp=datetime(2026, 8, 10, 10, 0),
        stop_price=stop,
        target_price=target,
        entry_bar_index=bar_index,
        extreme_price=entry,
    )


def bar_at(
    hour: int = 11,
    minute: int = 0,
    *,
    high: float,
    low: float,
    close: float,
) -> Bar:

    return Bar(
        open_price=close,
        high_price=high,
        low_price=low,
        close_price=close,
        end_timestamp=datetime(2026, 8, 10, hour, minute),
    )


def test_long_stop_fires_at_stop_price():

    engine = ExitEngine()

    decision = engine.evaluate(
        position=make_position(),
        bar=bar_at(high=101, low=89, close=95),
        bar_index=5,
        atr=5.0,
    )

    assert decision.should_exit
    assert decision.reason == "STOP_LOSS"
    assert decision.exit_price == 90.0


def test_long_target_fires_at_target_price():

    engine = ExitEngine()

    decision = engine.evaluate(
        position=make_position(),
        bar=bar_at(high=125, low=99, close=124),
        bar_index=5,
        atr=5.0,
    )

    assert decision.should_exit
    assert decision.reason == "TARGET"
    assert decision.exit_price == 120.0


def test_stop_wins_when_one_bar_spans_both_levels():
    """Intrabar path is unknown, so the adverse fill must be assumed."""

    engine = ExitEngine()

    decision = engine.evaluate(
        position=make_position(),
        bar=bar_at(high=125, low=85, close=110),
        bar_index=5,
        atr=5.0,
    )

    assert decision.reason == "STOP_LOSS"


def test_short_stop_is_above_entry():

    engine = ExitEngine()

    decision = engine.evaluate(
        position=make_position(
            direction="SHORT",
            entry=100.0,
            stop=110.0,
            target=80.0,
        ),
        bar=bar_at(high=111, low=99, close=105),
        bar_index=5,
        atr=5.0,
    )

    assert decision.reason == "STOP_LOSS"
    assert decision.exit_price == 110.0


def test_time_stop_fires_after_max_bars():

    engine = ExitEngine(
        config=ExitEngineConfig(max_bars_in_trade=10)
    )

    decision = engine.evaluate(
        position=make_position(bar_index=0),
        bar=bar_at(high=101, low=99, close=100),
        bar_index=10,
        atr=5.0,
    )

    assert decision.reason == "TIME_STOP"
    assert decision.exit_price == 100.0


def test_eod_squareoff_fires_at_configured_time():

    engine = ExitEngine()

    decision = engine.evaluate(
        position=make_position(),
        bar=bar_at(15, 20, high=101, low=99, close=100),
        bar_index=5,
        atr=5.0,
    )

    assert decision.reason == "EOD_SQUAREOFF"


def test_no_exit_when_bar_stays_inside_the_bracket():

    engine = ExitEngine()

    decision = engine.evaluate(
        position=make_position(),
        bar=bar_at(high=105, low=95, close=100),
        bar_index=5,
        atr=5.0,
    )

    assert not decision.should_exit
    assert decision.reason is None


def test_initial_levels_respect_r_multiple():

    engine = ExitEngine(
        config=ExitEngineConfig(
            stop_atr_multiple=2.0,
            target_r_multiple=3.0,
        )
    )

    stop, target = engine.initial_levels(
        direction="LONG",
        entry_price=100.0,
        atr=5.0,
    )

    assert stop == pytest.approx(90.0)
    assert target == pytest.approx(130.0)


def test_initial_levels_invert_for_short():

    engine = ExitEngine(
        config=ExitEngineConfig(
            stop_atr_multiple=2.0,
            target_r_multiple=3.0,
        )
    )

    stop, target = engine.initial_levels(
        direction="SHORT",
        entry_price=100.0,
        atr=5.0,
    )

    assert stop == pytest.approx(110.0)
    assert target == pytest.approx(70.0)


def test_zero_atr_is_rejected_rather_than_producing_a_zero_width_stop():

    engine = ExitEngine()

    with pytest.raises(ValueError):

        engine.initial_levels(
            direction="LONG",
            entry_price=100.0,
            atr=0.0,
        )


def test_trailing_stop_ratchets_up_but_never_down():

    engine = ExitEngine(
        config=ExitEngineConfig(trailing_atr_multiple=1.0)
    )

    position = make_position(stop=90.0)

    engine.evaluate(
        position=position,
        bar=bar_at(high=110, low=99, close=108),
        bar_index=5,
        atr=5.0,
    )

    assert position.stop_price == pytest.approx(105.0)

    engine.evaluate(
        position=position,
        bar=bar_at(high=106, low=105.5, close=106),
        bar_index=6,
        atr=5.0,
    )

    assert position.stop_price == pytest.approx(105.0)


def test_broker_pnl_sign_is_direction_aware():

    broker = PaperBroker()

    broker.open_position(
        symbol="BANKNIFTY",
        direction="SHORT",
        entry_price=100.0,
        quantity=10,
    )

    trade = broker.close_position(
        symbol="BANKNIFTY",
        exit_price=90.0,
        exit_reason="TARGET",
    )

    assert trade is not None
    assert trade.pnl == pytest.approx(100.0)
    assert not broker.has_open_position(symbol="BANKNIFTY")
