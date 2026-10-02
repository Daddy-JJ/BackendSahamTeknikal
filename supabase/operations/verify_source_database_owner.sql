-- READ ONLY. Independently confirm project hcjfxbynqzsaidlwvdfx in Dashboard.
-- Role names and privilege booleans only; never outputs passwords/Auth rows.
begin read only;
select pg_get_userbyid(d.datdba) as database_owner,
       pg_get_userbyid(n.nspowner) as public_schema_owner,
       has_schema_privilege('postgres','public','CREATE') as postgres_can_create_public,
       has_database_privilege('postgres',current_database(),'CREATE')
         as postgres_can_create_database_objects
from pg_database d cross join pg_namespace n
where d.datname=current_database() and n.nspname='public';
rollback;
