"""Automated Paper Journal simulation runner.

Simulates forward scanner signals into trade-level paper experiments.
Zero capital constraint, unit-risk R normalization, strictly isolated
from the actual journal ledger.
"""

import json
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from idx_scanner.context import Calendar
from idx_scanner.models import Costs, ExitConfig, Series, Signal
from idx_scanner.paper import (
    Experiment,
    PaperBook,
    paper_book_from_dict,
    paper_book_to_dict,
    step_paper_book,
    summarize_book,
)
from idx_scanner.strategies import STRATEGIES
from prepare_dev_setup import ROOT

PAPER_DIR = ROOT / "data" / "paper-journal"
BOOK_PATH = PAPER_DIR / "paper-book.json"
SUMMARY_PATH = PAPER_DIR / "latest-summary.json"
ACTIVATION_TIME = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)


def get_default_experiments() -> dict[str, list[Experiment]]:
    """Returns baseline experiments for each strategy."""
    experiments: dict[str, list[Experiment]] = {}
    costs = Costs(Decimal(15), Decimal(25), Decimal(5), status="provisional")
    for strategy in STRATEGIES:
        fixed_2r = Experiment(
            id=f"fixed-2r-{strategy}",
            strategy=strategy,
            exit=ExitConfig(mode="fixed_rr", target_r=Decimal(2)),
            costs=costs,
            activated_at=ACTIVATION_TIME,
        )
        ma_sma10 = Experiment(
            id=f"ma-sma10-{strategy}",
            strategy=strategy,
            exit=ExitConfig(mode="ma_close", target_r=None, ma_type="SMA", period=10),
            costs=costs,
            activated_at=ACTIVATION_TIME,
        )
        experiments[strategy] = [fixed_2r, ma_sma10]
    return experiments


def load_or_create_book(path: Path = BOOK_PATH) -> PaperBook:
    """Loads existing PaperBook from disk, or initializes a new one."""
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        return paper_book_from_dict(data)
    return PaperBook()


def process_paper_session(
    target_session: date,
    series_by_ticker: dict[str, Series],
    signals: Sequence[Signal],
    calendar: Calendar,
    observed_at: datetime,
    *,
    book_path: Path = BOOK_PATH,
    summary_path: Path = SUMMARY_PATH,
) -> tuple[PaperBook, dict]:
    """Steps existing paper trades on target_session, adds newly published signals,

    and persists the updated book and metrics summary.
    """
    book = load_or_create_book(book_path)
    experiments_by_strategy = get_default_experiments()

    # Step 1: Step open and pending trades for target_session
    updated_trades = step_paper_book(book, target_session, series_by_ticker, calendar, observed_at)

    # Step 2: Register newly published signals into baseline experiments
    new_plans = []
    for signal in signals:
        if signal.cohort == "forward" and signal.candidate.execution_eligible:
            strategy = signal.candidate.strategy
            for exp in experiments_by_strategy.get(strategy, []):
                plan = book.add(signal, exp, calendar)
                new_plans.append(plan)

    # Step 3: Compute summary metrics
    summary = summarize_book(book)
    summary.update(
        last_updated_at=observed_at.isoformat(),
        last_session=target_session.isoformat(),
        updated_trades_count=len(updated_trades),
        new_plans_count=len(new_plans),
    )

    # Step 4: Persist book and summary
    book_path.parent.mkdir(parents=True, exist_ok=True)
    serialized_book = paper_book_to_dict(book)
    book_path.write_text(json.dumps(serialized_book, indent=2) + "\n", encoding="utf-8")

    # Serialize summary with Decimal to string conversion
    def decimal_serializer(obj):
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        raise TypeError(f"Type {type(obj)} not serializable")

    summary_path.write_text(
        json.dumps(summary, indent=2, default=decimal_serializer) + "\n",
        encoding="utf-8",
    )

    return book, summary


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary-only", action="store_true", help="Print summary without modifying")
    args = parser.parse_args()

    if args.summary_only:
        if SUMMARY_PATH.exists():
            print(SUMMARY_PATH.read_text(encoding="utf-8"))
        else:
            print(json.dumps({"status": "no_paper_book_found"}))
        return 0

    book = load_or_create_book()
    summary = summarize_book(book)
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
