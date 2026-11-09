from __future__ import annotations

from dataclasses import dataclass
from datetime import time

from platform_core.paper_trading.paper_broker import (
    PaperPosition,
)


@dataclass(slots=True)
class ExitEngineConfig:

    stop_atr_multiple: float = 1.5

    target_r_multiple: float = 2.0

    trailing_atr_multiple: float = 0.0

    max_bars_in_trade: int = 120

    squareoff_time: time = time(15, 20)


@dataclass(slots=True)
class ExitDecision:

    should_exit: bool

    exit_price: float | None

    reason: str | None


class ExitEngine:
    """Deterministic bar-close exit evaluation.

    Resolves the four exit paths a paper position can take: protective stop,
    profit target, time stop, and end-of-session square-off. Structure-driven
    exits stay with the signal engine; this engine covers everything that must
    fire whether or not a new structure event arrives.
    """

    def __init__(
        self,
        *,
        config: ExitEngineConfig | None = None,
    ) -> None:

        self.config = (
            config or ExitEngineConfig()
        )

    def initial_levels(
        self,
        *,
        direction: str,
        entry_price: float,
        atr: float,
    ) -> tuple[float, float]:
        """Return the (stop_price, target_price) pair for a new position."""

        stop_distance = (
            atr
            * self.config.stop_atr_multiple
        )

        if stop_distance <= 0.0:

            raise ValueError(
                "stop distance must be "
                "positive; atr was "
                f"{atr}"
            )

        target_distance = (
            stop_distance
            * self.config.target_r_multiple
        )

        if direction == "LONG":

            return (
                entry_price - stop_distance,
                entry_price + target_distance,
            )

        return (
            entry_price + stop_distance,
            entry_price - target_distance,
        )

    def evaluate(
        self,
        *,
        position: PaperPosition,
        bar,
        bar_index: int,
        atr: float,
    ) -> ExitDecision:
        """Evaluate one completed bar against an open position."""

        self._update_trailing_stop(
            position=position,
            bar=bar,
            atr=atr,
        )

        # Stop is checked before target: when a single bar spans both levels
        # we cannot know the intrabar path, so we assume the adverse fill.
        if position.stop_price is not None:

            if (
                position.direction == "LONG"
                and bar.low_price
                <= position.stop_price
            ):

                return ExitDecision(
                    should_exit=True,
                    exit_price=(
                        position.stop_price
                    ),
                    reason="STOP_LOSS",
                )

            if (
                position.direction == "SHORT"
                and bar.high_price
                >= position.stop_price
            ):

                return ExitDecision(
                    should_exit=True,
                    exit_price=(
                        position.stop_price
                    ),
                    reason="STOP_LOSS",
                )

        if position.target_price is not None:

            if (
                position.direction == "LONG"
                and bar.high_price
                >= position.target_price
            ):

                return ExitDecision(
                    should_exit=True,
                    exit_price=(
                        position.target_price
                    ),
                    reason="TARGET",
                )

            if (
                position.direction == "SHORT"
                and bar.low_price
                <= position.target_price
            ):

                return ExitDecision(
                    should_exit=True,
                    exit_price=(
                        position.target_price
                    ),
                    reason="TARGET",
                )

        bars_held = (
            bar_index
            - position.entry_bar_index
        )

        if (
            self.config.max_bars_in_trade > 0
            and bars_held
            >= self.config.max_bars_in_trade
        ):

            return ExitDecision(
                should_exit=True,
                exit_price=bar.close_price,
                reason="TIME_STOP",
            )

        if self.is_squareoff_due(
            timestamp=bar.end_timestamp
        ):

            return ExitDecision(
                should_exit=True,
                exit_price=bar.close_price,
                reason="EOD_SQUAREOFF",
            )

        return ExitDecision(
            should_exit=False,
            exit_price=None,
            reason=None,
        )

    def is_squareoff_due(
        self,
        *,
        timestamp,
    ) -> bool:

        return (
            timestamp.time()
            >= self.config.squareoff_time
        )

    def _update_trailing_stop(
        self,
        *,
        position: PaperPosition,
        bar,
        atr: float,
    ) -> None:

        if (
            self.config.trailing_atr_multiple
            <= 0.0
        ):

            return

        trail_distance = (
            atr
            * self.config
            .trailing_atr_multiple
        )

        if position.direction == "LONG":

            position.extreme_price = max(
                position.extreme_price,
                bar.high_price,
            )

            candidate_stop = (
                position.extreme_price
                - trail_distance
            )

            if (
                position.stop_price is None
                or candidate_stop
                > position.stop_price
            ):

                position.stop_price = (
                    candidate_stop
                )

            return

        position.extreme_price = min(
            position.extreme_price,
            bar.low_price,
        )

        candidate_stop = (
            position.extreme_price
            + trail_distance
        )

        if (
            position.stop_price is None
            or candidate_stop
            < position.stop_price
        ):

            position.stop_price = (
                candidate_stop
            )
