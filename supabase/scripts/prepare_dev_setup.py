"""Build a local SQL Editor handoff from the versioned migration and owner env.

No service key, database password, or other .env value is copied into the SQL.
The generated file is deliberately placed under ignored backend/data/.
"""

import argparse
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "supabase/migrations/202609290001_scan_foundation.sql"
PRODUCTION_REF = "hcjfxbynqzsaidlwvdfx"


def local_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise ValueError("development env file is missing")
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        row = line.strip()
        if not row or row.startswith("#") or "=" not in row:
            continue
        key, value = row.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def prepare(project_ref: str, env_file: Path) -> Path:
    if project_ref == PRODUCTION_REF:
        raise ValueError("production project cannot use development setup")
    if not project_ref.isalnum() or not project_ref.islower():
        raise ValueError("project ref must contain lowercase letters and digits")
    path = (ROOT / env_file).resolve()
    if path != ROOT / ".env.development":
        raise ValueError("use backend/.env.development only")
    env = local_env(path)
    expected_url = f"https://{project_ref}.supabase.co"
    if env.get("SUPABASE_URL", "").rstrip("/") != expected_url:
        raise ValueError("SUPABASE_URL does not match requested project")
    raw_uid = env.get("APP_OWNER_USER_ID", "")
    owner_uid = str(UUID(raw_uid))
    if owner_uid != raw_uid.lower():
        raise ValueError("APP_OWNER_USER_ID is not a canonical UUID")

    migration = MIGRATION.read_text(encoding="utf-8").rstrip()
    if not migration.startswith("-- M2 scan persistence foundation."):
        raise ValueError("unexpected migration source")
    if not migration.endswith("commit;"):
        raise ValueError("migration must end in commit")
    statements = migration[: -len("commit;")].rstrip()
    setup = f"""-- SQL Editor handoff for Supabase project {project_ref}.
-- Generated locally. Do not commit this file or run it against another project.
-- Migration + owner registration execute atomically; a failure rolls both back.
{statements}

do $owner_setup$
begin
  if not exists (select 1 from auth.users
                 where id = '{owner_uid}'::uuid and is_anonymous is false) then
    raise exception 'owner_auth_user_missing_or_anonymous';
  end if;

  insert into public.app_members (user_id, role, enabled)
  values ('{owner_uid}'::uuid, 'owner', true)
  on conflict (user_id) do nothing;

  if not exists (select 1 from public.app_members
                 where user_id = '{owner_uid}'::uuid
                   and role = 'owner' and enabled) then
    raise exception 'owner_membership_not_enabled';
  end if;
end
$owner_setup$;

commit;

select
  exists (select 1 from public.app_members
          where user_id = '{owner_uid}'::uuid and enabled) as owner_ready,
  (select data_mode from public.deployment_settings where singleton) as data_mode;
"""
    output = ROOT / f"data/dev-supabase-setup-{project_ref}.sql"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(setup, encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-ref", required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env.development"))
    args = parser.parse_args()
    try:
        path = prepare(args.project_ref, args.env_file)
    except (ValueError, OSError) as error:
        parser.exit(2, f"Could not prepare SQL: {error}\n")
    print(f"Prepared local SQL Editor file: {path}")
    print("This file contains an owner UUID, not a service key. It is ignored by Git.")


if __name__ == "__main__":
    main()
