# Indian F&O Algo Trading Platform: v1

**The first version of an institutional-style, event-driven algorithmic trading platform for Indian index
derivatives (BankNifty / Nifty) on NSE, integrated with Zerodha Kite Connect.**

Python 3.12 · async/event-driven · market-structure analytics · options analytics · backtesting and paper trading

> v1 is the **foundation prototype**: it established the architecture, data pipeline, structure engines, and
> paper-trading loop. Its successor, **[v2](https://github.com/Madhubala1985/indian-fno-algo-trading-v2)**,
> took it to a live real-market-data dry run on a cloud VM.

---

## What was built

| Domain (`platform_core/`) | What it does |
|---|---|
| `core/` | Enums, constants, immutable event envelopes, the only cross-service contract |
| `orchestration/` | Async event bus, dependency injection, service registry, runtime lifecycle, main orchestrator |
| `data/` | Kite WebSocket ingestion, tick validation pipeline, bar builder, multi-timeframe builder, option-chain ingestion, Redis / PostgreSQL / TimescaleDB interfaces, historical fetcher, replay engine |
| `analytics/` | Causal market structure: swings, BOS/CHOCH, fair-value gaps, liquidity sweeps |
| `options/` | Options analytics: Greeks, IV, open interest, strike selection |
| `intelligence/` | Multi-timeframe market context and bias |
| `adaptive/` | Regime engine, adaptive policy engine, market memory, reflection engine |
| `signals/` | Signal engine combining structure confluence with regime |
| `risk/` | Position sizing and risk limits |
| `execution/` | Zerodha order manager, retry logic, latency monitor, fail-safe exits, reconciliation engine |
| `backtesting/` | Historical replay, backtest runner, batch backtester |
| `paper_trading/` | Paper broker, paper session, exit engine, trade logger, performance tracker, live paper runner |

## Results (honest)
- An end-to-end pipeline ran from raw 1-minute BankNifty data through structure detection, signals, sizing, and simulated execution, with a P&L log.
- The early paper run on real BankNifty data (`logs/paper_trades.csv`, 15 trades) was a **mixed, small sample with no demonstrated edge**.
- The lessons from v1 (bias staleness, session-boundary bar artifacts, exit modelling, the need for out-of-sample gates) directly drove the v2 redesign.

## Skills demonstrated
- Designing a modular, event-driven trading architecture (orchestrator, event bus, dependency injection)
- Real-time market-data engineering: WebSocket ingestion, validation, multi-timeframe bar aggregation
- Broker API integration (Zerodha Kite Connect: auth/session generation, historical data, orders)
- Market microstructure and options concepts (structure, FVGs, liquidity, Greeks, IV, OI)
- Backtesting and paper-trading infrastructure with trade logging and performance analytics

## Repository layout
```
platform_core/   all production code, organized by domain (see table above)
scripts/         backtests, live paper runner, Kite session generation, smoke tests
tests/           unit tests (paper session, exit engine)
configs/         paper-trading config + kite_config.example.json
data/            sample BankNifty 1-minute data
```

## Running
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q
python scripts/run_backtest.py                   # backtest on bundled sample data
# Live paper trading needs your own Kite Connect app:
cp configs/kite_config.example.json configs/kite_config.json   # fill in your key/secret
python scripts/generate_kite_session.py
python scripts/run_live_paper.py
```

## Part of a three-project series
| Project | Market | Focus |
|---|---|---|
| [XAU/USD Gold Quant Research](https://github.com/Madhubala1985/xau-gold-quant-research) | Spot gold, MT5 | Edge discovery and statistical falsification |
| **Indian F&O Algo Trading v1** (this repo) | NSE BankNifty | First platform: event-driven architecture, paper trading |
| [Indian F&O Algo Trading v2](https://github.com/Madhubala1985/indian-fno-algo-trading-v2) | NSE/BSE index options | Live real-data dry-run on a cloud VM, options analytics, fail-closed execution |

---
*Built with AI-pair-programming (Claude Code). For research and education only. Not financial advice. No real-money orders were placed.*
