"""Bounded public KSEI source collection; never approves actions or alters prices.

Only cash-dividend archive rows for captured universe symbols are collected.
PDF bytes and archive pages remain ignored local evidence. Amendments are kept
alongside original schedules, not silently superseded. No database connection.
"""

import hashlib
import json
import re
import time
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx
from prepare_dev_setup import ROOT
from publish_first_live_hold_run import captured_series

BASE = "https://web.ksei.co.id"
FOLDER = ROOT / "data/sources/ksei-research-20261003"
ARCHIVE = BASE + "/publications/corporate-action-schedules/cash-dividend"


class ArchiveRows(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.cells = None
        self.cell = None
        self.href = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.cells, self.href = [], None
        if tag == "td" and self.cells is not None:
            self.cell = []
        if tag == "a" and self.cell is not None:
            self.href = dict(attrs).get("href")

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag == "td" and self.cell is not None:
            self.cells.append(" ".join("".join(self.cell).split()))
            self.cell = None
        if tag == "tr" and self.cells is not None:
            if len(self.cells) == 3 and self.href:
                self.rows.append((*self.cells, self.href))
            self.cells = None


def source_url(href):
    url = urljoin(BASE, href)
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "web.ksei.co.id"
        or not parsed.path.startswith("/Announcement/Files/")
        or not parsed.path.lower().endswith(".pdf")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("unexpected_public_source_url")
    return url


def main():
    FOLDER.mkdir(parents=True, exist_ok=True)
    series = captured_series()
    symbols = {t for t, s in series.items() if s.actions}
    report = {
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "production_write": False,
        "automatic_approval": False,
        "http_requests": 0,
        "sources": [],
        "failures": [],
        "archive_months": [],
    }
    seen = set()
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        for year in (2023, 2024, 2025, 2026):
            months = (12,) if year == 2023 else range(1, 13 if year < 2026 else 11)
            for month in months:
                path = FOLDER / f"archive-{year}-{month:02}.html"
                if not path.exists():
                    # The legacy filter returned 500 with a persistent session;
                    # independent public GETs succeeded for the same parameters.
                    for attempt in range(3):
                        response = httpx.get(
                            ARCHIVE,
                            params={"Month": f"{month:02}", "Year": str(year)},
                            timeout=30,
                            follow_redirects=False,
                        )
                        report["http_requests"] += 1
                        if response.status_code < 500 or attempt == 2:
                            break
                        time.sleep(1 + attempt)
                    if response.status_code != 200:
                        report["failures"].append(
                            {
                                "month": f"{year}-{month:02}",
                                "http": response.status_code,
                            }
                        )
                        continue
                    path.write_bytes(response.content)
                parser = ArchiveRows()
                parser.feed(path.read_text(encoding="utf-8"))
                report["archive_months"].append(
                    {
                        "month": f"{year}-{month:02}",
                        "rows": len(parser.rows),
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                )
                for letter, title, published, href in parser.rows:
                    tickers = set(re.findall(r"\(([A-Z]{4})\)", title)) & symbols
                    # Schedule filenames contain explicit issuer code when the title omits it.
                    prefix = href.rsplit("/", 1)[-1].split("_")[0]
                    if prefix in symbols:
                        tickers.add(prefix)
                    if not tickers:
                        continue
                    url = source_url(href)
                    if url in seen:
                        continue
                    seen.add(url)
                    file = FOLDER / urlsplit(url).path.rsplit("/", 1)[-1]
                    if not file.exists():
                        if report["http_requests"] >= 350:
                            raise ValueError("public_source_request_budget_exhausted")
                        response = client.get(url)
                        report["http_requests"] += 1
                        if (
                            response.status_code != 200
                            or not response.content.startswith(b"%PDF")
                        ):
                            report["failures"].append(
                                {"source": url, "http": response.status_code}
                            )
                            continue
                        file.write_bytes(response.content)
                    report["sources"].append(
                        {
                            "tickers": sorted(tickers),
                            "letter": letter,
                            "title": title,
                            "published": published,
                            "source": url,
                            "source_file": file.relative_to(ROOT).as_posix(),
                            "source_sha256": hashlib.sha256(
                                file.read_bytes()
                            ).hexdigest(),
                            "review_status": "pending_fact_and_amendment_review",
                        }
                    )
                print(
                    json.dumps(
                        {
                            "archive": f"{year}-{month:02}",
                            "sources_collected": len(report["sources"]),
                            "requests": report["http_requests"],
                        }
                    ),
                    flush=True,
                )
    output = FOLDER / "collection.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "collection": str(output.relative_to(ROOT)),
                "sources": len(report["sources"]),
                "failures": len(report["failures"]),
                "production_write": False,
            }
        )
    )


if __name__ == "__main__":
    main()
