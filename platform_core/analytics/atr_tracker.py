from __future__ import annotations

from collections import deque


class ATRTracker:
    """Causal average-true-range and average-range tracker.

    The regime engine and position sizer both need a volatility baseline that
    is independent of the bar being classified. Feeding a bar's own range in as
    its own average collapses every comparison to a constant, so this tracker
    keeps a trailing window and reports the average of the bars that came
    *before* the current one.
    """

    def __init__(
        self,
        *,
        window: int = 14,
    ) -> None:

        if window <= 0:

            raise ValueError(
                "window must be positive"
            )

        self.window = window

        self._true_ranges: deque[float] = (
            deque(maxlen=window)
        )

        self._previous_close: float | None = (
            None
        )

    @property
    def ready(self) -> bool:

        return len(self._true_ranges) > 0

    @property
    def sample_count(self) -> int:

        return len(self._true_ranges)

    def current_atr(self) -> float | None:
        """Average true range over bars seen so far, or None if unseeded."""

        if not self._true_ranges:

            return None

        return (
            sum(self._true_ranges)
            / len(self._true_ranges)
        )

    def update(self, *, bar) -> float | None:
        """Fold one completed bar in; returns the ATR *before* this bar.

        Returning the prior ATR keeps the value causal — the caller can
        classify the current bar against history that excludes it.
        """

        prior_atr = self.current_atr()

        high_low = (
            bar.high_price - bar.low_price
        )

        if self._previous_close is None:

            true_range = high_low

        else:

            true_range = max(
                high_low,
                abs(
                    bar.high_price
                    - self._previous_close
                ),
                abs(
                    bar.low_price
                    - self._previous_close
                ),
            )

        self._true_ranges.append(true_range)

        self._previous_close = bar.close_price

        return prior_atr
