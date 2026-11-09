"""Live (or replayed) paper trading session.

    python scripts/run_live_paper.py --mode replay --csv data/banknifty_real.csv
    python scripts/run_live_paper.py --mode live

Replay mode drives the identical strategy path from a CSV, so the pipeline can
be validated without a broker session. Live mode needs a Kite access token
generated the same trading day (`scripts/generate_kite_session.py`).

Neither mode places a real order. Fills are simulated by PaperBroker.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent),
)

from platform_core.backtesting.historical_replay import (  # noqa: E402
    HistoricalReplayFeed,
)

from platform_core.paper_trading.live_paper_runner import (  # noqa: E402
    LivePaperRunner,
    print_session_report,
)

from platform_core.paper_trading.paper_session import (  # noqa: E402
    PaperSession,
    SessionConfig,
)


def run_replay(
    *,
    config: SessionConfig,
    csv_path: str,
) -> int:

    feed = HistoricalReplayFeed()

    bars = feed.load_csv(
        path=csv_path,
        symbol=config.symbol,
    )

    session = PaperSession(config=config)

    print(
        f"\n[REPLAY] {len(bars)} bars from "
        f"{csv_path}\n"
    )

    for bar in bars:

        session.process_bar(live_bar=bar)

    if bars:

        session.force_flat(
            live_bar=bars[-1],
            reason="SESSION_END",
        )

    print_session_report(
        session=session,
        bars_processed=len(bars),
    )

    return 0


def _seed(
    *,
    session: PaperSession,
    config: SessionConfig,
    seed_csv: str | None,
) -> None:

    if not seed_csv:

        print(
            "\n[WARMUP] No --seed-csv given. "
            "Higher-timeframe bias starts "
            "NEUTRAL, so entries stay gated "
            "until enough bars accumulate."
        )

        return

    bars = HistoricalReplayFeed().load_csv(
        path=seed_csv,
        symbol=config.symbol,
    )

    session.warm_up(bars=bars)


def run_live(
    *,
    config: SessionConfig,
    seed_csv: str | None = None,
) -> int:

    from platform_core.data.live.instrument_registry import (
        INSTRUMENTS,
    )

    from platform_core.data.live.kite_adapter import (
        KiteAdapter,
    )

    token = INSTRUMENTS.get(config.symbol)

    if token is None:

        print(
            f"\n[LIVE] Unknown symbol "
            f"{config.symbol!r}. Known: "
            f"{sorted(INSTRUMENTS)}"
        )

        return 2

    try:

        adapter = KiteAdapter()

    except Exception as exc:

        print(
            f"\n[LIVE] Could not initialise "
            f"the Kite adapter: {exc}\n"
            "Refresh the access token with "
            "scripts/generate_kite_session.py "
            "and retry."
        )

        return 2

    session = PaperSession(config=config)

    _seed(
        session=session,
        config=config,
        seed_csv=seed_csv,
    )

    runner = LivePaperRunner(
        config=config,
        session=session,
    )

    try:

        runner.run(
            adapter=adapter,
            instrument_token=token,
        )

    except TimeoutError as exc:

        print(
            f"\n[LIVE] Feed did not connect: "
            f"{exc}\n"
            "The access token is most likely "
            "expired — Kite tokens are valid "
            "for a single trading day."
        )

        return 2

    return 0


def main() -> int:

    parser = argparse.ArgumentParser(
        description=(
            "Run a paper trading session "
            "(no real orders)."
        )
    )

    parser.add_argument(
        "--mode",
        choices=["live", "replay"],
        default="replay",
    )

    parser.add_argument(
        "--csv",
        default="data/banknifty_real.csv",
        help="bar source for replay mode",
    )

    parser.add_argument(
        "--config",
        default="configs/paper_trading.json",
    )

    parser.add_argument(
        "--symbol",
        default=None,
        help="override the configured symbol",
    )

    parser.add_argument(
        "--seed-csv",
        default=None,
        help=(
            "live mode: recent bars used to "
            "warm the bias and volatility "
            "trackers before the session"
        ),
    )

    args = parser.parse_args()

    config = SessionConfig.load(
        path=args.config
    )

    if args.symbol:

        config.symbol = args.symbol

    if args.mode == "replay":

        return run_replay(
            config=config,
            csv_path=args.csv,
        )

    return run_live(
        config=config,
        seed_csv=args.seed_csv,
    )


if __name__ == "__main__":

    raise SystemExit(main())
