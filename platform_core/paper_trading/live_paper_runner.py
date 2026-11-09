from __future__ import annotations

import queue
import time as time_module
from dataclasses import dataclass
from datetime import datetime

from platform_core.data.bar_builder import (
    BarBuilder,
)

from platform_core.paper_trading.paper_session import (
    PaperSession,
    SessionConfig,
)


@dataclass(slots=True)
class NormalizedTick:
    """Minimal tick shape that BarBuilder consumes."""

    symbol: str

    exchange_timestamp: datetime

    last_price: float

    volume: float


class LivePaperRunner:
    """Drives a PaperSession from a live Kite tick stream.

    Kite delivers ticks on its own websocket thread. Rather than run strategy
    code there, ticks are handed to a queue and drained on the calling thread,
    which keeps bar construction, signal generation, and position state
    single-threaded and therefore deterministic.
    """

    def __init__(
        self,
        *,
        config: SessionConfig | None = None,
        session: PaperSession | None = None,
    ) -> None:

        self.config = config or SessionConfig()

        self.session = session or PaperSession(
            config=self.config
        )

        self.bar_builder = BarBuilder(
            timeframe_seconds=60
        )

        self._tick_queue: queue.Queue = (
            queue.Queue()
        )

        self._last_tick_wall_clock: float = (
            time_module.monotonic()
        )

        self._last_tick_price: float | None = (
            None
        )

        self.ticks_received = 0

        self.bars_processed = 0

    # ────────────────────────────────
    # tick intake
    # ────────────────────────────────

    def on_ticks(self, ticks) -> None:
        """Kite websocket callback. Runs on the websocket thread."""

        for tick in ticks:

            normalized = (
                self._normalize(tick=tick)
            )

            if normalized is not None:

                self._tick_queue.put(
                    normalized
                )

    def _normalize(
        self,
        *,
        tick,
    ) -> NormalizedTick | None:

        last_price = tick.get("last_price")

        if last_price is None:

            return None

        timestamp = (
            tick.get("exchange_timestamp")
            or tick.get("last_trade_time")
            or datetime.now()
        )

        return NormalizedTick(
            symbol=self.config.symbol,
            exchange_timestamp=timestamp,
            last_price=float(last_price),
            volume=float(
                tick.get("volume_traded")
                or 0.0
            ),
        )

    # ────────────────────────────────
    # main loop
    # ────────────────────────────────

    def run(
        self,
        *,
        adapter,
        instrument_token: int,
        poll_seconds: float = 1.0,
    ) -> None:

        adapter.add_tick_callback(
            self.on_ticks
        )

        adapter.connect(
            instrument_tokens=[
                instrument_token
            ]
        )

        print(
            f"\n[LIVE] Paper session running "
            f"for {self.config.symbol}. "
            f"Square-off at "
            f"{self.config.squareoff_time}, "
            f"close at "
            f"{self.config.market_close}.\n"
        )

        try:

            while True:

                self._drain_queue(
                    timeout=poll_seconds
                )

                if self._session_over():

                    break

        except KeyboardInterrupt:

            print(
                "\n[LIVE] Interrupted — "
                "flattening and reporting."
            )

        finally:

            self._finalize()

            try:

                adapter.disconnect()

            except Exception as exc:

                print(
                    f"\n[LIVE] Disconnect "
                    f"error ignored: {exc}"
                )

    def _drain_queue(
        self,
        *,
        timeout: float,
    ) -> None:

        deadline = (
            time_module.monotonic() + timeout
        )

        while True:

            remaining = (
                deadline
                - time_module.monotonic()
            )

            if remaining <= 0.0:

                return

            try:

                tick = self._tick_queue.get(
                    timeout=remaining
                )

            except queue.Empty:

                return

            self._handle_tick(tick=tick)

    def _handle_tick(
        self,
        *,
        tick: NormalizedTick,
    ) -> None:

        self.ticks_received += 1

        self._last_tick_wall_clock = (
            time_module.monotonic()
        )

        self._last_tick_price = (
            tick.last_price
        )

        if not self._within_market_hours(
            timestamp=tick.exchange_timestamp
        ):

            return

        completed_bar = (
            self.bar_builder.update_tick(
                tick=tick
            )
        )

        if completed_bar is None:

            return

        self._process(bar=completed_bar)

    def _process(self, *, bar) -> None:

        self.bars_processed += 1

        staleness = (
            time_module.monotonic()
            - self._last_tick_wall_clock
        )

        self.session.process_bar(
            live_bar=bar,
            data_staleness_seconds=staleness,
        )

    def _within_market_hours(
        self,
        *,
        timestamp: datetime,
    ) -> bool:

        current = timestamp.time()

        return (
            self.config.market_open
            <= current
            <= self.config.market_close
        )

    def _session_over(self) -> bool:

        return (
            datetime.now().time()
            >= self.config.market_close
        )

    def _finalize(self) -> None:
        """Close the trailing bar, flatten, and report."""

        trailing_bar = (
            self.bar_builder.force_close(
                symbol=self.config.symbol
            )
        )

        if trailing_bar is not None:

            self._process(bar=trailing_bar)

            self.session.force_flat(
                live_bar=trailing_bar,
                reason="SESSION_END",
            )

        print_session_report(
            session=self.session,
            ticks_received=self.ticks_received,
            bars_processed=self.bars_processed,
        )


def print_session_report(
    *,
    session: PaperSession,
    ticks_received: int | None = None,
    bars_processed: int | None = None,
) -> None:

    summary = session.summary()

    print(
        "\n"
        "═══════════════════════════════\n"
        "PAPER SESSION REPORT\n"
        "═══════════════════════════════\n"
    )

    if ticks_received is not None:

        print(f"Ticks received   : {ticks_received}")

    if bars_processed is not None:

        print(f"Bars processed   : {bars_processed}")

    print(f"Trades closed    : {summary.total_trades}")
    print(f"Wins / losses    : {summary.winning_trades} / {summary.losing_trades}")
    print(f"Win rate         : {summary.win_rate:.1%}")
    print(f"Total PnL (pts×qty): {summary.total_pnl:,.2f}")
    print(f"Average PnL      : {summary.average_pnl:,.2f}")
    print(f"Closing equity   : {session.equity:,.2f}")
    print(f"Entries blocked  : {session.blocked_entries}")

    if session.paper_broker.completed_trades:

        print("\nExit reason breakdown:")

        reasons: dict[str, int] = {}

        for trade in (
            session.paper_broker
            .completed_trades
        ):

            reasons[trade.exit_reason] = (
                reasons.get(
                    trade.exit_reason,
                    0,
                )
                + 1
            )

        for reason, count in sorted(
            reasons.items()
        ):

            print(f"  {reason:<24} {count}")

    if session.rejections:

        print("\nMost recent entry blocks:")

        for message in (
            session.rejections[-5:]
        ):

            print(f"  {message}")

    print()
