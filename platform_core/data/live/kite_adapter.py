from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable

from kiteconnect import KiteConnect
from kiteconnect import KiteTicker


CONFIG_PATH = "configs/kite_config.json"


class KiteAdapter:

    def __init__(self) -> None:

        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)

        self.api_key = config["api_key"]

        self.access_token = config["access_token"]

        self.kite = KiteConnect(
            api_key=self.api_key
        )

        self.kite.set_access_token(
            self.access_token
        )

        self.ticker = KiteTicker(
            self.api_key,
            self.access_token,
        )

        self._tick_callbacks: list[
            Callable
        ] = []

        self._connected = False

    @property
    def connected(self) -> bool:

        return self._connected

    def add_tick_callback(
        self,
        callback: Callable,
    ) -> None:

        self._tick_callbacks.append(callback)

    def connect(
        self,
        *,
        instrument_tokens: list[int],
    ) -> None:

        def on_connect(ws, response):

            print(
                "\n[KITE] WebSocket connected."
            )

            self._connected = True

            ws.subscribe(instrument_tokens)

            ws.set_mode(
                ws.MODE_FULL,
                instrument_tokens,
            )

            print(
                f"[KITE] Subscribed: "
                f"{instrument_tokens}"
            )

        def on_ticks(ws, ticks):

            for callback in (
                self._tick_callbacks
            ):

                callback(ticks)

        def on_close(
            ws,
            code,
            reason,
        ):

            self._connected = False

            print(
                f"\n[KITE] Closed: "
                f"{code} {reason}"
            )

        def on_error(
            ws,
            code,
            reason,
        ):

            print(
                f"\n[KITE] Error: "
                f"{code} {reason}"
            )

        self.ticker.on_connect = on_connect

        self.ticker.on_ticks = on_ticks

        self.ticker.on_close = on_close

        self.ticker.on_error = on_error

        thread = threading.Thread(
            target=self.ticker.connect,
            kwargs={"threaded": True},
            daemon=True,
        )

        thread.start()

        timeout = 10

        start = time.time()

        while not self._connected:

            if (
                time.time() - start
                > timeout
            ):

                raise TimeoutError(
                    "Kite websocket "
                    "connection timeout."
                )

            time.sleep(0.1)

    def disconnect(self) -> None:

        self.ticker.close()

        self._connected = False
