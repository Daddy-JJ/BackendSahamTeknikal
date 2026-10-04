"""Offline exact-match review queue from locally extracted KSEI PDF facts.

This queue is not an approval manifest. Ambiguous amounts, mismatches, duplicate
schedules and amendment titles remain pending. The reviewer must inspect source
facts before promoting any queue rows into the engine's exact-evidence manifest.
"""

import hashlib
import json
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

from idx_scanner.models import digest
from prepare_dev_setup import ROOT
from publish_first_live_hold_run import captured_series

MONTHS = dict(
    zip(
        [
            "Januari",
            "Februari",
            "Maret",
            "April",
            "Mei",
            "Juni",
            "Juli",
            "Agustus",
            "September",
            "Oktober",
            "November",
            "Desember",
        ],
        range(1, 13),
        strict=True,
    )
)
DATE = (
    r"(\d{1,2})\s+(Januari|Februari|Maret|April|Mei|Juni|Juli|Agustus|"
    r"September|Oktober|November|Desember)\s+(20\d{2})"
)


def id_date(text):
    match = re.fullmatch(DATE, text.strip(), flags=re.IGNORECASE)
    if not match:
        raise ValueError("source_date_unrecognized")
    return date(int(match[3]), MONTHS[match[2].capitalize()], int(match[1]))


def schedule_facts(text):
    ex = re.search(
        r"Tanggal Ex Dividen di Pasar Regular?\s*&\s*Pasar Negosiasi\s+" + DATE,
        text,
        flags=re.IGNORECASE,
    )
    cash = re.search(
        (
            r"Setiap\s+1\s*\(Satu\)\s+saham\s+akan mendapatkan dividen\s+"
            r"(?:tunai|Interim)\s+sebesar\s+Rp\.?\s*([\d.,]+)"
        ),
        text,
        flags=re.IGNORECASE,
    )
    if not ex or not cash:
        raise ValueError("unrecognized_source_table")
    amount = cash[1].rstrip(".,")
    if "," in amount:
        amount = amount.replace(".", "").replace(",", ".")
    elif "." in amount:
        parts = amount.split(".")
        if len(parts) > 2 or (len(parts[1]) == 3 and parts[0] != "0"):
            raise ValueError("ambiguous_source_decimal_separator")
    return id_date(" ".join(ex.groups())), Decimal(amount), ex[0], cash[0]


def build_queue(root: Path):
    folder = root / "data/sources/ksei-research-20261003"
    collected = json.loads((folder / "collection.json").read_text())
    raw = captured_series()
    candidates, pending = [], []
    for source in collected["sources"]:
        file = root / source["source_file"]
        if hashlib.sha256(file.read_bytes()).hexdigest() != source["source_sha256"]:
            raise ValueError("source_checksum_mismatch")
        text_file = file.with_suffix(".txt")
        if not text_file.exists():
            pending.append({**source, "reason": "text_extraction_pending"})
            continue
        text = text_file.read_text(encoding="utf-8")
        if not source["title"].startswith("Jadwal Pelaksanaan Pembagian"):
            pending.append(
                {**source, "reason": "amendment_or_other_notice_review_required"}
            )
            continue
        try:
            session, value, ex_quote, cash_quote = schedule_facts(text)
        except ValueError as exc:
            pending.append({**source, "reason": str(exc)})
            continue
        for ticker in source["tickers"]:
            actions = [
                a
                for a in raw[ticker].actions
                if a.kind == "dividend" and a.session == session
            ]
            if len(actions) != 1 or Decimal(actions[0].value) != value:
                pending.append(
                    {
                        **source,
                        "ticker": ticker,
                        "session": session.isoformat(),
                        "source_value": str(value),
                        "provider_values": [a.value for a in actions],
                        "reason": "provider_event_or_exact_value_mismatch",
                    }
                )
                continue
            candidates.append(
                {
                    **source,
                    "ticker": ticker,
                    "session": session.isoformat(),
                    "value": actions[0].value,
                    "source_value": str(value),
                    "action_digest": digest(actions[0]),
                    "ex_date_quote": ex_quote,
                    "cash_value_quote": cash_quote,
                    "published_date": id_date(source["published"]).isoformat(),
                    "review_status": "exact_candidate_pending_review",
                }
            )
    return {
        "automatic_approval": False,
        "production_write": False,
        "candidates": candidates,
        "pending": pending,
        "collection_failures": collected["failures"],
    }


def main():
    report = build_queue(ROOT)
    (ROOT / "data/ksei-dividend-review-queue-20261003.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "exact_candidates": len(report["candidates"]),
                "pending_sources": len(report["pending"]),
                "collection_failures": len(report["collection_failures"]),
                "automatic_approval": False,
            }
        )
    )


if __name__ == "__main__":
    main()
