"""Retrieve public evidence only when its frozen manifest hash matches.

No existing source is overwritten; checksum failures block runner execution.
No automatic re-approval, credential access or database IO.
"""

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import ZipFile

import httpx
from prepare_dev_setup import ROOT


def hydrate_archive(archive: Path, manifest: dict, root: Path) -> int:
    """Restore only reviewed public bytes; never replace a changed local source."""
    metadata = json.loads(archive.with_suffix(".json").read_text(encoding="utf-8"))
    if hashlib.sha256(archive.read_bytes()).hexdigest() != metadata["sha256"]:
        raise ValueError("reviewed_archive_checksum_mismatch")
    expected = {row["source_file"]: row["source_sha256"] for row in manifest["events"]}
    pending = []
    with ZipFile(archive) as package:
        names = package.namelist()
        if len(names) != len(set(names)) or set(names) != set(expected):
            raise ValueError("reviewed_archive_members_mismatch")
        if sum(info.file_size for info in package.infolist()) > 50_000_000:
            raise ValueError("reviewed_archive_size_limit")
        for name in names:
            file = (root / name).resolve()
            if not file.is_relative_to((root / "data/sources").resolve()):
                raise ValueError("source_path_outside_local_sources")
            content = package.read(name)
            if hashlib.sha256(content).hexdigest() != expected[name]:
                raise ValueError("reviewed_archive_source_checksum_mismatch")
            if file.exists():
                if hashlib.sha256(file.read_bytes()).hexdigest() != expected[name]:
                    raise ValueError("local_reviewed_source_changed")
            else:
                pending.append((file, content))
    # Validate every archive member before writing any public evidence.
    for file, content in pending:
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(content)
    return len(pending)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, help="Frozen previously reviewed public bytes")
    args = parser.parse_args()
    manifest = json.loads(
        (ROOT / "config/reference/ksei-reviewed-dividends-20261003.json").read_text()
    )
    seen = set()
    downloaded = 0
    archived = hydrate_archive(args.archive, manifest, ROOT) if args.archive else 0
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
                "archived_sources_restored": archived,
                "archive_is_prior_review_not_current_amendment_check": bool(args.archive),
                "production_write": False,
            }
        )
    )


if __name__ == "__main__":
    main()
