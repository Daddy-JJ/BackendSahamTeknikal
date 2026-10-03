import sys
from decimal import Decimal
from pathlib import Path

# Add backend and supabase/scripts to sys.path
SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "supabase" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from conftest import bar  # noqa: E402
from paper_journal_runner import (  # noqa: E402
    get_default_experiments,
    load_or_create_book,
    process_paper_session,
)

from idx_scanner.models import Series  # noqa: E402
from idx_scanner.strategies import STRATEGIES  # noqa: E402


def test_default_experiments():
    experiments = get_default_experiments()
    assert set(experiments.keys()) == set(STRATEGIES)
    for strategy in STRATEGIES:
        exps = experiments[strategy]
        assert len(exps) == 2
        fixed = next(e for e in exps if e.exit.mode == "fixed_rr")
        ma = next(e for e in exps if e.exit.mode == "ma_close")
        assert fixed.exit.target_r == Decimal(2)
        assert ma.exit.ma_type == "SMA" and ma.exit.period == 10


def test_process_paper_session_lifecycle(signal, calendar, tmp_path):
    book_file = tmp_path / "paper-book.json"
    summary_file = tmp_path / "latest-summary.json"

    # Verify load_or_create_book on empty
    initial_book = load_or_create_book(book_file)
    assert len(initial_book.trades) == 0

    series_map = {
        signal.ticker: Series(
            signal.ticker,
            f"{signal.ticker}.JK",
            "yfinance",
            "unadjusted_eod",
            (bar(calendar.sessions[0].day, 98, 101, 97, 100),),
            actions_complete=True,
        )
    }

    # Process session 0: signal registered as pending_entry plans
    book, summary = process_paper_session(
        calendar.sessions[0].day,
        series_map,
        [signal],
        calendar,
        calendar.sessions[0].closes_at,
        book_path=book_file,
        summary_path=summary_file,
    )

    assert book_file.exists()
    assert summary_file.exists()
    assert summary["new_plans_count"] == 2  # fixed_rr and ma_close
    assert summary["trades_count"] == 2
    assert summary["open_count"] == 2

    # Now simulate session 1: bar hits target (open=100, high=111, low=96, close=104)
    # Stop was 95, so risk = 5, target for 2R = 100 + 10 = 110. High 111 hits target!
    session_1_bars = (
        bar(calendar.sessions[0].day, 98, 101, 97, 100),
        bar(calendar.sessions[1].day, 100, 111, 96, 104),
    )
    series_map[signal.ticker] = Series(
        signal.ticker,
        f"{signal.ticker}.JK",
        "yfinance",
        "unadjusted_eod",
        session_1_bars,
        actions_complete=True,
    )

    book2, summary2 = process_paper_session(
        calendar.sessions[1].day,
        series_map,
        [],
        calendar,
        calendar.sessions[1].closes_at,
        book_path=book_file,
        summary_path=summary_file,
    )

    assert summary2["new_plans_count"] == 0
    assert summary2["updated_trades_count"] == 2
    # The fixed_rr trade closed on target hit!
    fixed_trade = next(t for t in book2.trades.values() if t.experiment.exit.mode == "fixed_rr")
    assert fixed_trade.state == "closed"
    assert fixed_trade.reason == "target"
    assert fixed_trade.realized_r is not None and fixed_trade.realized_r > Decimal(1)

    # Check summary metrics
    strat_metrics = summary2["strategy_metrics"]["FRACTAL_BREAKOUT_V1"]
    assert strat_metrics["closed"] >= 1
    assert strat_metrics["wins"] >= 1
    assert strat_metrics["win_rate"] == Decimal(1)
