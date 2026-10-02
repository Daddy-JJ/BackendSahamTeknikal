"""Real Auth/HTTP smoke on a fresh, fixed local disposable target only."""

import json
import os
import secrets
import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
PROJECT = "idx-smoke-local-20261002"
DB = "supabase_db_" + PROJECT
BASE = "http://127.0.0.1:54321"


def sql(query):
    result = subprocess.run(
        [
            "docker",
            "--context",
            "desktop-linux",
            "exec",
            "-i",
            DB,
            "psql",
            "-U",
            "postgres",
            "-d",
            "postgres",
            "-X",
            "-At",
            "-v",
            "ON_ERROR_STOP=1",
        ],
        input=query,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("disposable_sql_failed")
    return result.stdout.strip()


def main():
    report = {
        "target": PROJECT,
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "production_write": False,
        "real_auth_jwt": False,
        "checks": {},
    }
    stage = "local_target_readiness"
    try:
        inspect = subprocess.run(
            ["docker", "--context", "desktop-linux", "inspect", DB],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if inspect.returncode:
            raise RuntimeError("disposable_not_running")
        if not json.loads(inspect.stdout)[0]["State"]["Running"]:
            raise RuntimeError("disposable_stopped_pending_safe_bindings")
        containers = subprocess.check_output(
            [
                "docker",
                "--context",
                "desktop-linux",
                "ps",
                "--filter",
                "name=" + PROJECT,
                "--format",
                "{{.Names}}",
            ],
            text=True,
        ).splitlines()
        for name in containers:
            obj = json.loads(
                subprocess.check_output(
                    ["docker", "--context", "desktop-linux", "inspect", name],
                    text=True,
                )
            )[0]
            for bindings in obj["NetworkSettings"]["Ports"].values():
                if bindings and any(x["HostIp"] != "127.0.0.1" for x in bindings):
                    raise RuntimeError("disposable_ports_not_loopback")
        cli = Path(os.environ["LOCALAPPDATA"]) / (
            "npm-cache/_npx/c34c3565ecb5471d/node_modules/@supabase/cli-windows-x64/bin/supabase.exe"
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
            timeout=30,
            check=False,
        )
        if status.returncode:
            raise RuntimeError("disposable_status_failed")
        keys = json.loads(status.stdout)
        anon = keys["ANON_KEY"]
        service = keys["SERVICE_ROLE_KEY"]
        ready = json.loads(
            sql(
                "select json_build_object('users',(select count(*) from auth.users),"
                "'trades',(select count(*) from public.actual_trades),"
                "'members',(select count(*) from public.app_members),"
                "'versions',(select array_agg(version order by version) "
                "from supabase_migrations.schema_migrations));"
            )
        )
        if ready["users"] or ready["trades"] or ready["members"]:
            raise RuntimeError("fresh_disposable_required")
        if ready["versions"] != [
            "202609290001",
            "202609290002",
            "202609290003",
            "202609290004",
            "202609290005",
            "202609300006",
            "202610010007",
        ]:
            raise RuntimeError("disposable_migration_history_mismatch")
        sql(
            "update public.deployment_settings set data_mode='fixture' where singleton;"
        )
        report["checks"]["schema_history_loopback"] = True
        stage = "local_auth"
        password = secrets.token_urlsafe(32)
        users, tokens = {}, {}
        with httpx.Client(base_url=BASE, timeout=30, trust_env=False) as client:
            for label in ("owner_a", "owner_b", "outsider", "disabled_owner"):
                email = f"{label}-{uuid.uuid4().hex}@idx-smoke.invalid"
                response = client.post(
                    "/auth/v1/admin/users",
                    headers={"apikey": service, "Authorization": "Bearer " + service},
                    json={"email": email, "password": password, "email_confirm": True},
                )
                if response.status_code not in (200, 201):
                    raise RuntimeError("disposable_auth_create_failed")
                users[label] = response.json()["id"]
                response = client.post(
                    "/auth/v1/token?grant_type=password",
                    headers={"apikey": anon},
                    json={"email": email, "password": password},
                )
                if response.status_code != 200:
                    raise RuntimeError("disposable_auth_login_failed")
                tokens[label] = response.json()["access_token"]
                if label == "owner_a":
                    second = client.post(
                        "/auth/v1/token?grant_type=password",
                        headers={"apikey": anon},
                        json={"email": email, "password": password},
                    )
                    if second.status_code != 200:
                        raise RuntimeError("second_auth_session_failed")
                    tokens["owner_a_second"] = second.json()["access_token"]
            for label in ("owner_a", "owner_b", "disabled_owner"):
                uid = str(uuid.UUID(users[label]))
                enabled = "false" if label == "disabled_owner" else "true"
                sql(
                    f"insert into public.app_members(user_id,enabled) values('{uid}',{enabled});"
                )
            report["real_auth_jwt"] = True

            def request(label, method, path, **kwargs):
                headers = {"apikey": anon}
                if label != "anon":
                    headers["Authorization"] = "Bearer " + tokens[label]
                return client.request(
                    method, "/rest/v1/" + path, headers=headers, **kwargs
                )

            def apply(label, action, trade, payload, rid=None):
                return request(
                    label,
                    "POST",
                    "rpc/apply_actual_journal",
                    json={
                        "p_action": action,
                        "p_trade_id": trade,
                        "p_payload": payload,
                        "p_request_id": rid or str(uuid.uuid4()),
                    },
                )

            def ok(response):
                if response.status_code != 200:
                    raise RuntimeError(
                        "unexpected_rpc_status_" + str(response.status_code)
                    )
                return response.json()

            snapshot = {
                "version": "disposable-http-v1",
                "mode": "fixed_rr",
                "target_r": 2,
            }
            base = {
                "ticker": "TEST",
                "primary_strategy": "MACD_EMA200_V1",
                "initial_stop": 95,
                "exit_policy_snapshot": snapshot,
            }
            trade = ok(apply("owner_a", "create", None, base))["trade_id"]
            other = ok(apply("owner_b", "create", None, base))["trade_id"]
            stage = "rls_http"
            for label in ("owner_a", "owner_b", "outsider", "disabled_owner", "anon"):
                read = request(label, "GET", "actual_trades", params={"select": "id"})
                if label in ("owner_a", "owner_b"):
                    assert read.status_code == 200 and len(read.json()) == 1
                    assert read.json()[0]["id"] == (
                        trade if label == "owner_a" else other
                    )
                elif label == "anon":
                    assert read.status_code in (401, 403)
                else:
                    assert read.status_code == 200 and read.json() == []
                if label not in ("owner_a", "owner_b"):
                    denied = apply(label, "create", None, base)
                    assert denied.status_code in (401, 403)
                report["checks"][label + "_rls"] = True
            stage = "ledger_replay"
            payload = {
                "expected_revision": 1,
                "side": "buy",
                "quantity": 100,
                "price_idr": 100,
                "fee_idr": 25,
                "fee_status": "estimated",
                "filled_at": "2026-09-01T03:00:00Z",
            }
            rid = str(uuid.uuid4())
            first = ok(apply("owner_a", "fill", trade, payload, rid))
            assert ok(apply("owner_a", "fill", trade, payload, rid)) == first

            def counts():
                return sql(
                    f"select json_build_object('revision',(select revision from actual_trades "
                    f"where id='{trade}'),'receipts',(select count(*) from actual_journal_requests "
                    f"where owner_id='{users['owner_a']}'),'audit',(select count(*) from audit_events "
                    f"where entity_id='{trade}'),'notes',(select count(*) from actual_notes "
                    f"where trade_id='{trade}'));"
                )

            before = counts()
            conflict = apply("owner_a", "fill", trade, {**payload, "fee_idr": 26}, rid)
            assert conflict.status_code == 400 and conflict.json()["code"] == "23514"
            stale = apply(
                "owner_a", "note", trade, {"expected_revision": 1, "body": "stale"}
            )
            assert (
                stale.status_code == 412
                and stale.json()["message"] == "revision_conflict"
            )
            assert counts() == before
            report["checks"]["replay_conflict_stale_no_extra_rows"] = True
            ok(
                apply(
                    "owner_a",
                    "fill",
                    trade,
                    {
                        **payload,
                        "expected_revision": 2,
                        "price_idr": 102,
                        "fee_status": "actual",
                    },
                )
            )
            finalized = ok(
                apply("owner_a", "finalize", trade, {"expected_revision": 3})
            )
            assert Decimal(str(finalized["ledger"]["initial_risk_idr"])) == 1200
            partial = ok(
                apply(
                    "owner_a",
                    "fill",
                    trade,
                    {
                        **payload,
                        "expected_revision": 4,
                        "side": "sell",
                        "price_idr": 106,
                        "fee_status": "actual",
                        "filled_at": "2026-09-02T03:00:00Z",
                    },
                )
            )
            assert partial["ledger"]["open_quantity"] == 100
            estimate = ok(
                request(
                    "owner_a",
                    "POST",
                    "rpc/actual_journal_analytics",
                    json={"p_exit_snapshot": snapshot},
                )
            )
            assert estimate["closed"] == 0 and estimate["open"] == 1
            before = counts()
            oversell = apply(
                "owner_a",
                "fill",
                trade,
                {**payload, "expected_revision": 5, "side": "sell", "quantity": 101},
            )
            assert oversell.status_code == 400 and oversell.json()["code"] == "23514"
            assert counts() == before
            ok(
                apply(
                    "owner_a",
                    "correct_fill",
                    trade,
                    {
                        "expected_revision": 5,
                        "fill_id": first["ledger"]["fill_id"],
                        "quantity": 100,
                        "price_idr": 100,
                        "fee_idr": 25,
                        "fee_status": "actual",
                        "reason": "Actual fee confirmed",
                    },
                )
            )
            closed = ok(
                apply(
                    "owner_a",
                    "fill",
                    trade,
                    {
                        **payload,
                        "expected_revision": 6,
                        "side": "sell",
                        "price_idr": 107,
                        "fee_status": "actual",
                        "filled_at": "2026-09-03T03:00:00Z",
                    },
                )
            )
            ledger = closed["ledger"]
            assert Decimal(str(ledger["initial_risk_idr"])) == 1200
            assert Decimal(str(ledger["fee_total_idr"])) == 100
            assert Decimal(str(ledger["realized_pnl_idr"])) == 1000
            report["checks"]["canonical_partial_correction_oversell"] = True
            stage = "two_sessions"
            assert tokens["owner_a"] != tokens["owner_a_second"]
            before = json.loads(counts())

            def concurrent(label):
                # Separate network clients and independently issued Auth sessions.
                with httpx.Client(
                    base_url=BASE, timeout=30, trust_env=False
                ) as separate:
                    return separate.post(
                        "/rest/v1/rpc/apply_actual_journal",
                        headers={
                            "apikey": anon,
                            "Authorization": "Bearer " + tokens[label],
                        },
                        json={
                            "p_action": "note",
                            "p_trade_id": trade,
                            "p_payload": {"expected_revision": 7, "body": label},
                            "p_request_id": str(uuid.uuid4()),
                        },
                    )

            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(pool.map(concurrent, ("owner_a", "owner_a_second")))
            assert sorted(x.status_code for x in responses) == [200, 412]
            after = json.loads(counts())
            assert all(after[k] == before[k] + 1 for k in before)
            report["checks"]["independent_auth_sessions_concurrent_revision"] = True
            analytics = ok(
                request(
                    "owner_a",
                    "POST",
                    "rpc/actual_journal_analytics",
                    json={"p_exit_snapshot": snapshot},
                )
            )
            export = ok(
                request(
                    "owner_a",
                    "POST",
                    "rpc/export_actual_journal",
                    json={
                        "p_exit_snapshot": snapshot,
                        "p_status": "closed",
                        "p_limit": 200,
                    },
                )
            )
            assert (
                analytics["closed"] == 1
                and Decimal(str(analytics["net_pnl_idr"])) == 1000
            )
            assert Decimal(str(analytics["expectancy_r"])) == Decimal("0.833333333333")
            assert analytics["fee_quality"] == "actual"
            assert len(export["rows"]) == 1 and export["has_more"] is False
            report["checks"]["analytics_export_closed_snapshot"] = True
        report["status"] = "PASS_local_disposable_auth_http_only"
    except Exception as error:  # noqa: BLE001 -- sanitize Auth and subprocess errors, never tokens.
        report.update(
            status="BLOCKED_or_FAIL",
            stage=stage,
            error=str(error)
            if isinstance(error, RuntimeError)
            else type(error).__name__,
        )
    (ROOT / "data" / "disposable-auth-smoke-20261002.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2))
    return int(report["status"] != "PASS_local_disposable_auth_http_only")


if __name__ == "__main__":
    raise SystemExit(main())
