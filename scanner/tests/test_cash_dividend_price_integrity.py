"""Cash metadata never certifies prices or bypasses price-affecting defects."""

import json
from dataclasses import replace

import pytest
from test_dividend_reconciliation import example

from idx_scanner.context import CASH_DIVIDEND_POLICY_VERSION, quality
from idx_scanner.corporate_actions import reconcile_dividends
from idx_scanner.models import CorporateAction, digest
from idx_scanner.paper_runtime import session_source
from idx_scanner.persistence import market_series_envelope, series_from_revision


def policy_record(series):
    return next(json.loads(v) for v in series.provenance
                if json.loads(v)["kind"] == CASH_DIVIDEND_POLICY_VERSION)


@pytest.mark.parametrize("amount", ["0.32207403", "0.32211", "430.0"])
def test_new_or_changed_cash_amount_keeps_prices_and_remains_unreviewed(amount):
    raw, proof, calendar, target = example()
    raw = replace(raw, actions=(replace(raw.actions[0], value=amount),))
    result = reconcile_dividends(raw, (proof,), calendar, target)
    assert quality(result, target, calendar) == "valid"
    assert session_source(result, target, calendar)[2] is True
    assert result.bars is raw.bars and result.price_basis == raw.price_basis
    assert not result.reconciled_actions
    record = policy_record(result)
    assert record["events"] == [{"action_digest": digest(raw.actions[0]),
                                "review_status": "unreviewed"}]
    assert record["evidence_mismatches"]
    assert record["price_changes"] is record["ledger_changes"] is False
    assert reconcile_dividends(result, (proof,), calendar, target) is result
    saved = market_series_envelope(result, namespace="test", data_mode="live")["p_record"]
    assert series_from_revision(saved) == result


def test_new_cash_dividend_without_any_proof_is_not_falsely_approved():
    raw, _, calendar, target = example()
    result = reconcile_dividends(raw, (), calendar, target)
    assert quality(result, target, calendar) == "valid"
    assert not result.reconciled_actions
    assert policy_record(result)["events"][0]["review_status"] == "unreviewed"
    assert not policy_record(result)["evidence_mismatches"]


@pytest.mark.parametrize("reverse", [False, True])
def test_cash_mismatch_does_not_discard_independently_verified_split(reverse):
    raw, proof, calendar, target = example()
    split = CorporateAction(raw.bars[11].session, "split", "4.0")
    split_proof = replace(proof, kind="split", session=split.session, value=split.value,
                          action_digest=digest(split),
                          date_method="trading_start_date_new_nominal")
    changed = replace(raw.actions[0], value="99")
    raw = replace(raw, actions=(changed, split))
    proofs = (proof, split_proof) if not reverse else (split_proof, proof)
    result = reconcile_dividends(raw, proofs, calendar, target)
    assert quality(result, target, calendar) == "valid"
    assert result.reconciled_actions == (digest(split),)
    assert result.bars == raw.bars
    assert digest(changed) not in result.reconciled_actions
    assert reconcile_dividends(result, proofs, calendar, target) is result


@pytest.mark.parametrize("defect", ["split", "unknown_action", "unknown_actions",
                                    "basis", "provider", "invalid", "zero_volume",
                                    "missing_session", "stale"])
