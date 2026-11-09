from __future__ import annotations

from platform_core.adaptive.regime_engine import (
    RegimeEngine,
)

from platform_core.intelligence.htf_bias_engine import (
    HTFBiasEngine,
)

from platform_core.analytics.structure.bos_detector import (
    BOSDetector,
    BOSDetectorConfig,
)

from platform_core.analytics.structure.swing_detector import (
    SwingDetector,
    SwingDetectorConfig,
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

from platform_core.backtesting.historical_replay import (
    HistoricalReplayFeed,
)

from platform_core.data.live.live_structure_adapter import (
    LiveStructureAdapter,
)

from platform_core.paper_trading.paper_broker import (
    PaperBroker,
)

from platform_core.paper_trading.performance_tracker import (
    PerformanceTracker,
)

from platform_core.signals.signal_engine import (
    SignalEngine,
)


class BacktestRunner:

    def __init__(
        self,
        *,
        symbol: str,
        timeframe: str = "MIN_1",
    ) -> None:

        self.symbol = symbol

        self.timeframe = timeframe

        self.feed = HistoricalReplayFeed()

        self.adapter = (
            LiveStructureAdapter()
        )

        self.signal_engine = (
            SignalEngine()
        )

        self.paper_broker = (
            PaperBroker()
        )

        self.performance_tracker = (
            PerformanceTracker()
        )

        self.regime_engine = (
            RegimeEngine()
        )

        self.htf_bias_engine = (
            HTFBiasEngine()
        )

        self.swing_detector = (
            SwingDetector(
                config=SwingDetectorConfig(
                    instrument_id=symbol,
                    timeframe=timeframe,
                )
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

    def run(
        self,
        *,
        csv_path: str,
    ) -> None:

        bars = self.feed.load_csv(
            path=csv_path,
            symbol=self.symbol,
        )

        print(
            "\nBACKTEST STARTED\n"
        )

        for live_bar in bars:

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
                        swing_result.confirmed_points
                    ),
                )
            )
            
            if result.emitted_events:

                print("\nEVENTS:\n")

                for event in result.emitted_events:

                    print(event)

            bar_range = (
                live_bar.high_price
                - live_bar.low_price
            )

            average_range = max(
                bar_range,
                1.0,
            )

            regime = (
                self.regime_engine.classify(
                    bar_range=bar_range,
                    average_range=average_range,
                )
            )

            print(
                "\nMARKET REGIME:\n"
            )

            print(regime)


            market_context = (
                self.htf_bias_engine.build_context(
                    daily_bias="NEUTRAL",
                    h4_bias="BULLISH",
                    h1_bias="BULLISH",
                    m15_bias="BULLISH",
                    volatility_regime=(
                        regime.volatility_regime
                    ),
                )
            )
            
            signals = (
                self.signal_engine.generate_signals(
                    symbol=self.symbol,
                    events=result.emitted_events,
                    regime=regime,
                    market_context=market_context,
                )
            )

            for signal in signals:

                print(
                    "\nSIGNAL:\n"
                )

                print(signal)

                if signal.action == "OPEN":

                    if not (
                        self.paper_broker.has_open_position(
                            symbol=self.symbol
                        )
                    ):

                        self.paper_broker.open_position(
                            symbol=self.symbol,
                            direction=signal.direction,
                            entry_price=(
                                live_bar.close_price
                            ),
                            quantity=1,
                        )

                elif signal.action == "CLOSE":

                    if (
                        self.paper_broker.has_open_position(
                            symbol=self.symbol
                        )
                    ):

                        self.paper_broker.close_position(
                            symbol=self.symbol,
                            exit_price=(
                                live_bar.close_price
                            ),
                        )

                
        summary = (
            self.performance_tracker.calculate_summary(
                trades=(
                    self.paper_broker.completed_trades
                )
            )
        )

        print(
            "\nBACKTEST SUMMARY\n"
        )

        print(summary)
