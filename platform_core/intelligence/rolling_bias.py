from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass(slots=True)
class RollingBiasConfig:

    m15_lookback_bars: int = 15

    h1_lookback_bars: int = 60

    h4_lookback_bars: int = 240

    daily_lookback_bars: int = 375

    neutral_band_fraction: float = 0.0005


class RollingBiasTracker:
    """Derives per-timeframe directional bias from a stream of 1-minute bars.

    The backtest runner hardcoded its higher-timeframe bias to a permanently
    bullish set, which pinned `MarketContext.is_aligned` to True and made short
    signals unreachable. This tracker replaces that constant with a bias
    measured from the bars actually seen: each timeframe compares the latest
    close against the close `lookback` minutes earlier, with a neutral band so
    that flat tape does not read as directional.
    """

    def __init__(
        self,
        *,
        config: RollingBiasConfig | None = None,
    ) -> None:

        self.config = (
            config or RollingBiasConfig()
        )

        max_lookback = max(
            self.config.m15_lookback_bars,
            self.config.h1_lookback_bars,
            self.config.h4_lookback_bars,
            self.config.daily_lookback_bars,
        )

        self._closes: deque[float] = deque(
            maxlen=max_lookback + 1
        )

    @property
    def bar_count(self) -> int:

        return len(self._closes)

    def update(self, *, bar) -> None:

        self._closes.append(bar.close_price)

    def has_history_for(
        self,
        *,
        lookback_bars: int,
    ) -> bool:

        return len(self._closes) > lookback_bars

    def biases(self) -> dict[str, str]:
        """Return the current bias per timeframe.

        Timeframes without enough history yet report NEUTRAL, which keeps the
        alignment gate closed until the tracker is warm rather than letting an
        unseeded timeframe vote.
        """

        return {
            "m15_bias": self._bias_for(
                lookback_bars=(
                    self.config
                    .m15_lookback_bars
                )
            ),
            "h1_bias": self._bias_for(
                lookback_bars=(
                    self.config
                    .h1_lookback_bars
                )
            ),
            "h4_bias": self._bias_for(
                lookback_bars=(
                    self.config
                    .h4_lookback_bars
                )
            ),
            "daily_bias": self._bias_for(
                lookback_bars=(
                    self.config
                    .daily_lookback_bars
                )
            ),
        }

    def _bias_for(
        self,
        *,
        lookback_bars: int,
    ) -> str:

        if not self.has_history_for(
            lookback_bars=lookback_bars
        ):

            return "NEUTRAL"

        latest_close = self._closes[-1]

        reference_close = self._closes[
            -(lookback_bars + 1)
        ]

        if reference_close <= 0.0:

            return "NEUTRAL"

        change_fraction = (
            latest_close - reference_close
        ) / reference_close

        if (
            change_fraction
            > self.config.neutral_band_fraction
        ):

            return "BULLISH"

        if (
            change_fraction
            < -self.config.neutral_band_fraction
        ):

            return "BEARISH"

        return "NEUTRAL"
