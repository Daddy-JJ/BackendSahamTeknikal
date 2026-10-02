"""Prepare a guarded development SQL Editor handoff for migration 007; never run it."""

import hashlib
import json

from prepare_dev_actual_setup import DEV_REF
from prepare_dev_setup import ROOT, local_env

VERSION = "202610010007"
MIGRATION = ROOT / "supabase/migrations/202610010007_signal_action_conflict_http.sql"
MANIFEST = ROOT / "supabase/release-manifest.json"


def render_fix() -> str:
    migration = MIGRATION.read_text(encoding="utf-8").replace("\r\n", "\n")
    release = json.loads(MANIFEST.read_text(encoding="utf-8"))
    entry = next(item for item in release["migrations"] if item["version"] == VERSION)
    if hashlib.sha256(migration.encode()).hexdigest() != entry["sha256_lf"]:
        raise ValueError("migration_checksum_mismatch")
    if "\nbegin;\n" not in migration or not migration.rstrip().endswith("commit;"):
        raise ValueError("unexpected_migration_wrapper")
    body = migration.replace("\nbegin;\n", "\n", 1).rstrip()[: -len("commit;")]
    return f"""-- DEVELOPMENT ONLY: {DEV_REF}; verify the SQL Editor project URL.
-- Generated from the checksum-verified migration {VERSION}; do not edit the body.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '30s';
lock table public.deployment_settings in share mode;
do $guard$
declare v_definition text;
begin
  if (select data_mode from public.deployment_settings where singleton)
      is distinct from 'fixture' then
    raise exception 'development_fixture_mode_required';
  end if;
  if (select count(*) from public.app_members where role='owner' and enabled) <> 1 then
    raise exception 'expected_one_enabled_development_owner';
  end if;
  if to_regclass('public.signal_action_requests') is null then
    raise exception 'migration_001_required';
  end if;
  select pg_get_functiondef(to_regprocedure(
    'public.set_signal_action(text,text,integer,uuid)')) into v_definition;
  if v_definition is null or strpos(v_definition,
      'raise exception ''revision_conflict'' using errcode = ''40001'';') = 0 then
    raise exception 'unexpected_signal_conflict_function_version';
  end if;
end
$guard$;
{body}
commit;
select (strpos(pg_get_functiondef(to_regprocedure(
         'public.set_signal_action(text,text,integer,uuid)')),
         'raise exception ''revision_conflict'' using errcode = ''PT412'';') > 0)
       as signal_conflict_http_ready,
       (select data_mode from public.deployment_settings where singleton) as data_mode;
"""


def main() -> None:
    env = local_env(ROOT / ".env.development")
    if env.get("SUPABASE_URL", "").rstrip("/") != f"https://{DEV_REF}.supabase.co":
        raise ValueError("development_project_mismatch")
    output = ROOT / f"data/dev-signal-conflict-{DEV_REF}.sql"
    output.parent.mkdir(exist_ok=True)
    content = render_fix()
    if output.exists():
        if output.read_text(encoding="utf-8") != content:
            raise ValueError("existing_handoff_differs_refusing_overwrite")
    else:
        output.write_text(content, encoding="utf-8")
    print(f"Prepared guarded development handoff: {output}")


if __name__ == "__main__":
    main()
