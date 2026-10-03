"""Retrieve public evidence only when its frozen manifest hash matches.

No existing source is overwritten; checksum failures block runner execution.
No automatic re-approval, credential access or database IO.
"""

import hashlib
import json
from urllib.parse import urlsplit

import httpx
from prepare_dev_setup import ROOT


def main():
    manifest = json.loads(
        (ROOT / "config/reference/ksei-reviewed-dividends-20261003.json").read_text()
    )
    seen = set()
    downloaded = 0
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        for row in manifest["events"]:
            file = (ROOT / row["source_file"]).resolve()
            if not file.is_relative_to((ROOT / "data/sources").resolve()):
                raise ValueError("source_path_outside_local_sources")
            if file in seen:
                continue
            seen.add(file)
            url = urlsplit(row["source"])
            if (
                url.scheme != "https"
                or url.query
                or url.fragment
                or url.username
                or url.hostname not in ("web.ksei.co.id", "www.bca.co.id")
            ):
                raise ValueError("unexpected_primary_source")
            content = file.read_bytes() if file.exists() else None
            if content is None:
                response = client.get(row["source"])
                if response.status_code != 200:
                    raise ValueError("primary_source_unavailable")
                content = response.content
            if hashlib.sha256(content).hexdigest() != row["source_sha256"]:
                raise ValueError("primary_source_changed_requires_review")
            if not file.exists():
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(content)
                downloaded += 1
    print(
        json.dumps(
            {
                "source_hashes_verified": len(seen),
                "downloaded": downloaded,
                "production_write": False,
            }
        )
    )


if __name__ == "__main__":
    main()
