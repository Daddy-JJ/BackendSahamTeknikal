"""Generate (never execute) a guarded development migration 005 handoff."""

from uuid import UUID

from prepare_dev_setup import ROOT, local_env

DEV_REF = "vgmkpsestahkfahzdtae"


def render_setup(owner_uid: str) -> str:
    uid = str(UUID(owner_uid))
    migration = (ROOT / "supabase/migrations/202609290005_actual_journal.sql").read_text(
        encoding="utf-8"
    ).strip()
    if "\nbegin;\n" not in migration or not migration.endswith("commit;"):
        raise ValueError("unexpected_migration_wrapper")
    body = migration.replace("\nbegin;\n", "\n", 1)[:-len("commit;")]
    return f"""-- DEVELOPMENT ONLY: {DEV_REF}; verify the SQL Editor project URL.
-- Contains no fixture inserts and does not change deployment mode.
begin;
lock table public.deployment_settings in share mode;
do $guard$
begin
  if (select data_mode from public.deployment_settings where singleton)
      is distinct from 'fixture' then
    raise exception 'development_fixture_mode_required';
  end if;
  if not exists(select 1 from public.app_members where user_id='{uid}'::uuid
                and role='owner' and enabled) then
    raise exception 'development_owner_mismatch';
  end if;
  if to_regprocedure('public.read_market_series(uuid)') is null then
    raise exception 'revision_migrations_required';
  end if;
  if to_regprocedure('public.scan_publish_capabilities()') is null then
    raise exception 'deadline_migration_required';
  end if;
  if (public.scan_publish_capabilities()->>'deadline_version')::integer
      is distinct from 1 then
    raise exception 'deadline_version_mismatch';
  end if;
  if to_regclass('public.actual_trades') is not null then
    raise exception 'actual_schema_already_exists_review_migration_state';
  end if;
end
$guard$;
{body}
commit;
select to_regprocedure('public.apply_actual_journal(text,uuid,jsonb,uuid)') is not null
         as actual_journal_ready,
       to_regprocedure('public.export_actual_journal(date,date,text,text,jsonb,uuid,integer,text)')
         is not null as actual_export_ready,
       (select data_mode from public.deployment_settings where singleton) as data_mode;
"""


def main() -> None:
    env = local_env(ROOT / ".env.development")
    if env.get("SUPABASE_URL", "").rstrip("/") != f"https://{DEV_REF}.supabase.co":
        raise ValueError("development_project_mismatch")
    output = ROOT / f"data/dev-actual-journal-{DEV_REF}.sql"
    output.parent.mkdir(exist_ok=True)
    output.write_text(render_setup(env.get("APP_OWNER_USER_ID", "")), encoding="utf-8")
    print(f"Prepared local handoff only: {output}")


if __name__ == "__main__":
    main()
