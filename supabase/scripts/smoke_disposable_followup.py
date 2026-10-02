"""Additional HTTP gates on the fixed local QA target, never hosted production."""

import json
import secrets
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal

import httpx
from smoke_disposable_auth import BASE, PROJECT, ROOT, sql


def main():
    import os
    import subprocess
    from pathlib import Path

    report = {
        "target": PROJECT,
        "production_write": False,
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "checks": {},
    }
    stage = "guard"
    try:
        assert (
            sql("select data_mode from deployment_settings where singleton;")
            == "fixture"
        )
        assert sql("select count(*) from auth.users;") == "4"
        cli = Path(os.environ["LOCALAPPDATA"]) / (
            "npm-cache/_npx/c34c3565ecb5471d/node_modules/@supabase/cli-windows-x64/bin/supabase.exe"
        )
        result = subprocess.run(
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
        assert result.returncode == 0
        keys = json.loads(result.stdout)
        anon, service = keys["ANON_KEY"], keys["SERVICE_ROLE_KEY"]
        tokens, ids = {}, {}
        with httpx.Client(base_url=BASE, timeout=60, trust_env=False) as client:
            admin = {"apikey": service, "Authorization": "Bearer " + service}
            users = client.get("/auth/v1/admin/users", headers=admin).json()["users"]
            assert len(users) == 4 and all(
                u["email"].endswith("@idx-smoke.invalid") for u in users
            )
            password = secrets.token_urlsafe(32)
            for user in users:
                label = user["email"].split("-", 1)[0]
                assert label in ("owner_a", "owner_b", "outsider", "disabled_owner")
                ids[label] = str(uuid.UUID(user["id"]))
                assert (
                    client.put(
                        "/auth/v1/admin/users/" + ids[label],
                        headers=admin,
                        json={"password": password},
                    ).status_code
                    == 200
                )
                login = client.post(
                    "/auth/v1/token?grant_type=password",
                    headers={"apikey": anon},
                    json={"email": user["email"], "password": password},
                )
                assert login.status_code == 200
                tokens[label] = login.json()["access_token"]
                if label == "owner_a":
                    second = client.post(
                        "/auth/v1/token?grant_type=password",
                        headers={"apikey": anon},
                        json={"email": user["email"], "password": password},
                    )
                    assert second.status_code == 200
                    tokens["second"] = second.json()["access_token"]

            def req(label, method, path, **kwargs):
                h = {"apikey": anon}
                if label != "anon":
                    h["Authorization"] = "Bearer " + tokens[label]
                return client.request(method, "/rest/v1/" + path, headers=h, **kwargs)

            stage = "all_tables_rls"
            tables = (
                "actual_trades",
                "actual_fills",
                "actual_fill_corrections",
                "actual_stop_events",
                "actual_notes",
                "actual_trade_tags",
                "actual_journal_requests",
            )
            codes = {}
            for label in ("owner_a", "owner_b", "outsider", "disabled_owner", "anon"):
                codes[label] = {}
                for table in tables:
                    response = req(label, "GET", table, params={"select": "*"})
                    codes[label][table] = response.status_code
                    if label == "anon":
                        assert response.status_code in (401, 403)
                    else:
                        assert response.status_code == 200
                        rows = response.json()
                        if label in ("outsider", "disabled_owner"):
                            assert rows == []
                        else:
                            assert all(x["owner_id"] == ids[label] for x in rows)
                for rpc in ("actual_journal_analytics", "export_actual_journal"):
                    response = req(label, "POST", "rpc/" + rpc, json={})
                    codes[label][rpc] = response.status_code
                    if label in ("outsider", "disabled_owner", "anon"):
                        assert response.status_code in (401, 403)
                    else:
                        assert response.status_code == 200
            report["http_statuses"] = codes
            report["checks"]["seven_tables_and_analytics_export_rls"] = True
            response = req("owner_a", "POST", "actual_trades", json={"ticker": "TEST"})
            assert response.status_code == 403
            report["checks"]["direct_table_mutation_denied"] = True

            trade = req(
                "owner_a", "GET", "actual_trades", params={"select": "id,revision"}
            ).json()[0]
            snapshot = {
                "version": "disposable-http-v1",
                "mode": "fixed_rr",
                "target_r": 2,
            }

            def apply(action, payload):
                response = req(
                    "owner_a",
                    "POST",
                    "rpc/apply_actual_journal",
                    json={
                        "p_action": action,
                        "p_trade_id": trade["id"],
                        "p_payload": payload,
                        "p_request_id": str(uuid.uuid4()),
                    },
                )
                assert response.status_code == 200
                trade["revision"] = response.json()["revision"]
                return response.json()

            stage = "fee_quality_fk"
            fills = req(
                "owner_a",
                "GET",
                "actual_fills",
                params={
                    "select": "id,side,quantity,price_idr,fee_idr",
                    "trade_id": "eq." + trade["id"],
                },
            ).json()
            fill = next(x for x in fills if x["side"] == "buy")
            payload = {
                "fill_id": fill["id"],
                "quantity": fill["quantity"],
                "price_idr": fill["price_idr"],
                "fee_idr": fill["fee_idr"],
                "reason": "Disposable fee quality check",
            }
            apply(
                "correct_fill",
                {
                    **payload,
                    "expected_revision": trade["revision"],
                    "fee_status": "estimated",
                },
            )
            analytics = req(
                "owner_a",
                "POST",
                "rpc/actual_journal_analytics",
                json={"p_exit_snapshot": snapshot},
            ).json()
            assert (
                analytics["fee_quality"] == "includes_estimates"
                and analytics["estimated_fee_trades"] == 1
            )
            apply(
                "correct_fill",
                {
                    **payload,
                    "expected_revision": trade["revision"],
                    "fee_status": "actual",
                },
            )
            response = req(
                "owner_a",
                "GET",
                "actual_fills",
                params={
                    "select": "id,actual_fill_corrections!actual_fill_corrections_fill_id_fkey(sequence,fee_status)",
                    "id": "eq." + fill["id"],
                    "actual_fill_corrections.order": "sequence.desc",
                    "actual_fill_corrections.limit": 1,
                },
            )
            assert response.status_code == 200
            assert (
                response.json()[0]["actual_fill_corrections"][0]["fee_status"]
                == "actual"
            )
            report["checks"]["estimated_actual_fee_and_latest_correction_fk"] = True

            stage = "concurrent_identical_replay"
            rid = str(uuid.uuid4())
            body = {
                "p_action": "note",
                "p_trade_id": trade["id"],
                "p_payload": {
                    "expected_revision": trade["revision"],
                    "body": "Identical concurrent request",
                },
                "p_request_id": rid,
            }

            def counts():
                return json.loads(
                    sql(
                        f"select json_build_object('revision',(select revision from actual_trades "
                        f"where id='{trade['id']}'),'receipts',(select count(*) from actual_journal_requests "
                        f"where owner_id='{ids['owner_a']}'),'audit',(select count(*) from audit_events "
                        f"where entity_id='{trade['id']}'),'notes',(select count(*) from actual_notes "
                        f"where trade_id='{trade['id']}'))"
                    )
                )

            before = counts()

            def concurrent(label):
                with httpx.Client(
                    base_url=BASE, timeout=30, trust_env=False
                ) as independent:
                    return independent.post(
                        "/rest/v1/rpc/apply_actual_journal",
                        headers={
                            "apikey": anon,
                            "Authorization": "Bearer " + tokens[label],
                        },
                        json=body,
                    )

            assert tokens["owner_a"] != tokens["second"]
            with ThreadPoolExecutor(max_workers=2) as pool:
                replies = list(pool.map(concurrent, ("owner_a", "second")))
            assert [x.status_code for x in replies] == [200, 200]
            assert replies[0].json() == replies[1].json()
            after = counts()
            assert all(after[k] == before[k] + 1 for k in before)
            report["checks"]["two_auth_sessions_identical_replay_one_mutation"] = True

            stage = "cursor_201"
            # Fixtures created by backend RPC in a local SQL claim context.
            # Cursor/analytics reads below use a real Auth-issued owner JWT.
            sql(
                f"begin; select set_config('request.jwt.claim.sub','{ids['owner_a']}',true);"
                "set local role authenticated; do $$ declare t uuid; i integer; begin "
                "for i in 1..201 loop "
                't := (public.apply_actual_journal(\'create\',null,\'{"ticker":"CURSOR",'
                '"primary_strategy":"MACD_EMA200_V1","initial_stop":95,'
                '"exit_policy_snapshot":{"version":"disposable-cursor-v1","mode":"fixed_rr",'
                "\"target_r\":2}}',gen_random_uuid())->>'trade_id')::uuid;"
                'perform public.apply_actual_journal(\'fill\',t,\'{"expected_revision":1,"side":"buy",'
                '"quantity":1,"price_idr":100,"fee_idr":0,"fee_status":"actual",'
                '"filled_at":"2026-09-01T03:00:00Z"}\',gen_random_uuid());'
                'perform public.apply_actual_journal(\'fill\',t,\'{"expected_revision":2,"side":"sell",'
                '"quantity":1,"price_idr":110,"fee_idr":0,"fee_status":"actual",'
                '"filled_at":"2026-09-02T03:00:00Z"}\',gen_random_uuid());'
                "end loop; end $$; commit;"
            )
            cohort = {
                "version": "disposable-cursor-v1",
                "mode": "fixed_rr",
                "target_r": 2,
            }
            cursor, rows, pages = None, [], []
            while True:
                response = req(
                    "owner_a",
                    "POST",
                    "rpc/export_actual_journal",
                    json={
                        "p_exit_snapshot": cohort,
                        "p_status": "closed",
                        "p_limit": 200,
                        "p_after": cursor,
                    },
                )
                assert response.status_code == 200
                page = response.json()
                pages.append(len(page["rows"]))
                rows.extend(page["rows"])
                if not page["has_more"]:
                    break
                cursor = page["next_after"]
                assert cursor and len(pages) < 3
            assert pages == [200, 1] and len({x["trade_id"] for x in rows}) == 201
            assert sum(Decimal(x["realized_pnl_idr"]) for x in rows) == 2010
            analytics = req(
                "owner_a",
                "POST",
                "rpc/actual_journal_analytics",
                json={"p_exit_snapshot": cohort},
            ).json()
            assert (
                analytics["closed"] == 201
                and Decimal(str(analytics["net_pnl_idr"])) == 2010
            )
            report["checks"]["http_cursor_200_1_no_duplicates_analytics_ledger"] = True
            report["cursor"] = {
                "pages": pages,
                "unique_trades": 201,
                "terminal_has_more": False,
                "fixture_creation": "local SQL claims + backend RPC",
                "reads": "real Auth JWT HTTP",
            }
        report["status"] = "PASS_local_disposable_only"
    except Exception as error:  # noqa: BLE001 -- never print Auth/subprocess credential details.
        report.update(
            status="FAIL_or_BLOCKED", stage=stage, error_type=type(error).__name__
        )
    (ROOT / "data" / "disposable-followup-20261002.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return int(report["status"] != "PASS_local_disposable_only")


if __name__ == "__main__":
    raise SystemExit(main())
