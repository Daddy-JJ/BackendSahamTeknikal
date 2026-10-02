"""Generate guarded SQL Editor handoff for market revision migrations 002 + 003."""

from uuid import UUID

from prepare_dev_setup import ROOT, local_env

DEV_REF = "vgmkpsestahkfahzdtae"
MIGRATIONS = (
    "202609290002_market_series_revisions.sql",
    "202609290003_market_series_reconstruction.sql",
)


def render_setup(owner_uid: str) -> str:
    owner_uid = str(UUID(owner_uid))
    blocks = []
    for name in MIGRATIONS:
        sql = (ROOT / "supabase/migrations" / name).read_text(encoding="utf-8").strip()
        if "\nbegin;\n" not in sql or not sql.endswith("commit;"):
            raise ValueError("unexpected_migration_wrapper")
        blocks.append(sql.replace("\nbegin;\n", "\n", 1)[: -len("commit;")].rstrip())
    guard = f"""-- DEVELOPMENT ONLY: {DEV_REF}. Check the SQL Editor project URL.
-- Requires foundation 001, fixture mode and the expected enabled owner.
-- Does not change deployment mode, owner registration or existing market history.
begin;
do $development_guard$
begin
  if (select data_mode from public.deployment_settings where singleton)
       is distinct from 'fixture' then
    raise exception 'development_fixture_mode_required';
  end if;
  if not exists (select 1 from public.app_members
                 where user_id='{owner_uid}'::uuid and role='owner' and enabled) then
    raise exception 'development_owner_mismatch';
  end if;
  if to_regclass('public.market_series_revisions') is not null then
    raise exception 'market_schema_already_exists_review_migration_state';
  end if;
end
$development_guard$;
"""
    return (
        guard
        + "\n\n".join(blocks)
        + """
commit;
select
  to_regprocedure('public.read_market_series(uuid)') is not null as revision_schema_ready,
  (select data_mode from public.deployment_settings where singleton) as data_mode;
"""
    )


def main() -> None:
    env = local_env(ROOT / ".env.development")
    if env.get("SUPABASE_URL", "").rstrip("/") != f"https://{DEV_REF}.supabase.co":
        raise ValueError("development_project_mismatch")
    output = ROOT / f"data/dev-market-revisions-{DEV_REF}.sql"
    output.parent.mkdir(exist_ok=True)
    output.write_text(render_setup(env.get("APP_OWNER_USER_ID", "")), encoding="utf-8")
    print(f"Prepared: {output}")
    print(
        "Run once in development SQL Editor; expect revision_schema_ready=true, data_mode=fixture."
    )


if __name__ == "__main__":
    main()
