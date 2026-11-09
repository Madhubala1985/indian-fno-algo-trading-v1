from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from datetime import time
from datetime import timezone
from pathlib import Path

from platform_core.adaptive.regime_engine import (
    RegimeEngine,
)

from platform_core.analytics.atr_tracker import (
    ATRTracker,
)

from platform_core.analytics.structure.bos_detector import (
    BOSDetector,
    BOSDetectorConfig,
)

from platform_core.analytics.structure.choch_detector import (
    CHOCHDetector,
    CHOCHDetectorConfig,
)

from platform_core.analytics.structure.fvg_engine import (
    FVGEngine,
    FVGEngineConfig,
)

from platform_core.analytics.structure.liquidity_sweep_detector import (
    LiquiditySweepDetector,
    LiquiditySweepDetectorConfig,
)

from platform_core.analytics.structure.structure_engine import (
    StructureEngine,
    StructureEngineConfig,
    StructureEngineInput,
)

from platform_core.analytics.structure.support_resistance_engine import (
    SupportResistanceEngine,
    SupportResistanceEngineConfig,
)

from platform_core.analytics.structure.swing_detector import (
    SwingDetector,
    SwingDetectorConfig,
)

from platform_core.data.live.live_structure_adapter import (
    LiveStructureAdapter,
)

from platform_core.intelligence.htf_bias_engine import (
    HTFBiasEngine,
)

from platform_core.intelligence.rolling_bias import (
    RollingBiasTracker,
)

from platform_core.paper_trading.exit_engine import (
    ExitEngine,
    ExitEngineConfig,
)

from platform_core.paper_trading.paper_broker import (
    PaperBroker,
)

from platform_core.paper_trading.performance_tracker import (
    PerformanceTracker,
)

from platform_core.paper_trading.trade_logger import (
    TradeLogger,
)

from platform_core.risk.drawdown_protection import (
    DrawdownProtectionEngine,
    EquitySnapshot,
)

from platform_core.risk.kill_switches import (
    KillSwitchEngine,
    KillSwitchSnapshot,
)

from platform_core.risk.position_sizing import (
    PortfolioRiskSnapshot,
    PositionSizer,
    PositionSizingConfig,
    PositionSizingRequest,
)

from platform_core.signals.signal_engine import (
    SignalEngine,
)


DEFAULT_CONFIG_PATH = (
    "configs/paper_trading.json"
)


@dataclass(slots=True)
class SessionConfig:

    symbol: str = "BANKNIFTY"

    timeframe: str = "MIN_1"

    starting_equity: float = 1_000_000.0

    lot_size: int = 35

    contract_multiplier: float = 1.0

    max_lot_count: int = 10

    risk_fraction_per_trade: float = 0.005

    stop_atr_multiple: float = 1.5

    target_r_multiple: float = 2.0

    trailing_atr_multiple: float = 0.0

    max_bars_in_trade: int = 120

    squareoff_time: time = time(15, 20)

    atr_window: int = 14

    slow_atr_window: int = 100

    warmup_bars: int = 20

    liquidity_score: float = 0.90

    spread_bps: float = 2.0

    slippage_bps_estimate: float = 3.0

    max_allowed_drawdown_fraction: float = 0.12

    # Index futures/options are margined, not fully funded. The position sizer
    # models `available_cash` as cash that must cover full notional, which is
    # the cash-equity convention. Dividing equity by the margin fraction
    # converts equity into the notional it can actually carry, so the sizer's
    # cash haircut reflects real buying power instead of rejecting every lot.
    margin_fraction_of_notional: float = 0.12

    market_open: time = time(9, 15)

    market_close: time = time(15, 30)

    trade_log_path: str = "logs/paper_trades.csv"

    session_log_path: str = "logs/paper_sessions"

    @classmethod
    def load(
        cls,
        *,
        path: str = DEFAULT_CONFIG_PATH,
    ) -> "SessionConfig":

        raw = json.loads(
            Path(path).read_text()
        )

        for key in (
            "squareoff_time",
            "market_open",
            "market_close",
        ):

            if key in raw:

                hour, minute = (
                    raw[key].split(":")
                )

                raw[key] = time(
                    int(hour),
                    int(minute),
                )

        known = {
            field
            for field in cls.__slots__
        }

        return cls(
            **{
                key: value
                for key, value in raw.items()
                if key in known
            }
        )


