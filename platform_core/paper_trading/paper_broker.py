from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class PaperPosition:

    symbol: str

    direction: str

    entry_price: float

    quantity: int

    entry_timestamp: datetime

    stop_price: float | None = None

    target_price: float | None = None

    entry_bar_index: int = 0

    entry_reason: str = ""

    extreme_price: float = 0.0


@dataclass(slots=True)
class PaperTrade:

    symbol: str

    direction: str

    entry_price: float

    exit_price: float

    quantity: int

    pnl: float

    entry_timestamp: datetime | None = None

    exit_timestamp: datetime | None = None

    entry_reason: str = ""

    exit_reason: str = ""

    stop_price: float | None = None

    target_price: float | None = None

    bars_held: int = 0


class PaperBroker:

    def __init__(self) -> None:

        self.positions = {}

        self.completed_trades = []

    def open_position(
        self,
        *,
        symbol: str,
        direction: str,
        entry_price: float,
        quantity: int,
        stop_price: float | None = None,
        target_price: float | None = None,
        entry_bar_index: int = 0,
        entry_reason: str = "",
        entry_timestamp: datetime | None = None,
    ) -> None:

        if symbol in self.positions:
            return

        self.positions[symbol] = (
            PaperPosition(
                symbol=symbol,
                direction=direction,
                entry_price=entry_price,
                quantity=quantity,
                entry_timestamp=(
                    entry_timestamp
                    or datetime.now()
                ),
                stop_price=stop_price,
                target_price=target_price,
                entry_bar_index=(
                    entry_bar_index
                ),
                entry_reason=entry_reason,
                extreme_price=entry_price,
            )
        )

        print(
            f"\n[PAPER] OPENED "
            f"{direction} "
            f"{symbol} "
            f"@ {entry_price} "
            f"qty={quantity} "
            f"stop={stop_price} "
            f"target={target_price}"
        )

    def close_position(
        self,
        *,
        symbol: str,
        exit_price: float,
        exit_reason: str = "",
        exit_timestamp: datetime | None = None,
        exit_bar_index: int | None = None,
    ) -> PaperTrade | None:

        position = self.positions.get(
            symbol
        )

        if position is None:
            return None

        pnl = (
            (
                exit_price
                - position.entry_price
            )
            * position.quantity
        )

        if (
            position.direction
            == "SHORT"
        ):

            pnl *= -1

        trade = PaperTrade(
            symbol=position.symbol,
            direction=position.direction,
            entry_price=position.entry_price,
            exit_price=exit_price,
            quantity=position.quantity,
            pnl=pnl,
            entry_timestamp=(
                position.entry_timestamp
            ),
            exit_timestamp=(
                exit_timestamp
                or datetime.now()
            ),
            entry_reason=(
                position.entry_reason
            ),
            exit_reason=exit_reason,
            stop_price=position.stop_price,
            target_price=(
                position.target_price
            ),
            bars_held=(
                exit_bar_index
                - position.entry_bar_index
                if exit_bar_index is not None
                else 0
            ),
        )

        self.completed_trades.append(
            trade
        )

        del self.positions[symbol]

        print(
            f"\n[PAPER] CLOSED "
            f"{symbol} "
            f"@ {exit_price} "
            f"({exit_reason}) "
            f"PnL={pnl:.2f}"
        )

        return trade

    def get_position(
        self,
        *,
        symbol: str,
    ) -> PaperPosition | None:

        return self.positions.get(symbol)

    def has_open_position(
        self,
        *,
        symbol: str,
    ) -> bool:

        return symbol in self.positions
