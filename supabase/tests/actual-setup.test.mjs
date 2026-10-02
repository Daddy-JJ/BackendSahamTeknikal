import { PGlite } from "@electric-sql/pglite";
import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

test("development handoff rejects live, wrong owner, missing prerequisites and duplicate apply", async () => {
  const python=process.env.SCANNER_TEST_PYTHON || fileURLToPath(new URL(
    process.platform === "win32" ? "../../scanner/.venv/Scripts/python.exe" : "../../scanner/.venv/bin/python",import.meta.url));
  const scripts=fileURLToPath(new URL("../scripts/",import.meta.url));
  const owner="11111111-1111-4111-8111-111111111111";
  const handoff=execFileSync(python,["-c",
    "import sys; sys.path.insert(0,sys.argv[1]); from prepare_dev_actual_setup import render_setup; print(render_setup(sys.argv[2]))",
    scripts,owner],{encoding:"utf8"});
  const conflictFix=execFileSync(python,["-c",
    "import sys; sys.path.insert(0,sys.argv[1]); from prepare_dev_actual_conflict_fix import render_fix; print(render_fix(sys.argv[2]))",
    scripts,owner],{encoding:"utf8"});
  const db=new PGlite();
  try {
    await db.exec(`create role anon nologin; create role authenticated nologin;
      create role service_role nologin bypassrls; create schema auth;
      create table auth.users(id uuid primary key);
      create function auth.uid() returns uuid language sql stable as $$ select null::uuid $$;`);
    const migrate=async name => db.exec(readFileSync(new URL("../migrations/"+name,import.meta.url),"utf8"));
    await migrate("202609290001_scan_foundation.sql");
    async function reject(pattern) {
      await assert.rejects(() => db.exec(handoff),pattern);
      await db.exec("rollback");
      assert.equal((await db.query("select to_regclass('public.actual_trades') t")).rows[0].t,null);
    }
    await reject(/development_fixture_mode_required/);
    await db.exec("update public.deployment_settings set data_mode='fixture'");
    await reject(/development_owner_mismatch/);
    await db.query("insert into auth.users values ($1)",[owner]);
    await db.query("insert into public.app_members(user_id) values ($1)",[owner]);
    await reject(/revision_migrations_required/);
    await migrate("202609290002_market_series_revisions.sql");
    await migrate("202609290003_market_series_reconstruction.sql");
    await reject(/deadline_migration_required/);
    await migrate("202609290004_publication_deadline.sql");
    const result=await db.exec(handoff);
    assert.deepEqual(result.at(-1).rows[0],{
      actual_journal_ready:true,actual_export_ready:true,data_mode:"fixture",
    });
    assert.equal((await db.query("select count(*)::int n from public.actual_trades")).rows[0].n,0);
    await assert.rejects(() => db.exec(handoff),/actual_schema_already_exists/);
    await db.exec("rollback");
    await db.exec("update public.deployment_settings set data_mode='live'");
    await assert.rejects(() => db.exec(conflictFix),/development_fixture_mode_required/);
    await db.exec("rollback");
    await db.exec("update public.deployment_settings set data_mode='fixture'");
    const fixed=await db.exec(conflictFix);
    assert.deepEqual(fixed.at(-1).rows[0],{
      actual_conflict_http_ready:true,data_mode:"fixture",
    });
    await assert.rejects(() => db.exec(conflictFix),/unexpected_conflict_function_version/);
    await db.exec("rollback");
  } finally { await db.close(); }
});
