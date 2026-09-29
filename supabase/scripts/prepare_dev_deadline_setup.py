"""Prepare guarded development-only publication-deadline SQL handoff."""

from uuid import UUID
from prepare_dev_setup import ROOT, local_env

DEV_REF = "vgmkpsestahkfahzdtae"


def render_setup(owner_uid: str) -> str:
    uid = str(UUID(owner_uid))
    migration = (
        (ROOT / "supabase/migrations/202609290004_publication_deadline.sql")
        .read_text(encoding="utf-8")
        .strip()
    )
    if "\nbegin;\n" not in migration or not migration.endswith("commit;"):
        raise ValueError("unexpected_migration_wrapper")
    body = migration.replace("\nbegin;\n", "\n", 1)[: -len("commit;")]
    return f"""-- DEVELOPMENT ONLY: {DEV_REF}; verify the SQL Editor project URL.
begin;
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
end
$guard$;
{body}
commit;
select (public.scan_publish_capabilities()->>'deadline_version')::integer as deadline_version,
       (select data_mode from public.deployment_settings where singleton) as data_mode;
"""


def main() -> None:
    env = local_env(ROOT / ".env.development")
    if env.get("SUPABASE_URL", "").rstrip("/") != f"https://{DEV_REF}.supabase.co":
        raise ValueError("development_project_mismatch")
    path = ROOT / f"data/dev-publication-deadline-{DEV_REF}.sql"
    path.write_text(render_setup(env["APP_OWNER_USER_ID"]), encoding="utf-8")
    print(f"Prepared: {path}")


if __name__ == "__main__":
    main()