def test_cash_metadata_policy_preserves_price_integrity_holds(defect):
    raw, _, calendar, target = example()
    if defect == "split":
        raw = replace(raw, actions=raw.actions + (CorporateAction(target, "split", "2"),))
    elif defect == "unknown_action":
        raw = replace(raw, actions=raw.actions + (CorporateAction(target, "unknown", "2"),))
    elif defect == "unknown_actions":
        raw = replace(raw, actions_complete=False)
    elif defect == "basis":
        raw = replace(raw, price_basis="dividend_adjusted_or_unknown")
    elif defect == "provider":
        raw = replace(raw, provider="eodhd")
    elif defect == "invalid":
        raw = replace(raw, bars=raw.bars[:-1] + (replace(raw.bars[-1], close=-1),))
    elif defect == "zero_volume":
        raw = replace(raw, bars=raw.bars[:-1] + (replace(raw.bars[-1], volume=0),))
    elif defect == "missing_session":
        raw = replace(raw, bars=raw.bars[:100] + raw.bars[101:])
    elif defect == "stale":
        raw = replace(raw, bars=raw.bars[:-1])
    result = reconcile_dividends(raw, (), calendar, target)
    assert quality(result, target, calendar) != "valid"
    assert session_source(result, target, calendar)[2] is False
    assert result.bars == raw.bars


def test_future_cash_and_split_do_not_change_past_eligibility_or_audit():
    raw, _, calendar, target = example()
    before = reconcile_dividends(replace(raw, actions=()), (), calendar, target)
    future = calendar.next(target).day
    raw = replace(raw, actions=(CorporateAction(future, "dividend", "430"),
                                CorporateAction(future, "split", "4")))
    result = reconcile_dividends(raw, (), calendar, target)
    assert quality(result, target, calendar) == quality(before, target, calendar) == "valid"
    assert result.provenance == before.provenance
    assert result.bars == before.bars


def test_unmatched_split_evidence_still_cannot_certify_history():
    raw, proof, calendar, target = example()
    split = CorporateAction(raw.bars[11].session, "split", "4")
    split_proof = replace(proof, kind="split", session=split.session, value=split.value,
                          action_digest=digest(split),
                          date_method="trading_start_date_new_nominal")
    raw = replace(raw, actions=raw.actions + (replace(split, value="5"),))
    with pytest.raises(ValueError, match="provider_event_mismatch"):
        reconcile_dividends(raw, (proof, split_proof), calendar, target)
    assert quality(raw, target, calendar) == "corporate_action_hold"


@pytest.mark.parametrize("action_kind,valid", [("dividend", True), ("split", False)])
def test_paper_and_research_share_price_gate_without_rewriting_frozen_risk(
    signal, calendar, action_kind, valid,
):
    from datetime import timedelta

    from conftest import bar

    from idx_scanner.models import Series
    from idx_scanner.paper import PaperBook, step
    from idx_scanner.paper_research import create_evaluation, step_evaluation
    from idx_scanner.paper_runtime import close_experiments

    experiment = close_experiments(signal.published_at - timedelta(seconds=1))[
        signal.candidate.strategy
    ][0]
    plan = PaperBook().add(signal, experiment, calendar)
    session = calendar.get(signal.planned_entry_session)
    bars = (bar(signal.session), bar(session.day))
    source = Series(signal.ticker, "TEST.JK", "yfinance",
                    "yahoo_provider_ohlcv_auto_adjust_false_v1", bars,
                    actions=(CorporateAction(session.day, action_kind, "430"),))
    current, history, data_valid = session_source(source, session.day, calendar)
    assert data_valid is valid
    trade = step(plan, session.day, current, calendar, session.closes_at,
                 history=history, data_valid=data_valid)
    research = step_evaluation(create_evaluation(signal, "TEST.JK"), session.day,
                               current, calendar, session.closes_at, data_valid=data_valid)
    assert trade.initial_risk == plan.initial_risk
    assert trade.stop == plan.stop and trade.quantity == plan.quantity
    assert trade.planned_stop_loss_idr == plan.planned_stop_loss_idr
    assert trade.planned_stop_loss_idr <= 1000000
    if valid:
        assert trade.state == "open" and trade.entry == plan.planned_entry_price
        assert research["observed_sessions"] == 1
        assert research["results"]["net_5"] == research["results"]["net_10"] == "pending"
    else:
        assert trade.state == "data_hold" and trade.entry is None
        assert research["observed_sessions"] == 0
        assert set(research["results"].values()) == {"data_hold"}
