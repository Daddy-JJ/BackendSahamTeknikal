"""Scanner action007 with real local Auth sessions; fixture target only."""

import json
import os
import secrets
import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import httpx
from idx_scanner.persistence import scan_envelope
from smoke_dev_fixture import fixture_scan
from smoke_disposable_auth import BASE, PROJECT, ROOT, sql


def main():
    report = {
        "target": PROJECT,
        "production_write": False,
        "data_mode": "fixture",
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "checks": {},
    }
    try:
        assert (
            sql("select data_mode from deployment_settings where singleton;")
            == "fixture"
        )
        cli = (
            Path(os.environ["LOCALAPPDATA"])
            / "npm-cache/_npx/c34c3565ecb5471d/node_modules/@supabase/cli-windows-x64/bin/supabase.exe"
        )
        status = subprocess.run(
            [
                str(cli),
                "status",
                "--workdir",
                str(ROOT / "data" / PROJECT),
                "--output",
                "json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert status.returncode == 0
        keys = json.loads(status.stdout)
        anon = keys["ANON_KEY"]
        service = keys["SERVICE_ROLE_KEY"]
        tokens, owner = {}, None
        with httpx.Client(base_url=BASE, timeout=30, trust_env=False) as c:
            admin = {"apikey": service, "Authorization": "Bearer " + service}
            users = c.get("/auth/v1/admin/users", headers=admin).json()["users"]
            assert len(users) == 4 and all(
                u["email"].endswith("@idx-smoke.invalid") for u in users
            )
            for u in users:
                label = u["email"].split("-", 1)[0]
                password = secrets.token_urlsafe(32)
                assert (
                    c.put(
                        "/auth/v1/admin/users/" + u["id"],
                        headers=admin,
                        json={"password": password},
                    ).status_code
                    == 200
                )
                r = c.post(
                    "/auth/v1/token?grant_type=password",
                    headers={"apikey": anon},
                    json={"email": u["email"], "password": password},
                )
                assert r.status_code == 200
                tokens[label] = r.json()["access_token"]
                if label == "owner_a":
                    owner = str(uuid.UUID(u["id"]))
                    r = c.post(
                        "/auth/v1/token?grant_type=password",
                        headers={"apikey": anon},
                        json={"email": u["email"], "password": password},
                    )
                    assert r.status_code == 200
                    tokens["second"] = r.json()["access_token"]
            fixture = fixture_scan()
            r = c.post(
                "/rest/v1/rpc/publish_scan",
                headers=admin,
                json=scan_envelope(fixture, "local_auth_action_smoke", "fixture"),
            )
            assert r.status_code == 200
            signal = fixture.signals[0].id

            def action(label, value, revision, rid):
                with httpx.Client(
                    base_url=BASE, timeout=30, trust_env=False
                ) as independent:
                    return independent.post(
                        "/rest/v1/rpc/set_signal_action",
                        headers={
                            "apikey": anon,
                            "Authorization": "Bearer " + tokens[label],
                        },
                        json={
                            "p_signal_id": signal,
                            "p_action": value,
                            "p_expected_revision": revision,
                            "p_request_id": rid,
                        },
                    )

            rid = str(uuid.uuid4())
            first = action("owner_a", "watchlist", 0, rid)
            assert first.status_code == 200
            replay = action("second", "watchlist", 0, rid)
            assert replay.status_code == 200 and replay.json() == first.json()

            def counts():
                return json.loads(
                    sql(
                        f"select json_build_object('revision',(select revision from signal_actions "
                        f"where owner_id='{owner}' and signal_id='{signal}'),'requests',(select count(*) from signal_action_requests "
                        f"where owner_id='{owner}'),'audit',(select count(*) from audit_events "
                        f"where owner_id='{owner}' and entity_id='{signal}'));"
                    )
                )

            before = counts()
            changed = action("owner_a", "planned", 0, rid)
            stale = action("second", "planned", 0, str(uuid.uuid4()))
            assert changed.status_code == 400 and changed.json()["code"] == "23514"
            assert (
                stale.status_code == 412
                and stale.json()["message"] == "revision_conflict"
            )
            assert counts() == before
            report["checks"]["replay_200_changed_400_23514_stale_412_no_extra_rows"] = (
                True
            )
            for label in ("outsider", "disabled_owner"):
                denied = action(label, "watchlist", 0, str(uuid.uuid4()))
                assert denied.status_code == 403
                report["checks"][label + "_action_denied"] = True
            assert tokens["owner_a"] != tokens["second"]
            with ThreadPoolExecutor(max_workers=2) as pool:
                replies = list(
                    pool.map(
                        lambda label: action(label, "planned", 1, str(uuid.uuid4())),
                        ("owner_a", "second"),
                    )
                )
            assert sorted(r.status_code for r in replies) == [200, 412]
            after = counts()
            assert all(after[k] == before[k] + 1 for k in before)
            report["checks"][
                "two_real_auth_sessions_200_412_one_receipt_audit_revision"
            ] = True
        report["status"] = "PASS_local_disposable_auth_http"
    except Exception as error:  # noqa: BLE001 -- suppress credential-bearing HTTP/subprocess errors.
        report.update(status="FAIL_or_BLOCKED", error_type=type(error).__name__)
    (ROOT / "data" / "disposable-signal-20261002.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return int(report["status"] != "PASS_local_disposable_auth_http")


if __name__ == "__main__":
    raise SystemExit(main())
