from dataclasses import replace
from datetime import timedelta

import pytest

from idx_scanner.engine import scan
from idx_scanner.fixtures import sample_market
from idx_scanner.models import CorporateAction, ScanState, canonical_json


@pytest.fixture(scope="module")
def market():
    return sample_market(620)


def run(market, series=None, state=None, published=None, target_index=619):
    data, calendar, universe = market
    session = calendar.sessions[target_index]
    return scan(
        series if series is not None else data,
        session.day,
        calendar,
        universe,
        published or session.closes_at + timedelta(hours=3),
        state or ScanState(),
    )


def test_deterministic_repeat_and_idempotency(market):
    state = ScanState()
    first = run(market, state=state)
    assert first.signals
    second = run(market, state=state)
    assert canonical_json(first) == canonical_json(second)
    assert len(state.signals) == len(first.signals)


def test_future_perturbation_cannot_change_signal_snapshot(market):
    series, calendar, universe = market
    modified = {
        t: replace(
            s,
            bars=s.bars[:611]
            + tuple(replace(b, close=b.close * 2, high=b.high * 3) for b in s.bars[611:]),
        )
        for t, s in series.items()
    }
    assert canonical_json(run(market, target_index=610)) == canonical_json(
        run(market, modified, target_index=610)
    )


@pytest.mark.parametrize(
    "issue", ["missing", "stale", "gap", "zero_volume", "invalid", "corporate_action"]
)
def test_partial_coverage_holds_rs_but_not_all_other_strategies(market, issue):
    original, calendar, universe = market
    data = dict(original)
    s = data["DEMO-B"]
    if issue == "missing":
        del data["DEMO-B"]
    elif issue == "stale":
        data["DEMO-B"] = replace(s, bars=s.bars[:-1])
    elif issue == "gap":
        data["DEMO-B"] = replace(s, bars=s.bars[:300] + s.bars[301:])
    elif issue == "zero_volume":
        data["DEMO-B"] = replace(s, bars=s.bars[:-1] + (replace(s.bars[-1], volume=0),))
    elif issue == "invalid":
        data["DEMO-B"] = replace(s, bars=s.bars[:-1] + (replace(s.bars[-1], high=1),))
    else:
        data["DEMO-B"] = replace(s, actions=(CorporateAction(s.bars[-1].session, "split", "2/1"),))
    result = run(market, data)
    assert result.status == "partial"
    assert (result.coverage_valid, result.coverage_total) == (4, 5)
    assert result.ranking.status == "cross_section_incomplete"
    assert all(s.candidate.strategy != "RS_BREAKOUT_V1" for s in result.signals)
    assert sum(item.status == "evaluated" for item in result.items) == 4


def test_mixed_provider_rejected(market):
    data = dict(market[0])
    data["DEMO-B"] = replace(data["DEMO-B"], price_basis="other")
    with pytest.raises(ValueError, match="mixed_provider"):
        run(market, data)


def test_late_publication_is_not_forward(market):
    result = run(market, published=market[1].sessions[620].opens_at)
    assert result.signals
    assert all(s.cohort == "late_model_only" for s in result.signals)


def test_not_closed_rejected_and_unknown_calendar_blocked(market):
    with pytest.raises(ValueError, match="not_closed"):
        run(market, published=market[1].sessions[619].opens_at)
    data, calendar, universe = market
    with pytest.raises(ValueError, match="blocked_configuration"):
        scan(
            data,
            calendar.sessions[-1].day,
            calendar,
            universe,
            calendar.sessions[-1].closes_at,
            ScanState(),
        )


def test_provider_revision_does_not_overwrite_published_snapshot(market):
    state = ScanState()
    first = run(market, state=state)
    signal = first.signals[0]
    data = dict(market[0])
    old = data[signal.ticker]
    data[signal.ticker] = replace(
        old, bars=old.bars[:-1] + (replace(old.bars[-1], volume=9999999),)
    )
    run(market, data, state=state)
    assert state.signals[signal.id] == signal
