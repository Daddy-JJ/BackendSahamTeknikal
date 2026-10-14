"""Synthetic cross-language fixture must derive from the same canonical writer."""

from idx_scanner.chart_fixture import synthetic_chart_envelope, synthetic_chart_export


def test_explicit_fixture_export_contains_canonical_receipt_and_render_contract():
    exported = synthetic_chart_export("22222222-2222-4222-8222-222222222222",
                                      "11111111-1111-4111-8111-111111111111")
    envelope = synthetic_chart_envelope()
    assert envelope["success"] is True
    assert envelope["data"]["data_mode"] == "fixture"
    assert envelope["data"]["source"]["input_digest"] == exported["market_record"]["input_digest"]
    assert envelope["data"]["revision"] == exported["p_record"]["revision"]
    assert envelope["data"]["pagination"]["returned_slots"] == 40
    assert envelope["data"]["pagination"]["has_more"] is False
    assert envelope["data"]["indicators"]["sma10"]["eligible_from"] is not None
    assert envelope["data"]["indicators"]["ema200"]["reason"] == "insufficient_history"
