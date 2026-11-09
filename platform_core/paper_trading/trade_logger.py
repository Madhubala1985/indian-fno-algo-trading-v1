from __future__ import annotations

import csv
from pathlib import Path

from platform_core.paper_trading.paper_broker import (
    PaperTrade,
)


LOG_PATH = (
    "logs/paper_trades.csv"
)


COLUMNS = [
    "symbol",
    "direction",
    "entry_timestamp",
    "exit_timestamp",
    "entry_price",
    "exit_price",
    "quantity",
    "pnl",
    "entry_reason",
    "exit_reason",
    "stop_price",
    "target_price",
    "bars_held",
]


class TradeLogger:

    def __init__(
        self,
        *,
        log_path: str = LOG_PATH,
    ) -> None:

        self.log_path = Path(log_path)

        self.log_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if not self.log_path.exists():

            self._write_header()

            return

        self._reconcile_existing_header()

    def log_trade(
        self,
        *,
        trade: PaperTrade,
    ) -> None:

        with open(
            self.log_path,
            "a",
            newline="",
        ) as f:

            writer = csv.writer(f)

            writer.writerow(
                [
                    trade.symbol,
                    trade.direction,
                    _iso(trade.entry_timestamp),
                    _iso(trade.exit_timestamp),
                    trade.entry_price,
                    trade.exit_price,
                    trade.quantity,
                    f"{trade.pnl:.2f}",
                    trade.entry_reason,
                    trade.exit_reason,
                    trade.stop_price,
                    trade.target_price,
                    trade.bars_held,
                ]
            )

        print(
            "\n[LOGGER] Trade persisted."
        )

    def _write_header(self) -> None:

        with open(
            self.log_path,
            "w",
            newline="",
        ) as f:

            csv.writer(f).writerow(COLUMNS)

    def _reconcile_existing_header(
        self,
    ) -> None:
        """Upgrade a legacy log in place, but never destroy recorded trades."""

        with open(self.log_path, newline="") as f:

            rows = list(csv.reader(f))

        if rows and rows[0] == COLUMNS:

            return

        data_rows = [
            row
            for row in rows[1:]
            if any(
                field.strip()
                for field in row
            )
        ]

        if data_rows:

            raise RuntimeError(
                f"{self.log_path} uses an outdated schema and holds "
                f"{len(data_rows)} trade(s). Archive or migrate it before "
                "running, so no recorded trades are lost."
            )

        self._write_header()

        print(
            f"\n[LOGGER] Upgraded empty log "
            f"{self.log_path} to the "
            f"current schema."
        )


def _iso(value) -> str:

    return (
        value.isoformat()
        if value is not None
        else ""
    )