class PaperSession:
    """Bar-driven paper trading session shared by the live and replay feeds.

    One completed bar in, zero or more position transitions out. The ordering
    inside `process_bar` is deliberate: exits are evaluated against an open
    position before any new entry is considered, so a stop and a fresh signal
    on the same bar cannot leave the book double-counted.
    """

    def __init__(
        self,
        *,
        config: SessionConfig | None = None,
        trade_logger: TradeLogger | None = None,
    ) -> None:

        self.config = config or SessionConfig()

        symbol = self.config.symbol

        timeframe = self.config.timeframe

        self.adapter = LiveStructureAdapter()

        self.swing_detector = SwingDetector(
            config=SwingDetectorConfig(
                instrument_id=symbol,
                timeframe=timeframe,
            )
        )

        self.engine = StructureEngine(

            config=StructureEngineConfig(
                instrument_id=symbol,
                timeframe=timeframe,
            ),

            liquidity_sweep_detector=(
                LiquiditySweepDetector(
                    config=(
                        LiquiditySweepDetectorConfig(
                            instrument_id=symbol,
                            timeframe=timeframe,
                        )
                    )
                )
            ),

            bos_detector=BOSDetector(
                config=BOSDetectorConfig(
                    instrument_id=symbol,
                    timeframe=timeframe,
                )
            ),

            choch_detector=CHOCHDetector(
                config=CHOCHDetectorConfig(
                    instrument_id=symbol,
                    timeframe=timeframe,
                )
            ),

            fvg_engine=FVGEngine(
                config=FVGEngineConfig(
                    instrument_id=symbol,
                    timeframe=timeframe,
                )
            ),

            support_resistance_engine=(
                SupportResistanceEngine(
                    config=(
                        SupportResistanceEngineConfig(
                            instrument_id=symbol,
                            timeframe=timeframe,
                        )
                    )
                )
            ),
        )

        self.regime_engine = RegimeEngine()

        self.htf_bias_engine = HTFBiasEngine()

        self.bias_tracker = (
            RollingBiasTracker()
        )

        self.signal_engine = SignalEngine()

        self.atr_tracker = ATRTracker(
            window=self.config.atr_window
        )

        self.slow_atr_tracker = ATRTracker(
            window=(
                self.config.slow_atr_window
            )
        )

        self.exit_engine = ExitEngine(
            config=ExitEngineConfig(
                stop_atr_multiple=(
                    self.config
                    .stop_atr_multiple
                ),
                target_r_multiple=(
                    self.config
                    .target_r_multiple
                ),
                trailing_atr_multiple=(
                    self.config
                    .trailing_atr_multiple
                ),
                max_bars_in_trade=(
                    self.config
                    .max_bars_in_trade
                ),
                squareoff_time=(
                    self.config.squareoff_time
                ),
            )
        )

        self.paper_broker = PaperBroker()

        self.performance_tracker = (
            PerformanceTracker()
        )

        self.trade_logger = (
            trade_logger
            or TradeLogger(
                log_path=(
                    self.config
                    .trade_log_path
                )
            )
        )

        self.position_sizer = PositionSizer(
            config=PositionSizingConfig(
                max_risk_fraction_per_trade=(
                    self.config
                    .risk_fraction_per_trade
                )
            )
        )

        self.drawdown_engine = (
            DrawdownProtectionEngine()
        )

        self.kill_switch_engine = (
            KillSwitchEngine()
        )

        self.bar_index = 0

        self.equity = (
            self.config.starting_equity
        )

        self.peak_equity = self.equity

        self.realized_pnl_day = 0.0

        self.consecutive_losses = 0

        self.rejections: list[str] = []

        self.blocked_entries = 0

        self._session_date = None

    # ────────────────────────────────
    # main entry point
    # ────────────────────────────────

    def process_bar(
        self,
        *,
        live_bar,
        data_staleness_seconds: float = 0.0,
    ) -> None:

        self.bar_index += 1

        self._roll_session_if_needed(
            live_bar=live_bar
        )

        atr = self.atr_tracker.update(
            bar=live_bar
        )

        slow_atr = (
            self.slow_atr_tracker.update(
                bar=live_bar
            )
        )

        self.bias_tracker.update(
            bar=live_bar
        )

        structure_bar = (
            self.adapter.convert_bar(
                live_bar=live_bar
            )
        )

        swing_result = (
            self.swing_detector.process_bar(
                structure_bar
            )
        )

        result = self.engine.process(
            payload=StructureEngineInput(
                bar=structure_bar,
                swing_points=(
                    swing_result
                    .confirmed_points
                ),
            )
        )

        regime = (
            self.regime_engine.classify(
                bar_range=(
                    live_bar.high_price
                    - live_bar.low_price
                ),
                average_range=(
                    atr
                    if atr and atr > 0.0
                    else (
                        live_bar.high_price
                        - live_bar.low_price
                    )
                    or 1.0
                ),
            )
        )

        biases = self.bias_tracker.biases()

        market_context = (
            self.htf_bias_engine
            .build_context(
                daily_bias=(
                    biases["daily_bias"]
                ),
                h4_bias=biases["h4_bias"],
                h1_bias=biases["h1_bias"],
                m15_bias=biases["m15_bias"],
                volatility_regime=(
                    regime.volatility_regime
                ),
            )
        )

        signals = (
            self.signal_engine
            .generate_signals(
                symbol=self.config.symbol,
                events=result.emitted_events,
                regime=regime,
                market_context=market_context,
            )
        )

        # 1. mechanical exits (stop / target / time / square-off)
        self._apply_mechanical_exits(
            live_bar=live_bar,
            atr=atr,
        )

        # 2. structure-driven exits
        self._apply_structure_exits(
            live_bar=live_bar,
            signals=signals,
        )

        # 3. entries, subject to the risk gate
        self._apply_entries(
            live_bar=live_bar,
            signals=signals,
            regime=regime,
            market_context=market_context,
            atr=atr,
            slow_atr=slow_atr,
            data_staleness_seconds=(
                data_staleness_seconds
            ),
        )

    def warm_up(self, *, bars) -> int:
        """Seed the detectors and trackers with prior bars, taking no trades.

        Higher-timeframe bias needs hundreds of one-minute bars before it stops
        reporting NEUTRAL. A session started cold at the open therefore cannot
        satisfy the 3-of-4 alignment gate for most of the day. Replaying recent
        history through the same pipeline — without touching the broker — puts
        the trackers in the state they would have been in had the session been
        running all along.
        """

        seeded = 0

        for live_bar in bars:

            self.bar_index += 1

            self.atr_tracker.update(
                bar=live_bar
            )

            self.slow_atr_tracker.update(
                bar=live_bar
            )

            self.bias_tracker.update(
                bar=live_bar
            )

            structure_bar = (
                self.adapter.convert_bar(
                    live_bar=live_bar
                )
            )

            swing_result = (
                self.swing_detector
                .process_bar(structure_bar)
            )

            self.engine.process(
                payload=StructureEngineInput(
                    bar=structure_bar,
                    swing_points=(
                        swing_result
                        .confirmed_points
                    ),
                )
            )

            self._session_date = (
                live_bar.end_timestamp.date()
            )

            seeded += 1

        print(
            f"\n[WARMUP] Seeded {seeded} bars. "
            f"Bias state: "
            f"{self.bias_tracker.biases()}"
        )

        return seeded

    def _roll_session_if_needed(
        self,
        *,
        live_bar,
    ) -> None:
        """Reset per-session risk state when the trading date changes.

        Daily loss and the kill switch's consecutive-loss streak are
        session-scoped. Left to accumulate across days they would latch a
        session halt from one day into every day that follows, which is how a
        multi-day replay ends up trading only its first active session.
        """

        current_date = (
            live_bar.end_timestamp.date()
        )

        if self._session_date is None:

            self._session_date = current_date

            return

        if current_date == self._session_date:

            return

        self._session_date = current_date

        self.realized_pnl_day = 0.0

        self.consecutive_losses = 0

        self.kill_switch_engine.reset()

        print(
            f"\n[SESSION] New trading day "
            f"{current_date} — daily loss, "
            f"loss streak, and kill switch "
            f"reset."
        )

    def force_flat(
        self,
        *,
        live_bar,
        reason: str = "SESSION_END",
    ) -> None:
        """Close any open position at the last known price."""

        if not (
            self.paper_broker
            .has_open_position(
                symbol=self.config.symbol
            )
        ):

            return

        self._close(
            exit_price=live_bar.close_price,
            exit_reason=reason,
            exit_timestamp=(
                live_bar.end_timestamp
            ),
        )

    def summary(self):

        return (
            self.performance_tracker
            .calculate_summary(
                trades=(
                    self.paper_broker
                    .completed_trades
                )
            )
        )

    # ────────────────────────────────
    # exits
    # ────────────────────────────────

    def _apply_mechanical_exits(
        self,
        *,
        live_bar,
        atr: float | None,
    ) -> None:

        position = (
            self.paper_broker.get_position(
                symbol=self.config.symbol
            )
        )

        if position is None:

            return

        decision = self.exit_engine.evaluate(
            position=position,
            bar=live_bar,
            bar_index=self.bar_index,
            atr=atr or 0.0,
        )

        if not decision.should_exit:

            return

        self._close(
            exit_price=decision.exit_price,
            exit_reason=decision.reason,
            exit_timestamp=(
                live_bar.end_timestamp
            ),
        )

    def _apply_structure_exits(
        self,
        *,
        live_bar,
        signals,
    ) -> None:

        position = (
            self.paper_broker.get_position(
                symbol=self.config.symbol
            )
        )

        if position is None:

            return

        for signal in signals:

            if signal.action != "CLOSE":

                continue

            # A CLOSE signal is tagged with the direction it invalidates.
            # Closing on the opposite tag would flatten a position that the
            # structure still supports.
            if (
                signal.direction
                != position.direction
            ):

                continue

            self._close(
                exit_price=(
                    live_bar.close_price
                ),
                exit_reason=(
                    "STRUCTURE_INVALIDATED"
                ),
                exit_timestamp=(
                    live_bar.end_timestamp
                ),
            )

            return

    def _close(
        self,
        *,
        exit_price: float,
        exit_reason: str,
        exit_timestamp: datetime,
    ) -> None:

        trade = (
            self.paper_broker
            .close_position(
                symbol=self.config.symbol,
                exit_price=exit_price,
                exit_reason=exit_reason,
                exit_timestamp=exit_timestamp,
                exit_bar_index=self.bar_index,
            )
        )

        if trade is None:

            return

        self.equity += trade.pnl

        self.peak_equity = max(
            self.peak_equity,
            self.equity,
        )

        self.realized_pnl_day += trade.pnl

        if trade.pnl <= 0.0:

            self.consecutive_losses += 1

        else:

            self.consecutive_losses = 0

        self.trade_logger.log_trade(
            trade=trade
        )

    # ────────────────────────────────
    # entries
    # ────────────────────────────────

    def _apply_entries(
        self,
        *,
        live_bar,
        signals,
        regime,
        market_context,
        atr: float | None,
        slow_atr: float | None,
        data_staleness_seconds: float,
    ) -> None:

        open_signals = [
            signal
            for signal in signals
            if signal.action == "OPEN"
        ]

        if not open_signals:

            return

        if (
            self.paper_broker
            .has_open_position(
                symbol=self.config.symbol
            )
        ):

            return

        if (
            self.bar_index
            < self.config.warmup_bars
        ):

            self._reject(
                "WARMUP: only "
                f"{self.bar_index} bars seen"
            )

            return

        if atr is None or atr <= 0.0:

            self._reject(
                "NO_VOLATILITY_BASELINE: "
                "ATR unavailable"
            )

            return

        if self.exit_engine.is_squareoff_due(
            timestamp=live_bar.end_timestamp
        ):

            self._reject(
                "PAST_SQUAREOFF: no new "
                "entries after "
                f"{self.config.squareoff_time}"
            )

            return

        signal = open_signals[0]

        timestamp = _as_utc(
            live_bar.end_timestamp
        )

        drawdown_result = (
            self._evaluate_drawdown(
                timestamp=timestamp
            )
        )

        kill_switch_decision = (
            self._evaluate_kill_switch(
                timestamp=timestamp,
                drawdown_result=drawdown_result,
                data_staleness_seconds=(
                    data_staleness_seconds
                ),
            )
        )

        if not drawdown_result.trading_allowed:

            self._reject(
                "DRAWDOWN_BLOCK: "
                f"{drawdown_result.status}"
            )

            return

        if not (
            kill_switch_decision
            .new_entries_allowed
        ):

            self._reject(
                "KILL_SWITCH: "
                f"{kill_switch_decision.level}"
                f" — {kill_switch_decision.reason}"
            )

            return

        stop_price, target_price = (
            self.exit_engine.initial_levels(
                direction=signal.direction,
                entry_price=(
                    live_bar.close_price
                ),
                atr=atr,
            )
        )

        sizing_result = self._size_position(
            signal=signal,
            live_bar=live_bar,
            stop_price=stop_price,
            market_context=market_context,
            atr=atr,
            slow_atr=slow_atr,
            timestamp=timestamp,
        )

        if not sizing_result.tradable:

            self._reject(
                "SIZING_REJECT: "
                f"{sizing_result.rejection_reason}"
            )

            return

        if sizing_result.recommended_units <= 0:

            self._reject(
                "SIZING_ZERO: risk budget "
                "supports no units"
            )

            return

        self.paper_broker.open_position(
            symbol=self.config.symbol,
            direction=signal.direction,
            entry_price=live_bar.close_price,
            quantity=(
                sizing_result
                .recommended_units
            ),
            stop_price=stop_price,
            target_price=target_price,
            entry_bar_index=self.bar_index,
            entry_reason=signal.reason,
            entry_timestamp=(
                live_bar.end_timestamp
            ),
        )

    def _size_position(
        self,
        *,
        signal,
        live_bar,
        stop_price: float,
        market_context,
        atr: float,
        slow_atr: float | None,
        timestamp: datetime,
    ):

        volatility_ratio = (
            atr / slow_atr
            if slow_atr and slow_atr > 0.0
            else 1.0
        )

        drawdown_fraction = (
            max(
                0.0,
                (
                    self.peak_equity
                    - self.equity
                )
                / self.peak_equity,
            )
            if self.peak_equity > 0.0
            else 0.0
        )

        buying_power = (
            self.equity
            / self.config
            .margin_fraction_of_notional
        )

        portfolio = PortfolioRiskSnapshot(
            equity=self.equity,
            available_cash=buying_power,
            current_portfolio_heat=0.0,
            current_drawdown_fraction=min(
                drawdown_fraction,
                1.0,
            ),
            max_allowed_drawdown_fraction=(
                self.config
                .max_allowed_drawdown_fraction
            ),
            correlation_exposure_fraction=0.0,
            open_position_count=len(
                self.paper_broker.positions
            ),
        )

        request = PositionSizingRequest(
            underlying_symbol=(
                self.config.symbol
            ),
            timestamp=timestamp,
            direction=signal.direction,
            instrument_type="INDEX",
            entry_price=live_bar.close_price,
            stop_price=stop_price,
            contract_multiplier=(
                self.config
                .contract_multiplier
            ),
            lot_size=self.config.lot_size,
            minimum_lot_count=1,
            maximum_lot_count=(
                self.config.max_lot_count
            ),
            confidence_score=min(
                max(signal.confidence, 0.0),
                1.0,
            ),
            actionability_score=min(
                max(
                    market_context
                    .confidence_score,
                    0.0,
                ),
                1.0,
            ),
            realized_volatility_ratio=max(
                volatility_ratio,
                0.01,
            ),
            liquidity_score=(
                self.config.liquidity_score
            ),
            spread_bps=self.config.spread_bps,
            slippage_bps_estimate=(
                self.config
                .slippage_bps_estimate
            ),
            expected_correlation_to_book=0.0,
            portfolio=portfolio,
        )

        return (
            self.position_sizer
            .size_position(request=request)
        )

    # ────────────────────────────────
    # risk gates
    # ────────────────────────────────

    def _evaluate_drawdown(
        self,
        *,
        timestamp: datetime,
    ):

        snapshot = EquitySnapshot(
            timestamp=timestamp,
            equity=self.equity,
            realized_pnl_day=(
                self.realized_pnl_day
            ),
            realized_pnl_rolling_window=(
                self.equity
                - self.config.starting_equity
            ),
            consecutive_losses=(
                self.consecutive_losses
            ),
            open_risk_fraction=0.0,
        )

        return (
            self.drawdown_engine.evaluate(
                snapshot=snapshot
            )
        )

    def _evaluate_kill_switch(
        self,
        *,
        timestamp: datetime,
        drawdown_result,
        data_staleness_seconds: float,
    ):

        snapshot = KillSwitchSnapshot(
            timestamp=timestamp,
            drawdown_status=(
                drawdown_result.status
            ),
            portfolio_heat_status="NORMAL",
            exposure_status="NORMAL",
            trading_allowed_by_drawdown=(
                drawdown_result
                .trading_allowed
            ),
            adjusted_slippage_bps=(
                self.config
                .slippage_bps_estimate
            ),
            reject_rate_fraction=0.0,
            consecutive_losses=(
                self.consecutive_losses
            ),
            duplicate_order_signals=0,
            data_staleness_seconds=max(
                data_staleness_seconds,
                0.0,
            ),
            infrastructure_healthy=True,
            manual_kill_requested=False,
            manual_resume_requested=False,
        )

        return (
            self.kill_switch_engine.evaluate(
                snapshot=snapshot
            )
        )

    def _reject(self, message: str) -> None:

        self.blocked_entries += 1

        self.rejections.append(message)

        print(f"\n[RISK] Entry blocked — {message}")


def _as_utc(value: datetime) -> datetime:

    if value.tzinfo is None:

        return value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(timezone.utc)
