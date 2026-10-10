"""Explicit local-only PG17 probe. Fresh network-disabled tmpfs; no remote credentials."""
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "supabase/scripts"))
import restore_backup_prompt as restore

OWNER = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def main():
    name = "idx-restore-check-" + uuid4().hex
    checks = []
    original_run = restore.run

    def bounded_run(*args, **kwargs):
        # Local Docker Desktop startup/cleanup can exceed the operator helper's
        # 30s default. Keep SQL/query timeouts unchanged and production helpers intact.
        if args and (args[0] in {"run", "rm"} or "pg_isready" in args):
            kwargs["timeout"] = 90
        return original_run(*args, **kwargs)

    restore.run = bounded_run
    try:
        restore.launch_target(name)
        def sql(text):
            return restore.local_sql(name, text)
        sql("""CREATE ROLE anon NOLOGIN;CREATE ROLE authenticated NOLOGIN;
          CREATE ROLE service_role NOLOGIN BYPASSRLS;CREATE SCHEMA auth;
          CREATE TABLE auth.users(id uuid PRIMARY KEY);
          CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$
            SELECT nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
          GRANT USAGE ON SCHEMA auth,public TO anon,authenticated,service_role;
          GRANT EXECUTE ON FUNCTION auth.uid() TO anon,authenticated,service_role;""")
        manifest = json.loads((ROOT / "supabase/release-manifest.json").read_text())
        bodies = []
        for migration in manifest["migrations"]:
            body = (ROOT / "supabase/migrations" / migration["file"]).read_text().replace("\r\n", "\n")
            assert hashlib.sha256(body.encode()).hexdigest() == migration["sha256_lf"]
            bodies.append(body)
        for body in bodies[:-1]:
            sql(body)
        sql(f"INSERT INTO auth.users VALUES('{OWNER}'),('{OTHER}');"
            f"INSERT INTO public.app_members(user_id) VALUES('{OWNER}');"
            "UPDATE public.deployment_settings SET data_mode='fixture';"
            f"SELECT public.init_paper_model_v1('{OWNER}','fixture');"
            f"SELECT public.commit_paper_session_v1('{OWNER}','fixture',0,'old-checkpoint','2024-01-15',"
            "'{\"experiments\":{},\"trades\":{}}','{}');"
            f"INSERT INTO public.paper_trades(id,owner_id,data_mode,ticker,strategy,experiment_id,exit_mode,state,reason,realized_r)"
            f" VALUES('legacy','{OWNER}','fixture','TEST','FRACTAL_BREAKOUT_V1','legacy','fixed_rr','closed','legacy',2);")
        def state():
            return sql("SELECT json_build_object('models',(SELECT json_agg(x) FROM public.paper_models x),"
                            "'requests',(SELECT json_agg(x) FROM public.paper_runtime_requests x),"
                            "'trades',(SELECT json_agg(x) FROM public.paper_trades x),"
                            "'actual',(SELECT json_agg(x) FROM public.actual_trades x));")
        before = json.loads(state())
        sql(bodies[-1])
        assert json.loads(state()) == before
        checks.append("populated_001_010_to_011_preserved")

        def cas(request):
            return restore.run("exec", "-i", name, "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1",
                               "-v", "VERBOSITY=verbose", "-h", "/tmp", "-U", restore.OPERATOR,
                               "-d", "postgres", text=True, input=f"SET ROLE service_role; SELECT public.commit_paper_session_v1('{OWNER}','fixture',1,'{request}','2024-01-15','{{\"experiments\":{{}},\"trades\":{{}}}}','{{}}');", timeout=60)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(cas, ["native-cas-a", "native-cas-b"]))
        assert min(r.returncode for r in results) == 0
        assert sum(r.returncode == 0 for r in results) == 1
        assert "PT409" in next(r.stderr for r in results if r.returncode)
        winner = "native-cas-a" if results[0].returncode == 0 else "native-cas-b"
        replay = cas(winner)
        assert replay.returncode == 0 and json.loads(replay.stdout)["replayed"] is True
        checks.append("native_two_connection_cas_and_exact_retry")

        fixture = json.loads((ROOT / "supabase/tests/fixtures/paper-engine-canonical-v1.json").read_text())["cases"]["exact_cap_zero_lot"]
        book = fixture["book"]
        activation = sql(f"SELECT activated_at FROM public.paper_models WHERE owner_id='{OWNER}';").strip()
        signal = fixture["signal"]
        signal.update(id="f" * 64, config_hash="c" * 64, input_digest="d" * 64, published_at=activation)
        for trade in book["trades"].values():
            trade["signal"] = signal
            trade["experiment"]["activated_at"] = activation
        sql("INSERT INTO public.signals(id,namespace,data_mode,ticker,strategy,session_date,config_hash,input_digest,universe_version,calendar_version,provider,price_basis,planned_entry_session,cohort,published_at,snapshot) VALUES(" +
            ",".join(map(literal, [signal["id"], "native", "fixture", signal["ticker"], signal["candidate"]["strategy"], signal["session"], signal["config_hash"], signal["input_digest"], "synthetic", "synthetic", "fixture", "test", signal["planned_entry_session"], "forward", activation, json.dumps(signal)])) + ");")

        def commit_native(payload, request):
            return sql(f"SET ROLE service_role; SELECT public.commit_paper_session_v1('{OWNER}','fixture',2,{literal(request)},'2024-01-15',{literal(json.dumps(payload))}::jsonb,'{{}}');")

        duplicate = json.loads(json.dumps(book))
        t = json.loads(json.dumps(next(iter(duplicate["trades"].values()))))
        t["id"] = "different-economic-id"
        duplicate["trades"][t["id"]] = t
        try:
            commit_native(duplicate, "bad-duplicate")
            raise AssertionError("duplicate_accepted")
        except restore.RestoreFailure as error:
            assert error.details["sqlstate"] == "23505"
        assert sql("SELECT count(*) FROM public.paper_trades;").strip() == "1"
        assert sql(f"SELECT revision FROM public.paper_models WHERE owner_id='{OWNER}';").strip() == "2"
        checks.append("economic_duplicate_atomic_rollback")
        result = json.loads(commit_native(book, "exact-zero-lot"))
        assert result["revision"] == 3
        assert all(t["lots"] == 0 and t["reason"] == "skipped_budget" for t in result["book"]["trades"].values())
        checks.append("exact_budget_boundary_zero_lot")

        outsider = f"SET ROLE authenticated; SELECT set_config('request.jwt.claim.sub','{OTHER}',false);"
        assert sql(outsider + "SELECT count(*) FROM public.paper_trades;").splitlines()[-1] == "0"
        for body in [outsider + "SELECT public.read_paper_processing_health_v1();",
                     "SET ROLE anon; SELECT public.read_trade_reporting_v1();",
                     "SET ROLE service_role; UPDATE public.paper_trades SET reason='bad';"]:
            try:
                sql(body)
                raise AssertionError("unauthorized_access_accepted")
            except restore.RestoreFailure as error:
                assert error.details["sqlstate"] == "42501"
        checks.append("owner_outsider_anon_service_DML_denials")
        h = json.loads(sql(f"SELECT public.paper_processing_health_v1('{OWNER}','fixture','2026-10-10T11:00:00Z');"))
        assert h["expected_session"] == "2026-10-09" and h["overdue"] is True
        checks.append("no_job_friday_overdue_from_canonical_calendar")
        print(json.dumps({"status": "PASS", "checks": checks, "native_postgresql": True,
                          "network": "none", "production_write": False, "remote_connected": False}))
    finally:
        assert restore.run("rm", "--force", name, text=True).returncode == 0


if __name__ == "__main__":
    main()
