"""Chart 015/016 native upgrade/security proof in a disposable no-network database."""

import json
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from rehearse_restored_release import checked_release
from restore_backup_prompt import (
    ROOT,
    RestoreFailure,
    launch_target,
    local_sql,
    run,
    set_source_database_owner,
)

ECONOMIC_TABLES = (
    "app_members",
    "deployment_settings",
    "scan_runs",
    "scan_run_items",
    "signals",
    "scan_run_signals",
    "signal_actions",
    "audit_events",
    "paper_trades",
    "paper_models",
    "paper_events",
    "signal_evaluations",
    "actual_trades",
    "actual_fills",
    "actual_fill_corrections",
    "actual_stop_events",
    "actual_notes",
    "actual_trade_tags",
)


def fingerprints(name):
    expressions = ",".join(
        f"'{table}',(SELECT md5(coalesce(string_agg(to_jsonb(t)::text,'' "
        f"ORDER BY to_jsonb(t)::text),'')) FROM public.{table} t)"
        for table in ECONOMIC_TABLES
    )
    return json.loads(local_sql(name, "SELECT jsonb_build_object(" + expressions + ");"))


def main():
    name = "idx-restore-check-" + uuid4().hex
    owner = "11111111-1111-4111-8111-111111111111"
    outsider = "22222222-2222-4222-8222-222222222222"
    report = {"scope": "native-local-no-network", "remote": False}
    try:
        launch_target(name)
        local_sql(
            name,
            """CREATE ROLE postgres NOSUPERUSER LOGIN; CREATE ROLE anon;
          CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS;
          CREATE SCHEMA auth; CREATE TABLE auth.users(id uuid PRIMARY KEY);
          CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$
            SELECT nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
          GRANT USAGE ON SCHEMA auth TO postgres,anon,authenticated,service_role;
          GRANT REFERENCES ON auth.users TO postgres;
          GRANT EXECUTE ON FUNCTION auth.uid() TO postgres,anon,authenticated,service_role;""",
        )
        set_source_database_owner(name, "postgres")
        migrations = checked_release(ROOT)
        for _, sql in migrations[:14]:
            local_sql(name, "SET ROLE postgres;\n" + sql)
        local_sql(
            name,
            f"""INSERT INTO auth.users VALUES('{owner}'),('{outsider}');
          INSERT INTO public.app_members(user_id) VALUES('{owner}');
          INSERT INTO public.actual_trades(owner_id,data_mode,ticker,primary_strategy,
            exit_policy_snapshot,initial_stop,current_stop)
            VALUES('{owner}','live','ADRO','MACD_EMA200_V1','{{}}',90,90);""",
        )
        before = fingerprints(name)
        for index, (_, sql) in enumerate(migrations[14:], start=15):
            code = "PZ" + str(index).zfill(3)
            failed = (
                sql.rstrip().removesuffix("commit;")
                + f"DO $$ BEGIN RAISE SQLSTATE '{code}'; END $$;\ncommit;"
            )
            try:
                local_sql(name, "SET ROLE postgres;\n" + failed)
            except RestoreFailure as error:
                assert error.details["sqlstate"] == code
            else:
                raise AssertionError("injected_chart_failure_not_observed")
            query = (
                "SELECT to_regclass('public.ticker_chart_artifacts_v1') IS NULL;"
                if index == 15 else
                "SELECT to_regprocedure('public.prune_ticker_chart_cursors_v1(integer)') IS NULL;"
            )
            assert local_sql(name, query).strip() == "t"
            assert fingerprints(name) == before
            local_sql(name, "SET ROLE postgres;\n" + sql)
            assert fingerprints(name) == before
        assert local_sql(name, "SELECT count(*) FROM public.actual_trades;").strip() == "1"
        grants = json.loads(
            local_sql(
                name,
                """SELECT json_build_object(
          'reader_owner',has_function_privilege('authenticated','public.read_ticker_chart_v1(jsonb)','EXECUTE'),
          'reader_anon',has_function_privilege('anon','public.read_ticker_chart_v1(jsonb)','EXECUTE'),
          'writer_owner',has_function_privilege('authenticated',
            'public.persist_ticker_chart_artifact_v1(jsonb)','EXECUTE'),
          'writer_service',has_function_privilege('service_role',
            'public.persist_ticker_chart_artifact_v1(jsonb)','EXECUTE'),
          'cleanup_service',has_function_privilege('service_role',
            'public.prune_ticker_chart_cursors_v1(integer)','EXECUTE'),
          'cleanup_owner',has_function_privilege('authenticated',
            'public.prune_ticker_chart_cursors_v1(integer)','EXECUTE'),
          'core_owner',has_function_privilege('authenticated',
            'chart_private.read_ticker_chart_core_v1(jsonb)','EXECUTE'),
          'table_bypass',has_table_privilege('authenticated','public.ticker_chart_artifacts_v1','SELECT'));""",
            )
        )
        assert grants == {
            "reader_owner": True,
            "reader_anon": False,
            "writer_owner": False,
            "writer_service": True,
            "cleanup_service": True,
            "cleanup_owner": False,
            "core_owner": False,
            "table_bypass": False,
        }
        result = json.loads(
            local_sql(
                name,
                "SET ROLE authenticated;"
                f"SELECT set_config('request.jwt.claim.sub','{outsider}',false);"
                'SELECT public.read_ticker_chart_v1(\'{"ticker":"ADRO"}\');',
            ).splitlines()[-1]
        )
        assert result["error"]["code"] == "FORBIDDEN"
        result = json.loads(
            local_sql(
                name,
                "SET ROLE authenticated;"
                f"SELECT set_config('request.jwt.claim.sub','{owner}',false);"
                'SELECT public.read_ticker_chart_v1(\'{"ticker":"ADRO"}\');',
            ).splitlines()[-1]
        )
        assert result["error"]["code"] == "DATA_UNAVAILABLE"
        loaded = json.loads(
            local_sql(
                name,
                "SET ROLE service_role;"
                f"SELECT public.load_ticker_chart_inputs_v1('{owner}','ADRO');",
            )
        )
        assert len(loaded["actual_trades"]) == 1 and loaded["data_mode"] == "live"
        report.update(
            upgrade014_to015=True,
            injected015_rollback=True,
            upgrade015_to016=True,
            injected016_rollback=True,
            ledger_preserved=True,
            grants=grants,
            owner_outsider_denial=True,
            service_input_loader=True,
            economic_fingerprints_preserved=list(ECONOMIC_TABLES),
        )
        print(json.dumps(report))
    finally:
        assert run("rm", "--force", name, text=True).returncode == 0


if __name__ == "__main__":
    main()
