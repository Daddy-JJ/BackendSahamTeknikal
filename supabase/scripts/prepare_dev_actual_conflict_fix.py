"""Generate a guarded, development-only migration 006 SQL handoff; never execute it."""

from prepare_dev_actual_setup import DEV_REF
from prepare_dev_setup import ROOT, local_env


def render_fix(owner_uid: str) -> str:
    from uuid import UUID

    uid = str(UUID(owner_uid))
    migration = (
        ROOT / "supabase/migrations/202609300006_actual_journal_conflict_http.sql"
    ).read_text(encoding="utf-8").strip()
    if "\nbegin;\n" not in migration or not migration.endswith("commit;"):
        raise ValueError("unexpected_migration_wrapper")
    body = migration.replace("\nbegin;\n", "\n", 1)[: -len("commit;")]
    return f"""-- DEVELOPMENT ONLY: {DEV_REF}; verify the SQL Editor project URL.
-- Does not change journal data, owner permissions or deployment mode.
begin;
lock table public.deployment_settings in share mode;
do $guard$
declare v_definition text;
begin
  if (select data_mode from public.deployment_settings where singleton)
      is distinct from 'fixture' then
    raise exception 'development_fixture_mode_required';
  end if;
  if not exists(select 1 from public.app_members where user_id='{uid}'::uuid
                and role='owner' and enabled) then
    raise exception 'development_owner_mismatch';
  end if;
  select pg_get_functiondef(to_regprocedure(
    'public.apply_actual_journal(text,uuid,jsonb,uuid)')) into v_definition;
  if v_definition is null then
    raise exception 'migration_005_required';
  end if;
  if strpos(v_definition,
      'raise exception ''revision_conflict'' using errcode = ''40001'';') = 0 then
    raise exception 'unexpected_conflict_function_version';
  end if;
end
$guard$;
{body}
commit;
select strpos(pg_get_functiondef(to_regprocedure(
         'public.apply_actual_journal(text,uuid,jsonb,uuid)')),
         'raise exception ''revision_conflict'' using errcode = ''PT412'';') > 0
       as actual_conflict_http_ready,
       (select data_mode from public.deployment_settings where singleton) as data_mode;
"""


def main() -> None:
    env = local_env(ROOT / ".env.development")
    if env.get("SUPABASE_URL", "").rstrip("/") != f"https://{DEV_REF}.supabase.co":
        raise ValueError("development_project_mismatch")
    output = ROOT / f"data/dev-actual-conflict-fix-{DEV_REF}.sql"
    output.parent.mkdir(exist_ok=True)
    output.write_text(render_fix(env.get("APP_OWNER_USER_ID", "")), encoding="utf-8")
    print(f"Prepared local handoff only: {output}")


if __name__ == "__main__":
    main()
