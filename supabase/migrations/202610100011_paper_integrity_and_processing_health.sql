-- Forward-only integrity, canonical processing health, and auditable reporting.
-- Existing model/configuration, actual ledger, legacy trades and event payloads are preserved.
begin;

-- Duplicate economics require operator reconciliation; never delete historical records here.
create unique index paper_economic_identity_v1 on public.paper_trades
  (owner_id,data_mode,model_version,signal_id,experiment_id)
  where model_version='close-signal-risk-v1';

create table public.paper_calendar_v1 (
  singleton boolean primary key default true check(singleton),
  config_sha256_lf text not null check(config_sha256_lf ~ '^[0-9a-f]{64}$'),
  payload jsonb not null
);
alter table public.paper_calendar_v1 enable row level security;
revoke all on public.paper_calendar_v1 from public,anon,authenticated,service_role;
grant select on public.paper_calendar_v1 to authenticated,service_role;
create policy owner_read on public.paper_calendar_v1 for select to authenticated
  using ((select public.is_app_owner()));
create trigger immutable_calendar before update or delete on public.paper_calendar_v1
  for each row execute function public.reject_immutable_mutation();
insert into public.paper_calendar_v1(config_sha256_lf,payload) values('54fc8efbfc53a43bcb907a2a799ff098688fd23e9700f7d3c762214a5390895b',$calendar${"data_mode":"live","version":"idx-calendar-known-sources-20261002-v2-explicit-closures","source":"https://www.idxcarbon.co.id/document/share/158/0a901391-a0ad-4ca5-930e-2788cb7eb27f","published_date":"2025-09-23","source_checksum":"c1666b1d02d55cd9e69b11cf059871468c501fab151b2a0d09eb64a6b7e090fc","checksum_scope":"canonical source_manifest transcription, not downloaded PDF bytes","source_manifest":{"calendar_references":[{"year":2024,"reference":"config/reference/idx-holidays-2024-source.json","reference_sha256":"df71e048def4626a7d41cfb2fa9094df257af8d25f04cbde9b2152233d70e67f"},{"year":2025,"reference":"config/reference/idx-holidays-2025-source.json","reference_sha256":"f69edd28a42e99e385b0825bec36ccebf95aa02ce7cf8d4b3959d79469410174"},{"year":2026,"reference":"config/reference/idx-holidays-2026-source.json","reference_sha256":"174a4c2229276e189727b0e63006d75a62b07c2452ec6828490071327084515c"}],"timing_source":"https://www.idx.id/en/products-services/trading-hours-and-mechanism/","timing_transcription":{"regular_earliest_matching":"08:58:00","regular_post_close_end":"16:15:00","applies_from":"2026-10-02","historical_hours_claimed":false},"reference_checksum_scope":"canonical JSON transcription, not source file/PDF bytes","closed_session_policy":"explicit published holidays only; no inferred weekend/session closure"},"historical_days":["2024-01-02","2024-01-03","2024-01-04","2024-01-05","2024-01-08","2024-01-09","2024-01-10","2024-01-11","2024-01-12","2024-01-15","2024-01-16","2024-01-17","2024-01-18","2024-01-19","2024-01-22","2024-01-23","2024-01-24","2024-01-25","2024-01-26","2024-01-29","2024-01-30","2024-01-31","2024-02-01","2024-02-02","2024-02-05","2024-02-06","2024-02-07","2024-02-12","2024-02-13","2024-02-15","2024-02-16","2024-02-19","2024-02-20","2024-02-21","2024-02-22","2024-02-23","2024-02-26","2024-02-27","2024-02-28","2024-02-29","2024-03-01","2024-03-04","2024-03-05","2024-03-06","2024-03-07","2024-03-08","2024-03-13","2024-03-14","2024-03-15","2024-03-18","2024-03-19","2024-03-20","2024-03-21","2024-03-22","2024-03-25","2024-03-26","2024-03-27","2024-03-28","2024-04-01","2024-04-02","2024-04-03","2024-04-04","2024-04-05","2024-04-16","2024-04-17","2024-04-18","2024-04-19","2024-04-22","2024-04-23","2024-04-24","2024-04-25","2024-04-26","2024-04-29","2024-04-30","2024-05-02","2024-05-03","2024-05-06","2024-05-07","2024-05-08","2024-05-13","2024-05-14","2024-05-15","2024-05-16","2024-05-17","2024-05-20","2024-05-21","2024-05-22","2024-05-27","2024-05-28","2024-05-29","2024-05-30","2024-05-31","2024-06-03","2024-06-04","2024-06-05","2024-06-06","2024-06-07","2024-06-10","2024-06-11","2024-06-12","2024-06-13","2024-06-14","2024-06-19","2024-06-20","2024-06-21","2024-06-24","2024-06-25","2024-06-26","2024-06-27","2024-06-28","2024-07-01","2024-07-02","2024-07-03","2024-07-04","2024-07-05","2024-07-08","2024-07-09","2024-07-10","2024-07-11","2024-07-12","2024-07-15","2024-07-16","2024-07-17","2024-07-18","2024-07-19","2024-07-22","2024-07-23","2024-07-24","2024-07-25","2024-07-26","2024-07-29","2024-07-30","2024-07-31","2024-08-01","2024-08-02","2024-08-05","2024-08-06","2024-08-07","2024-08-08","2024-08-09","2024-08-12","2024-08-13","2024-08-14","2024-08-15","2024-08-16","2024-08-19","2024-08-20","2024-08-21","2024-08-22","2024-08-23","2024-08-26","2024-08-27","2024-08-28","2024-08-29","2024-08-30","2024-09-02","2024-09-03","2024-09-04","2024-09-05","2024-09-06","2024-09-09","2024-09-10","2024-09-11","2024-09-12","2024-09-13","2024-09-17","2024-09-18","2024-09-19","2024-09-20","2024-09-23","2024-09-24","2024-09-25","2024-09-26","2024-09-27","2024-09-30","2024-10-01","2024-10-02","2024-10-03","2024-10-04","2024-10-07","2024-10-08","2024-10-09","2024-10-10","2024-10-11","2024-10-14","2024-10-15","2024-10-16","2024-10-17","2024-10-18","2024-10-21","2024-10-22","2024-10-23","2024-10-24","2024-10-25","2024-10-28","2024-10-29","2024-10-30","2024-10-31","2024-11-01","2024-11-04","2024-11-05","2024-11-06","2024-11-07","2024-11-08","2024-11-11","2024-11-12","2024-11-13","2024-11-14","2024-11-15","2024-11-18","2024-11-19","2024-11-20","2024-11-21","2024-11-22","2024-11-25","2024-11-26","2024-11-28","2024-11-29","2024-12-02","2024-12-03","2024-12-04","2024-12-05","2024-12-06","2024-12-09","2024-12-10","2024-12-11","2024-12-12","2024-12-13","2024-12-16","2024-12-17","2024-12-18","2024-12-19","2024-12-20","2024-12-23","2024-12-24","2024-12-27","2024-12-30","2025-01-02","2025-01-03","2025-01-06","2025-01-07","2025-01-08","2025-01-09","2025-01-10","2025-01-13","2025-01-14","2025-01-15","2025-01-16","2025-01-17","2025-01-20","2025-01-21","2025-01-22","2025-01-23","2025-01-24","2025-01-30","2025-01-31","2025-02-03","2025-02-04","2025-02-05","2025-02-06","2025-02-07","2025-02-10","2025-02-11","2025-02-12","2025-02-13","2025-02-14","2025-02-17","2025-02-18","2025-02-19","2025-02-20","2025-02-21","2025-02-24","2025-02-25","2025-02-26","2025-02-27","2025-02-28","2025-03-03","2025-03-04","2025-03-05","2025-03-06","2025-03-07","2025-03-10","2025-03-11","2025-03-12","2025-03-13","2025-03-14","2025-03-17","2025-03-18","2025-03-19","2025-03-20","2025-03-21","2025-03-24","2025-03-25","2025-03-26","2025-03-27","2025-04-08","2025-04-09","2025-04-10","2025-04-11","2025-04-14","2025-04-15","2025-04-16","2025-04-17","2025-04-21","2025-04-22","2025-04-23","2025-04-24","2025-04-25","2025-04-28","2025-04-29","2025-04-30","2025-05-02","2025-05-05","2025-05-06","2025-05-07","2025-05-08","2025-05-09","2025-05-14","2025-05-15","2025-05-16","2025-05-19","2025-05-20","2025-05-21","2025-05-22","2025-05-23","2025-05-26","2025-05-27","2025-05-28","2025-06-02","2025-06-03","2025-06-04","2025-06-05","2025-06-10","2025-06-11","2025-06-12","2025-06-13","2025-06-16","2025-06-17","2025-06-18","2025-06-19","2025-06-20","2025-06-23","2025-06-24","2025-06-25","2025-06-26","2025-06-30","2025-07-01","2025-07-02","2025-07-03","2025-07-04","2025-07-07","2025-07-08","2025-07-09","2025-07-10","2025-07-11","2025-07-14","2025-07-15","2025-07-16","2025-07-17","2025-07-18","2025-07-21","2025-07-22","2025-07-23","2025-07-24","2025-07-25","2025-07-28","2025-07-29","2025-07-30","2025-07-31","2025-08-01","2025-08-04","2025-08-05","2025-08-06","2025-08-07","2025-08-08","2025-08-11","2025-08-12","2025-08-13","2025-08-14","2025-08-15","2025-08-19","2025-08-20","2025-08-21","2025-08-22","2025-08-25","2025-08-26","2025-08-27","2025-08-28","2025-08-29","2025-09-01","2025-09-02","2025-09-03","2025-09-04","2025-09-08","2025-09-09","2025-09-10","2025-09-11","2025-09-12","2025-09-15","2025-09-16","2025-09-17","2025-09-18","2025-09-19","2025-09-22","2025-09-23","2025-09-24","2025-09-25","2025-09-26","2025-09-29","2025-09-30","2025-10-01","2025-10-02","2025-10-03","2025-10-06","2025-10-07","2025-10-08","2025-10-09","2025-10-10","2025-10-13","2025-10-14","2025-10-15","2025-10-16","2025-10-17","2025-10-20","2025-10-21","2025-10-22","2025-10-23","2025-10-24","2025-10-27","2025-10-28","2025-10-29","2025-10-30","2025-10-31","2025-11-03","2025-11-04","2025-11-05","2025-11-06","2025-11-07","2025-11-10","2025-11-11","2025-11-12","2025-11-13","2025-11-14","2025-11-17","2025-11-18","2025-11-19","2025-11-20","2025-11-21","2025-11-24","2025-11-25","2025-11-26","2025-11-27","2025-11-28","2025-12-01","2025-12-02","2025-12-03","2025-12-04","2025-12-05","2025-12-08","2025-12-09","2025-12-10","2025-12-11","2025-12-12","2025-12-15","2025-12-16","2025-12-17","2025-12-18","2025-12-19","2025-12-22","2025-12-23","2025-12-24","2025-12-29","2025-12-30","2026-01-02","2026-01-05","2026-01-06","2026-01-07","2026-01-08","2026-01-09","2026-01-12","2026-01-13","2026-01-14","2026-01-15","2026-01-19","2026-01-20","2026-01-21","2026-01-22","2026-01-23","2026-01-26","2026-01-27","2026-01-28","2026-01-29","2026-01-30","2026-02-02","2026-02-03","2026-02-04","2026-02-05","2026-02-06","2026-02-09","2026-02-10","2026-02-11","2026-02-12","2026-02-13","2026-02-18","2026-02-19","2026-02-20","2026-02-23","2026-02-24","2026-02-25","2026-02-26","2026-02-27","2026-03-02","2026-03-03","2026-03-04","2026-03-05","2026-03-06","2026-03-09","2026-03-10","2026-03-11","2026-03-12","2026-03-13","2026-03-16","2026-03-17","2026-03-25","2026-03-26","2026-03-27","2026-03-30","2026-03-31","2026-04-01","2026-04-02","2026-04-06","2026-04-07","2026-04-08","2026-04-09","2026-04-10","2026-04-13","2026-04-14","2026-04-15","2026-04-16","2026-04-17","2026-04-20","2026-04-21","2026-04-22","2026-04-23","2026-04-24","2026-04-27","2026-04-28","2026-04-29","2026-04-30","2026-05-04","2026-05-05","2026-05-06","2026-05-07","2026-05-08","2026-05-11","2026-05-12","2026-05-13","2026-05-18","2026-05-19","2026-05-20","2026-05-21","2026-05-22","2026-05-25","2026-05-26","2026-05-29","2026-06-02","2026-06-03","2026-06-04","2026-06-05","2026-06-08","2026-06-09","2026-06-10","2026-06-11","2026-06-12","2026-06-15","2026-06-17","2026-06-18","2026-06-19","2026-06-22","2026-06-23","2026-06-24","2026-06-25","2026-06-26","2026-06-29","2026-06-30","2026-07-01","2026-07-02","2026-07-03","2026-07-06","2026-07-07","2026-07-08","2026-07-09","2026-07-10","2026-07-13","2026-07-14","2026-07-15","2026-07-16","2026-07-17","2026-07-20","2026-07-21","2026-07-22","2026-07-23","2026-07-24","2026-07-27","2026-07-28","2026-07-29","2026-07-30","2026-07-31","2026-08-03","2026-08-04","2026-08-05","2026-08-06","2026-08-07","2026-08-10","2026-08-11","2026-08-12","2026-08-13","2026-08-14","2026-08-18","2026-08-19","2026-08-20","2026-08-21","2026-08-24","2026-08-26","2026-08-27","2026-08-28","2026-08-31","2026-09-01","2026-09-02","2026-09-03","2026-09-04","2026-09-07","2026-09-08","2026-09-09","2026-09-10","2026-09-11","2026-09-14","2026-09-15","2026-09-16","2026-09-17","2026-09-18","2026-09-21","2026-09-22","2026-09-23","2026-09-24","2026-09-25","2026-09-28","2026-09-29","2026-09-30","2026-10-01"],"sessions":[{"day":"2026-10-02","opens_at":"2026-10-02T08:58:00+07:00","closes_at":"2026-10-02T16:15:00+07:00"},{"day":"2026-10-05","opens_at":"2026-10-05T08:58:00+07:00","closes_at":"2026-10-05T16:15:00+07:00"},{"day":"2026-10-06","opens_at":"2026-10-06T08:58:00+07:00","closes_at":"2026-10-06T16:15:00+07:00"},{"day":"2026-10-07","opens_at":"2026-10-07T08:58:00+07:00","closes_at":"2026-10-07T16:15:00+07:00"},{"day":"2026-10-08","opens_at":"2026-10-08T08:58:00+07:00","closes_at":"2026-10-08T16:15:00+07:00"},{"day":"2026-10-09","opens_at":"2026-10-09T08:58:00+07:00","closes_at":"2026-10-09T16:15:00+07:00"},{"day":"2026-10-12","opens_at":"2026-10-12T08:58:00+07:00","closes_at":"2026-10-12T16:15:00+07:00"},{"day":"2026-10-13","opens_at":"2026-10-13T08:58:00+07:00","closes_at":"2026-10-13T16:15:00+07:00"},{"day":"2026-10-14","opens_at":"2026-10-14T08:58:00+07:00","closes_at":"2026-10-14T16:15:00+07:00"},{"day":"2026-10-15","opens_at":"2026-10-15T08:58:00+07:00","closes_at":"2026-10-15T16:15:00+07:00"},{"day":"2026-10-16","opens_at":"2026-10-16T08:58:00+07:00","closes_at":"2026-10-16T16:15:00+07:00"},{"day":"2026-10-19","opens_at":"2026-10-19T08:58:00+07:00","closes_at":"2026-10-19T16:15:00+07:00"},{"day":"2026-10-20","opens_at":"2026-10-20T08:58:00+07:00","closes_at":"2026-10-20T16:15:00+07:00"},{"day":"2026-10-21","opens_at":"2026-10-21T08:58:00+07:00","closes_at":"2026-10-21T16:15:00+07:00"},{"day":"2026-10-22","opens_at":"2026-10-22T08:58:00+07:00","closes_at":"2026-10-22T16:15:00+07:00"},{"day":"2026-10-23","opens_at":"2026-10-23T08:58:00+07:00","closes_at":"2026-10-23T16:15:00+07:00"},{"day":"2026-10-26","opens_at":"2026-10-26T08:58:00+07:00","closes_at":"2026-10-26T16:15:00+07:00"},{"day":"2026-10-27","opens_at":"2026-10-27T08:58:00+07:00","closes_at":"2026-10-27T16:15:00+07:00"},{"day":"2026-10-28","opens_at":"2026-10-28T08:58:00+07:00","closes_at":"2026-10-28T16:15:00+07:00"},{"day":"2026-10-29","opens_at":"2026-10-29T08:58:00+07:00","closes_at":"2026-10-29T16:15:00+07:00"},{"day":"2026-10-30","opens_at":"2026-10-30T08:58:00+07:00","closes_at":"2026-10-30T16:15:00+07:00"},{"day":"2026-11-02","opens_at":"2026-11-02T08:58:00+07:00","closes_at":"2026-11-02T16:15:00+07:00"},{"day":"2026-11-03","opens_at":"2026-11-03T08:58:00+07:00","closes_at":"2026-11-03T16:15:00+07:00"},{"day":"2026-11-04","opens_at":"2026-11-04T08:58:00+07:00","closes_at":"2026-11-04T16:15:00+07:00"},{"day":"2026-11-05","opens_at":"2026-11-05T08:58:00+07:00","closes_at":"2026-11-05T16:15:00+07:00"},{"day":"2026-11-06","opens_at":"2026-11-06T08:58:00+07:00","closes_at":"2026-11-06T16:15:00+07:00"},{"day":"2026-11-09","opens_at":"2026-11-09T08:58:00+07:00","closes_at":"2026-11-09T16:15:00+07:00"},{"day":"2026-11-10","opens_at":"2026-11-10T08:58:00+07:00","closes_at":"2026-11-10T16:15:00+07:00"},{"day":"2026-11-11","opens_at":"2026-11-11T08:58:00+07:00","closes_at":"2026-11-11T16:15:00+07:00"},{"day":"2026-11-12","opens_at":"2026-11-12T08:58:00+07:00","closes_at":"2026-11-12T16:15:00+07:00"},{"day":"2026-11-13","opens_at":"2026-11-13T08:58:00+07:00","closes_at":"2026-11-13T16:15:00+07:00"},{"day":"2026-11-16","opens_at":"2026-11-16T08:58:00+07:00","closes_at":"2026-11-16T16:15:00+07:00"},{"day":"2026-11-17","opens_at":"2026-11-17T08:58:00+07:00","closes_at":"2026-11-17T16:15:00+07:00"},{"day":"2026-11-18","opens_at":"2026-11-18T08:58:00+07:00","closes_at":"2026-11-18T16:15:00+07:00"},{"day":"2026-11-19","opens_at":"2026-11-19T08:58:00+07:00","closes_at":"2026-11-19T16:15:00+07:00"},{"day":"2026-11-20","opens_at":"2026-11-20T08:58:00+07:00","closes_at":"2026-11-20T16:15:00+07:00"},{"day":"2026-11-23","opens_at":"2026-11-23T08:58:00+07:00","closes_at":"2026-11-23T16:15:00+07:00"},{"day":"2026-11-24","opens_at":"2026-11-24T08:58:00+07:00","closes_at":"2026-11-24T16:15:00+07:00"},{"day":"2026-11-25","opens_at":"2026-11-25T08:58:00+07:00","closes_at":"2026-11-25T16:15:00+07:00"},{"day":"2026-11-26","opens_at":"2026-11-26T08:58:00+07:00","closes_at":"2026-11-26T16:15:00+07:00"},{"day":"2026-11-27","opens_at":"2026-11-27T08:58:00+07:00","closes_at":"2026-11-27T16:15:00+07:00"},{"day":"2026-11-30","opens_at":"2026-11-30T08:58:00+07:00","closes_at":"2026-11-30T16:15:00+07:00"},{"day":"2026-12-01","opens_at":"2026-12-01T08:58:00+07:00","closes_at":"2026-12-01T16:15:00+07:00"},{"day":"2026-12-02","opens_at":"2026-12-02T08:58:00+07:00","closes_at":"2026-12-02T16:15:00+07:00"},{"day":"2026-12-03","opens_at":"2026-12-03T08:58:00+07:00","closes_at":"2026-12-03T16:15:00+07:00"},{"day":"2026-12-04","opens_at":"2026-12-04T08:58:00+07:00","closes_at":"2026-12-04T16:15:00+07:00"},{"day":"2026-12-07","opens_at":"2026-12-07T08:58:00+07:00","closes_at":"2026-12-07T16:15:00+07:00"},{"day":"2026-12-08","opens_at":"2026-12-08T08:58:00+07:00","closes_at":"2026-12-08T16:15:00+07:00"},{"day":"2026-12-09","opens_at":"2026-12-09T08:58:00+07:00","closes_at":"2026-12-09T16:15:00+07:00"},{"day":"2026-12-10","opens_at":"2026-12-10T08:58:00+07:00","closes_at":"2026-12-10T16:15:00+07:00"},{"day":"2026-12-11","opens_at":"2026-12-11T08:58:00+07:00","closes_at":"2026-12-11T16:15:00+07:00"},{"day":"2026-12-14","opens_at":"2026-12-14T08:58:00+07:00","closes_at":"2026-12-14T16:15:00+07:00"},{"day":"2026-12-15","opens_at":"2026-12-15T08:58:00+07:00","closes_at":"2026-12-15T16:15:00+07:00"},{"day":"2026-12-16","opens_at":"2026-12-16T08:58:00+07:00","closes_at":"2026-12-16T16:15:00+07:00"},{"day":"2026-12-17","opens_at":"2026-12-17T08:58:00+07:00","closes_at":"2026-12-17T16:15:00+07:00"},{"day":"2026-12-18","opens_at":"2026-12-18T08:58:00+07:00","closes_at":"2026-12-18T16:15:00+07:00"},{"day":"2026-12-21","opens_at":"2026-12-21T08:58:00+07:00","closes_at":"2026-12-21T16:15:00+07:00"},{"day":"2026-12-22","opens_at":"2026-12-22T08:58:00+07:00","closes_at":"2026-12-22T16:15:00+07:00"},{"day":"2026-12-23","opens_at":"2026-12-23T08:58:00+07:00","closes_at":"2026-12-23T16:15:00+07:00"},{"day":"2026-12-28","opens_at":"2026-12-28T08:58:00+07:00","closes_at":"2026-12-28T16:15:00+07:00"},{"day":"2026-12-29","opens_at":"2026-12-29T08:58:00+07:00","closes_at":"2026-12-29T16:15:00+07:00"},{"day":"2026-12-30","opens_at":"2026-12-30T08:58:00+07:00","closes_at":"2026-12-30T16:15:00+07:00"}],"timing_semantics":"Earliest regular-market price matching is a publication deadline, not a guaranteed per-security fill time; actual next-open price remains unknown. Historical warm-up dates have no inferred times.","reviewed_at_utc":"2026-10-02T14:32:38.448597+00:00","limitations":["Known official calendar announcements reconciled; review newly published exchange amendments before each live run.","Calendar ends 2026; 2027 is blocked until official source is added.","No historical execution/backtest timing before 2026-10-02 is supplied."],"closed_days":["2024-01-01","2024-02-08","2024-02-09","2024-02-14","2024-03-11","2024-03-12","2024-03-29","2024-04-08","2024-04-09","2024-04-10","2024-04-11","2024-04-12","2024-04-15","2024-05-01","2024-05-09","2024-05-10","2024-05-23","2024-05-24","2024-06-17","2024-06-18","2024-09-16","2024-11-27","2024-12-25","2024-12-26","2024-12-31","2025-01-01","2025-01-27","2025-01-28","2025-01-29","2025-03-28","2025-03-31","2025-04-01","2025-04-02","2025-04-03","2025-04-04","2025-04-07","2025-04-18","2025-05-01","2025-05-12","2025-05-13","2025-05-29","2025-05-30","2025-06-06","2025-06-09","2025-06-27","2025-08-18","2025-09-05","2025-12-25","2025-12-26","2025-12-31","2026-01-01","2026-01-16","2026-02-16","2026-02-17","2026-03-18","2026-03-19","2026-03-20","2026-03-23","2026-03-24","2026-04-03","2026-05-01","2026-05-14","2026-05-15","2026-05-27","2026-05-28","2026-06-01","2026-06-16","2026-08-17","2026-08-25","2026-12-24","2026-12-25","2026-12-31"]}$calendar$::jsonb);

create function public.paper_calendar_days_v1() returns table(day date,opens_at timestamptz,closes_at timestamptz)
language sql stable security definer set search_path='' as $$
  select (x->>'day')::date,(x->>'opens_at')::timestamptz,(x->>'closes_at')::timestamptz
    from public.paper_calendar_v1 c cross join lateral jsonb_array_elements(c.payload->'sessions') x
  union all
  select x::date,null::timestamptz,null::timestamptz
    from public.paper_calendar_v1 c cross join lateral jsonb_array_elements_text(c.payload->'historical_days') x;
$$;
revoke all on function public.paper_calendar_days_v1() from public,anon,authenticated,service_role;

create table public.paper_job_events_v1 (
  owner_id uuid not null references auth.users(id),data_mode text not null check(data_mode in ('live','fixture')),
  job_id text not null,phase text not null,status text not null,session_date date,
  failure_code text,context jsonb not null,recorded_at timestamptz not null default now(),
  event_sequence bigint generated always as identity,
  primary key(owner_id,data_mode,job_id,phase,status)
);
alter table public.paper_job_events_v1 enable row level security;
revoke all on public.paper_job_events_v1 from public,anon,authenticated,service_role;
grant select on public.paper_job_events_v1 to authenticated,service_role;
create policy owner_read on public.paper_job_events_v1 for select to authenticated
  using ((select public.is_app_owner()) and owner_id=(select auth.uid()));
create trigger immutable_job before update or delete on public.paper_job_events_v1
  for each row execute function public.reject_immutable_mutation();

create function public.record_paper_job_v1(p_owner_id uuid,p_data_mode text,p_job_id text,p_phase text,p_status text,
  p_session date,p_failure_code text default null,p_context jsonb default '{}'::jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare saved public.paper_job_events_v1; kv record; replay boolean:=false;
begin
  perform public.assert_paper_owner_v1(p_owner_id,p_data_mode);
  if p_job_id is null or p_job_id !~ '^[A-Za-z0-9:_./-]{1,160}$'
    or p_phase is null or p_phase not in ('scanner','publication','paper','job')
    or p_status is null or p_status not in ('running','succeeded','failed','skipped')
    or (p_failure_code is not null and (p_failure_code !~ '^[a-z0-9_:-]{1,100}$' or p_status<>'failed'))
    or jsonb_typeof(p_context) is distinct from 'object' then
    raise exception 'invalid_paper_job_event' using errcode='22023';
  end if;
  for kv in select * from jsonb_each(p_context) loop
    if kv.key not in ('workflow','run_id','event','schedule','observed_at','source_sha','calendar_version',
        'elapsed_ms','revision','pending','open','closed','coverage_valid','coverage_total') then
      raise exception 'invalid_paper_job_context' using errcode='22023';
    end if;
    if kv.key in ('elapsed_ms','revision','pending','open','closed','coverage_valid','coverage_total') then
      if jsonb_typeof(kv.value)<>'number' or (kv.value#>>'{}')::numeric<0 or (kv.value#>>'{}')::numeric>1000000000000 then
        raise exception 'invalid_paper_job_context' using errcode='22023'; end if;
    elsif kv.key='observed_at' then
      if jsonb_typeof(kv.value)<>'string' or (kv.value#>>'{}') !~ '^\d{4}-\d{2}-\d{2}T.*(Z|[+-]\d{2}:\d{2})$' then
        raise exception 'invalid_paper_job_context' using errcode='22023'; end if;
      perform (kv.value#>>'{}')::timestamptz;
    elsif kv.key='workflow' then
      if jsonb_typeof(kv.value)<>'string' or (kv.value#>>'{}') !~ '^[A-Za-z0-9_. /&()-]{1,160}$'
        or lower(kv.value#>>'{}') ~ '(bearer|password|secret|service_role|eyj)' then
        raise exception 'invalid_paper_job_context' using errcode='22023'; end if;
    elsif kv.key='schedule' then
      if jsonb_typeof(kv.value)<>'string' or (kv.value#>>'{}') !~ '^[0-9 */,-]{1,80}$' then
        raise exception 'invalid_paper_job_context' using errcode='22023'; end if;
    else
      if jsonb_typeof(kv.value)<>'string' or (kv.value#>>'{}') !~ '^[A-Za-z0-9_.:/-]{1,160}$'
        or lower(kv.value#>>'{}') ~ '(bearer|password|secret|service_role|eyj)' then
        raise exception 'invalid_paper_job_context' using errcode='22023'; end if;
    end if;
  end loop;
  insert into public.paper_job_events_v1(owner_id,data_mode,job_id,phase,status,session_date,failure_code,context)
    values(p_owner_id,p_data_mode,p_job_id,p_phase,p_status,p_session,p_failure_code,p_context)
    on conflict do nothing returning * into saved;
  if not found then
    replay:=true;
    select * into strict saved from public.paper_job_events_v1 where owner_id=p_owner_id and data_mode=p_data_mode
      and job_id=p_job_id and phase=p_phase and status=p_status;
    if saved.session_date is distinct from p_session or saved.failure_code is distinct from p_failure_code or saved.context is distinct from p_context then
      raise exception 'paper_job_idempotency_conflict' using errcode='PT409'; end if;
  end if;
  return jsonb_build_object('contract_version',1,'job_id',saved.job_id,'phase',saved.phase,'status',saved.status,
    'recorded_at',saved.recorded_at,'replayed',replay);
end $$;
revoke all on function public.record_paper_job_v1(uuid,text,text,text,text,date,text,jsonb) from public,anon,authenticated,service_role;
grant execute on function public.record_paper_job_v1(uuid,text,text,text,text,date,text,jsonb) to service_role;

create function public.paper_processing_health_v1(p_owner uuid,p_mode text,p_at timestamptz)
returns jsonb language plpgsql stable security definer set search_path='' as $$
declare expected date; processed date; first_day date; last_known date; cal jsonb; job public.paper_job_events_v1;
  due bigint; overdue boolean; health text; hold_count bigint; held_since date; next_eligible timestamptz;
begin
  select payload into strict cal from public.paper_calendar_v1 where singleton;
  select min(day),max(day) filter(where closes_at<=p_at) into first_day,expected
    from public.paper_calendar_days_v1() where closes_at is not null;
  select greatest((select max(day) from public.paper_calendar_days_v1()),
    (select max(x::date) from jsonb_array_elements_text(cal->'closed_days') x)) into last_known;
  select last_session into processed from public.paper_models where owner_id=p_owner and data_mode=p_mode and model_version='close-signal-risk-v1';
  select * into job from public.paper_job_events_v1 where owner_id=p_owner and data_mode=p_mode
    order by recorded_at desc,event_sequence desc limit 1;
  select count(*) into due from public.paper_trades t join public.paper_calendar_days_v1() c on c.day=t.entry_session
    where t.owner_id=p_owner and t.data_mode=p_mode and t.model_version='close-signal-risk-v1'
      and t.state in ('pending_entry','data_hold') and t.details->>'entry' is null and c.opens_at<=p_at;
  with held as (
    select case when t.details->>'entry' is null then t.entry_session
      else (select min(day) from public.paper_calendar_days_v1() where day>(t.details->>'last_session')::date) end as held_day
    from public.paper_trades t where t.owner_id=p_owner and t.data_mode=p_mode and t.model_version='close-signal-risk-v1' and t.state='data_hold'
    union all
    select case when e.payload->>'last_session' is null then (e.payload->>'entry_session')::date
      else (select min(day) from public.paper_calendar_days_v1() where day>(e.payload->>'last_session')::date) end
    from public.signal_evaluations e where e.owner_id=p_owner and e.data_mode=p_mode and e.model_version='close-signal-risk-v1'
      and exists(select 1 from jsonb_each_text(e.payload->'results') r where r.value='data_hold')
  ) select count(*),min(held_day) into hold_count,held_since from held;
  overdue:=expected is not null and (processed is null or processed<expected or coalesce(held_since<=expected,false));
  health:=case when (p_at at time zone 'Asia/Jakarta')::date<first_day
      or (p_at at time zone 'Asia/Jakarta')::date>last_known then 'calendar_unknown'
    when job.status='failed' and (overdue or job.session_date>=expected) then 'failed'
    when job.status='running' and job.recorded_at>p_at-interval '30 minutes' then 'running'
    when hold_count>0 then 'data_hold'
    when overdue then 'overdue' when processed is null then 'missing' else 'ready' end;
  if health='calendar_unknown' then expected:=null;overdue:=false;end if;
  if health<>'calendar_unknown' then
    select min(closes_at) into next_eligible from public.paper_calendar_days_v1()
      where closes_at is not null and (processed is null or day>processed or day=held_since);
  end if;
  return jsonb_build_object('contract_version',1,'data_mode',p_mode,'model_version','close-signal-risk-v1',
    'expected_session',expected,'processed_session',processed,'status',health,'overdue',overdue,
    'pending_entry_due',due,'data_hold_count',hold_count,'held_since_session',held_since,'calendar_version',cal->>'version','checked_at',p_at,
    'latest_job_status',job.status,'latest_job_phase',job.phase,'failure_code',job.failure_code,'last_attempt_at',job.recorded_at,
    'next_eligible_processing_at',next_eligible);
end $$;
revoke all on function public.paper_processing_health_v1(uuid,text,timestamptz) from public,anon,authenticated,service_role;
create function public.read_paper_processing_health_v1() returns jsonb
language plpgsql stable security definer set search_path='' as $$
declare owner uuid:=auth.uid(); dm text; begin
  if owner is null or not public.is_app_owner() then raise exception 'owner_required' using errcode='42501'; end if;
  select data_mode into strict dm from public.deployment_settings where singleton;
  return public.paper_processing_health_v1(owner,dm,now());
end $$;
revoke all on function public.read_paper_processing_health_v1() from public,anon,authenticated,service_role;
grant execute on function public.read_paper_processing_health_v1() to authenticated;

-- Keep the already-tested atomic CAS/request/event/ledger implementation private.
alter function public.commit_paper_session_v1(uuid,text,bigint,text,date,jsonb,jsonb,uuid) rename to commit_paper_session_before011;
revoke all on function public.commit_paper_session_before011(uuid,text,bigint,text,date,jsonb,jsonb,uuid) from public,anon,authenticated,service_role;
-- The new exact-budget policy checks unrounded price risk plus cent-rounded fees.
-- The legacy branch retains the original cent-rounded total budget acceptance.
do $$ declare body text; old_check text; new_check text; begin
  select pg_get_functiondef('public.commit_paper_session_before011(uuid,text,bigint,text,date,jsonb,jsonb,uuid)'::regprocedure) into body;
  old_check:='while expected_lots>0 and round(expected_lots*100*(entry-stop)+round(expected_lots*100*entry*0.0015,2)+round(expected_lots*100*stop*0.0025,2),2)>1000000 loop';
  new_check:='while expected_lots>0 and (case when t->>''sizing_policy_version''=''exact_risk_fees_v2'' then expected_lots*100*(entry-stop)+round(expected_lots*100*entry*0.0015,2)+round(expected_lots*100*stop*0.0025,2) else round(expected_lots*100*(entry-stop)+round(expected_lots*100*entry*0.0015,2)+round(expected_lots*100*stop*0.0025,2),2) end)>1000000 loop';
  if position(old_check in body)=0 then raise exception 'unexpected_previous_sizing_contract'; end if;
  execute replace(body,old_check,new_check);
end $$;
create function public.valid_paper_untradable_evidence_v1(p jsonb,p_ticker text,p_mode text,p_day date,p_observed timestamptz)
returns boolean language plpgsql immutable set search_path='' as $$
begin
  if jsonb_typeof(p) is distinct from 'object' or not p ?& array['version','ticker','session','data_mode',
      'source_url','document_sha256','verified_at','reason','digest']
    or exists(select 1 from jsonb_object_keys(p) k where k not in ('version','ticker','session','data_mode',
      'source_url','document_sha256','verified_at','reason','digest','observed_at')) then return false; end if;
  return coalesce(p->>'version'='verified_untradable_v1' and p->>'ticker'=p_ticker and p->>'data_mode'=p_mode
    and (p->>'session')::date=p_day and p->>'reason'='official_whole_session_suspension'
    and p->>'document_sha256' ~ '^[a-f0-9]{64}$' and p->>'digest' ~ '^[a-f0-9]{64}$'
    and p->>'verified_at' ~ '^\d{4}-\d{2}-\d{2}T.*(Z|[+-]\d{2}:\d{2})$'
    and (p->>'verified_at')::timestamptz<=p_observed
    and ((p->>'source_url' ~* '^https://([a-z0-9-]+\.)*idx\.co\.id/' )
      or (p_mode='fixture' and p->>'source_url' ~ '^synthetic://'))
    and (not p ? 'observed_at' or ((p->>'observed_at')::timestamptz=p_observed
      and p->>'observed_at' ~ '^\d{4}-\d{2}-\d{2}T.*(Z|[+-]\d{2}:\d{2})$')),false);
exception when invalid_text_representation or datetime_field_overflow or invalid_datetime_format then return false;
end $$;
revoke all on function public.valid_paper_untradable_evidence_v1(jsonb,text,text,date,timestamptz) from public,anon,authenticated,service_role;

create function public.commit_paper_session_v1(p_owner_id uuid,p_data_mode text,p_expected_revision bigint,p_request_id text,
  p_session date,p_book jsonb,p_evaluations jsonb,p_source_run_id uuid default null)
returns jsonb language plpgsql security definer set search_path='' as $$
declare m public.paper_models; item record; e jsonb; old_e jsonb; sig public.signals; v record; n integer;
  old_count integer; old_len integer; proof_len integer; old_proof_len integer; expected_count integer; last_day date; previous_day date; close_at timestamptz;
  raw_loss numeric; lots bigint; qty bigint; entry numeric; stop numeric; policy text; old_t jsonb; proof jsonb;
begin
  perform public.assert_paper_owner_v1(p_owner_id,p_data_mode);
  select * into strict m from public.paper_models where owner_id=p_owner_id and data_mode=p_data_mode and model_version='close-signal-risk-v1' for update;
  -- Exact historical request replay remains available, including grandfathered payloads.
  if exists(select 1 from public.paper_runtime_requests where owner_id=p_owner_id and data_mode=p_data_mode
      and model_version=m.model_version and request_id=p_request_id) then
    return public.commit_paper_session_before011(p_owner_id,p_data_mode,p_expected_revision,p_request_id,p_session,p_book,p_evaluations,p_source_run_id);
  end if;
  for item in select * from jsonb_each(p_book->'trades') loop
    e:=item.value; old_t:=m.book->'trades'->item.key;
    if (e#>>'{experiment,id}') is distinct from ('close-signal-risk-v1-'||
        (case when e#>>'{experiment,exit,mode}'='fixed_rr' then 'fixed2r' else 'ma10' end)||'-'||(e#>>'{experiment,strategy}')) then
      raise exception 'paper_experiment_identity_mismatch' using errcode='22023'; end if;
    policy:=coalesce(e->>'sizing_policy_version','rounded_net_v1');
    if (old_t is null and policy<>'exact_risk_fees_v2')
      or policy not in ('rounded_net_v1','exact_risk_fees_v2')
      or (old_t is not null and policy is distinct from coalesce(old_t->>'sizing_policy_version','rounded_net_v1')) then
      raise exception 'immutable_paper_sizing_policy' using errcode='22023'; end if;
    if policy='exact_risk_fees_v2' then
      lots:=(e->>'lots')::bigint;qty:=lots*100;entry:=(e->>'planned_entry_price')::numeric;stop:=(e->>'stop')::numeric;
      raw_loss:=qty*(entry-stop)+round(qty*entry*0.0015,2)+round(qty*stop*0.0025,2);
      if raw_loss>1000000 then raise exception 'invalid_paper_sizing' using errcode='22023'; end if;
    end if;
    for proof in select x.value from jsonb_array_elements(e->'events') with ordinality x(value,n)
      where x.n>coalesce(jsonb_array_length(old_t->'events'),0) and x.value ? 'untradable_evidence' loop
      if not public.valid_paper_untradable_evidence_v1(proof->'untradable_evidence',e#>>'{signal,ticker}',p_data_mode,
        (proof->>'session')::date,(proof->>'observed_at')::timestamptz) then
        raise exception 'invalid_paper_untradable_evidence' using errcode='22023'; end if;
    end loop;
  end loop;
  for item in select * from jsonb_each(p_evaluations) loop
    e:=item.value; old_e:=m.evaluations->item.key;
    select * into sig from public.signals where id=item.key and data_mode=p_data_mode;
    if not found then raise exception 'invalid_signal_evaluation' using errcode='22023'; end if;
    if old_e is null and ((e->>'signal_session')::date is distinct from sig.session_date
      or (e->>'entry_session')::date is distinct from sig.planned_entry_session
      or (e->>'entry_price')::numeric is distinct from (sig.snapshot#>>'{candidate,reference_close}')::numeric
      or (e->>'initial_stop')::numeric is distinct from (sig.snapshot#>>'{candidate,stop}')::numeric
      or (e->>'target_1r')::numeric is distinct from 2*(e->>'entry_price')::numeric-(e->>'initial_stop')::numeric
      or (e->>'target_2r')::numeric is distinct from 3*(e->>'entry_price')::numeric-2*(e->>'initial_stop')::numeric
      or (e->>'entry_price')::numeric <= (e->>'initial_stop')::numeric or (e->>'initial_stop')::numeric<=0) then
      raise exception 'signal_evaluation_plan_mismatch' using errcode='22023'; end if;
    old_count:=coalesce((old_e->>'observed_sessions')::integer,0);
    old_len:=coalesce(jsonb_array_length(old_e->'input_digests'),0);
    n:=(e->>'observed_sessions')::integer;
    if jsonb_typeof(coalesce(e->'untradable_evidence','[]'::jsonb)) is distinct from 'array' then
      raise exception 'invalid_signal_evaluation_evidence' using errcode='22023'; end if;
    proof_len:=jsonb_array_length(coalesce(e->'untradable_evidence','[]'::jsonb));
    old_proof_len:=jsonb_array_length(coalesce(old_e->'untradable_evidence','[]'::jsonb));
    if proof_len<old_proof_len or exists(select 1 from jsonb_array_elements(old_e->'untradable_evidence') with ordinality p(value,n)
        where p.value is distinct from e->'untradable_evidence'->(p.n::integer-1)) then
      raise exception 'immutable_signal_evaluation_evidence' using errcode='22023'; end if;
    for proof in select x.value from jsonb_array_elements(e->'untradable_evidence') with ordinality x(value,n)
      where x.n>old_proof_len loop
      select closes_at into close_at from public.paper_calendar_days_v1() where day=(proof->>'session')::date;
      if not proof ? 'observed_at' or close_at is null or (proof->>'session')::date<sig.planned_entry_session
        or (proof->>'session')::date>p_session or (proof->>'observed_at')::timestamptz<close_at
        or not public.valid_paper_untradable_evidence_v1(proof,sig.ticker,p_data_mode,
          (proof->>'session')::date,(proof->>'observed_at')::timestamptz) then
        raise exception 'invalid_signal_evaluation_evidence' using errcode='22023'; end if;
    end loop;
    for v in select key,value from jsonb_each_text(e->'results') where value='excluded'
      and value is distinct from old_e#>>array['results',key] loop
      last_day:=case when v.key='net_5' then (select day from public.paper_calendar_days_v1()
        where day>=sig.planned_entry_session order by day offset 4 limit 1)
        when v.key='net_10' then (select day from public.paper_calendar_days_v1()
        where day>=sig.planned_entry_session order by day offset 9 limit 1) else null end;
      if not coalesce((n=0 and e#>>array['exclusion_reasons',v.key]='official_untradable_entry'
          and exists(select 1 from jsonb_array_elements(e->'untradable_evidence') p where p->>'session'=e->>'entry_session'))
        or (e#>>array['exclusion_reasons',v.key]='official_untradable_horizon' and last_day is not null
          and n>=case when v.key='net_5' then 5 else 10 end
          and exists(select 1 from jsonb_array_elements(e->'untradable_evidence') p where (p->>'session')::date=last_day)),false) then
        raise exception 'signal_evaluation_exclusion_evidence_required' using errcode='22023'; end if;
    end loop;
    if old_e is not null and exists(select 1 from jsonb_each_text(old_e->'results') r where r.value='excluded'
      and e#>>array['exclusion_reasons',r.key] is distinct from old_e#>>array['exclusion_reasons',r.key]) then
      raise exception 'immutable_signal_evaluation_exclusion' using errcode='22023'; end if;
    if old_e is not null and n=old_count and (
        (e->>'last_session')::date is distinct from (old_e->>'last_session')::date
        or exists(select 1 from jsonb_each_text(e->'results') r where r.value not in ('pending','data_hold')
          and r.value is distinct from old_e#>>array['results',r.key]
          and not (n=0 and r.value='excluded' and e#>>array['exclusion_reasons',r.key]='official_untradable_entry'
            and proof_len>old_proof_len and exists(select 1 from jsonb_array_elements(e->'untradable_evidence') with ordinality p(value,n)
              where p.n>old_proof_len and p.value->>'session'=e->>'entry_session')))) then
      raise exception 'signal_evaluation_observation_required' using errcode='22023'; end if;
    if jsonb_typeof(e->'input_digests') is distinct from 'array' or n is null or n<old_count
      or jsonb_array_length(e->'input_digests')-old_len<>n-old_count
      or ((e->>'last_session')::date>p_session)
      or (n=0 and e->>'last_session' is not null) then
      raise exception 'signal_evaluation_observation_mismatch' using errcode='22023'; end if;
    previous_day:=(old_e->>'last_session')::date;
    for v in select value,ordinality from jsonb_array_elements(e->'input_digests') with ordinality where ordinality>old_len loop
      if jsonb_typeof(v.value)<>'object' or v.value->>'digest' is null or v.value->>'digest' !~ '^[0-9a-f]{64}$'
        or v.value->>'observed_at' is null then raise exception 'invalid_signal_evaluation_digest' using errcode='22023'; end if;
      last_day:=(v.value->>'session')::date;
      select closes_at into close_at from public.paper_calendar_days_v1() where day=last_day;
      if close_at is null or last_day>p_session or (v.value->>'observed_at')::timestamptz<close_at
        or (previous_day is null and last_day<>sig.planned_entry_session)
        or (previous_day is not null and last_day is distinct from (select min(day) from public.paper_calendar_days_v1() where day>previous_day)) then
        raise exception 'invalid_signal_evaluation_chronology' using errcode='22023'; end if;
      previous_day:=last_day;
    end loop;
    if n>old_count and (e->>'last_session')::date is distinct from previous_day then
      raise exception 'signal_evaluation_observation_mismatch' using errcode='22023'; end if;
    if old_e is null and n>0 then
      select count(*) into expected_count from public.paper_calendar_days_v1() where day between sig.planned_entry_session and (e->>'last_session')::date;
      if n<>expected_count then raise exception 'signal_evaluation_observation_mismatch' using errcode='22023'; end if;
    end if;
    if (e#>>'{results,net_5}'='won' and n<5 and coalesce(old_e#>>'{results,net_5}','')<>'won')
      or (e#>>'{results,net_10}'='won' and n<10 and coalesce(old_e#>>'{results,net_10}','')<>'won') then
      raise exception 'signal_evaluation_horizon_incomplete' using errcode='22023'; end if;
    if n=0 and exists(select 1 from jsonb_each_text(e->'results') r
        where r.value in ('won','lost','ambiguous') and r.value is distinct from old_e#>>array['results',r.key]) then
      raise exception 'signal_evaluation_observation_required' using errcode='22023'; end if;
  end loop;
  return public.commit_paper_session_before011(p_owner_id,p_data_mode,p_expected_revision,p_request_id,p_session,p_book,p_evaluations,p_source_run_id);
end $$;
revoke all on function public.commit_paper_session_v1(uuid,text,bigint,text,date,jsonb,jsonb,uuid) from public,anon,authenticated,service_role;
grant execute on function public.commit_paper_session_v1(uuid,text,bigint,text,date,jsonb,jsonb,uuid) to service_role;

create or replace function public.trade_reporting_summary_v1(p_rows jsonb) returns jsonb
language sql immutable set search_path='' as $$
  with r as(select (value->>'realized_pnl_idr')::numeric pnl,(value->>'realized_r')::numeric rr,n from jsonb_array_elements(p_rows) with ordinality e(value,n)),
  o as(select n,sum(pnl) over(order by n) cum from r),d as(select greatest(0,max(cum) over(order by n))-cum dd from o),
  s as(select count(*) closed,count(*) filter(where pnl>0) wins,count(*) filter(where pnl<0) losses,count(*) filter(where pnl=0) be,
    coalesce(sum(pnl),0) net,avg(pnl) expectancy,avg(rr) expectancy_r,sum(pnl) filter(where pnl>0) gains,
    -sum(pnl) filter(where pnl<0) losses_total,avg(pnl) filter(where pnl>0) avg_win,-avg(pnl) filter(where pnl<0) avg_loss from r)
  select jsonb_build_object('closed',closed,'wins',wins,'losses',losses,'breakeven',be,'net_pnl_idr',net,
    'win_rate',wins::numeric/nullif(closed,0),'expectancy_idr',expectancy,'expectancy_r',expectancy_r,'max_drawdown_idr',(select coalesce(max(dd),0) from d),
    'profit_factor_idr',case when losses>0 then coalesce(gains,0)/losses_total else null end,
    'payoff_ratio_idr',avg_win/nullif(avg_loss,0),
    'profit_factor_state',case when closed=0 then 'no_closed' when wins=0 and losses=0 then 'no_directional_results' when losses=0 then 'no_losses' else 'finite' end,
    'payoff_ratio_state',case when closed=0 then 'no_closed' when wins=0 and losses=0 then 'no_directional_results' when losses=0 then 'no_losses' when wins=0 then 'no_wins' else 'finite' end) from s;
$$;

create function public.paper_exclusion_reason_v1(p_trade public.paper_trades) returns text
language sql immutable set search_path='' as $$
  select case when p_trade.cohort<>'forward' then 'non_forward_cohort'
    when exists(select 1 from jsonb_array_elements(p_trade.details->'events') e where e->>'reason'='late_model_only')
      or p_trade.reason like '%late%' then 'late_model_only'
    when p_trade.state='ambiguous_review' or p_trade.alternate_r is not null then 'ambiguous_order'
    when not p_trade.actionable then 'nonactionable_model_only'
    when p_trade.state in ('skipped','expired') then p_trade.reason else null end;
$$;
revoke all on function public.paper_exclusion_reason_v1(public.paper_trades) from public,anon,authenticated,service_role;

create function public.reporting_trade_enrichment_v1(p_row jsonb,p_owner uuid,p_mode text,p_data text,p_as_of date)
returns jsonb language plpgsql stable security definer set search_path='' as $$
declare t public.paper_trades; a public.actual_trades; reason text; holding bigint; days integer; end_day date; entered boolean; eligible boolean;
begin
  if p_mode='paper' then
    select * into strict t from public.paper_trades where id=p_row->>'id' and owner_id=p_owner and data_mode=p_data;
    reason:=public.paper_exclusion_reason_v1(t); entered:=t.details->>'entry' is not null;
    eligible:=t.state='closed' and reason is null;
  else
    select * into strict a from public.actual_trades where id=(p_row->>'id')::uuid and owner_id=p_owner and data_mode=p_data;
    entered:=(p_row->>'entry_session') is not null;eligible:=a.status='closed';
    p_row:=p_row||jsonb_build_object('state',a.status,'open_quantity',a.open_quantity,'current_stop',a.current_stop,'revision',a.revision);
  end if;
  end_day:=coalesce((p_row->>'exit_session')::date,p_as_of);
  if entered and (p_row->>'entry_session')::date<=end_day then
    if exists(select 1 from public.paper_calendar_days_v1() where day=(p_row->>'entry_session')::date)
      and exists(select 1 from public.paper_calendar_days_v1() where day=end_day) then
      select count(*) into holding from public.paper_calendar_days_v1() where day between (p_row->>'entry_session')::date and end_day;
    end if;
    days:=end_day-(p_row->>'entry_session')::date+1;
  end if;
  return p_row||jsonb_build_object('metric_eligible',eligible,'exclusion_reason',reason,
    'cohort',case when p_mode='paper' then t.cohort else null end,'holding_sessions',holding,'holding_calendar_days',days);
end $$;
revoke all on function public.reporting_trade_enrichment_v1(jsonb,uuid,text,text,date) from public,anon,authenticated,service_role;

create function public.paper_experiment_comparison_v1(p_owner uuid,p_data text,p_from date,p_to date,p_strategy text,p_as_of date)
returns jsonb language plpgsql stable security definer set search_path='' as $$
declare rows_json jsonb; sides jsonb:='{}'; exit_key text; closed_rows jsonb; side jsonb; common_ids jsonb; fixed_ids jsonb; ma_ids jsonb; pairs jsonb;
begin
  select coalesce(jsonb_agg(public.reporting_trade_enrichment_v1(to_jsonb(r),p_owner,'paper',p_data,p_as_of)||jsonb_build_object('exit_key',k.exit_key)),'[]') into rows_json
    from (values('fixed2r'),('ma10')) k(exit_key) cross join lateral public.trade_reporting_rows_v1(p_owner,p_data,'paper',k.exit_key,p_strategy,null,null) r
    where r.state not in ('closed','ambiguous_review') or ((p_from is null or r.exit_session>=p_from) and (p_to is null or r.exit_session<=p_to));
  foreach exit_key in array array['fixed2r','ma10'] loop
    select coalesce(jsonb_agg(x order by x->>'exit_session',x->>'id'),'[]') into closed_rows
      from jsonb_array_elements(rows_json) x where x->>'exit_key'=exit_key and (x->>'metric_eligible')::boolean;
    select jsonb_build_object('signals',count(*),'entered',count(*) filter(where x->>'holding_calendar_days' is not null),
      'closed_assessed',count(*) filter(where (x->>'metric_eligible')::boolean),'open',count(*) filter(where x->>'state'='open'),
      'pending_entry',count(*) filter(where x->>'state'='pending_entry'),'skipped',count(*) filter(where x->>'state'='skipped'),
      'excluded',count(*) filter(where x->>'state' in ('closed','ambiguous_review') and not (x->>'metric_eligible')::boolean),
      'mean_holding_sessions',avg((x->>'holding_sessions')::numeric)) into side from jsonb_array_elements(rows_json)x where x->>'exit_key'=exit_key;
    sides:=sides||jsonb_build_object(exit_key,side||jsonb_build_object('summary',public.trade_reporting_summary_v1(closed_rows)));
  end loop;
  with entered as(select x from jsonb_array_elements(rows_json)x where x->>'holding_calendar_days' is not null),
    f as(select x from entered where x->>'exit_key'='fixed2r'),m as(select x from entered where x->>'exit_key'='ma10'),
    paired as(select f.x f,m.x m from f join m on f.x->>'signal_id'=m.x->>'signal_id')
  select coalesce((select jsonb_agg(f->>'signal_id' order by f->>'signal_id') from paired),'[]'),
    coalesce((select jsonb_agg(x->>'signal_id' order by x->>'signal_id') from f where not exists(select 1 from m where m.x->>'signal_id'=f.x->>'signal_id')),'[]'),
    coalesce((select jsonb_agg(x->>'signal_id' order by x->>'signal_id') from m where not exists(select 1 from f where f.x->>'signal_id'=m.x->>'signal_id')),'[]'),
    coalesce((select jsonb_agg(jsonb_build_object('signal_id',f->>'signal_id','ticker',f->>'ticker','strategy',f->>'strategy',
      'fixed2r',jsonb_build_object('trade_id',f->>'id','state',f->>'state','metric_eligible',(f->>'metric_eligible')::boolean,'pnl_idr',case when (f->>'metric_eligible')::boolean then (f->>'realized_pnl_idr')::numeric else null end,'holding_sessions',(f->>'holding_sessions')::integer),
      'ma10',jsonb_build_object('trade_id',m->>'id','state',m->>'state','metric_eligible',(m->>'metric_eligible')::boolean,'pnl_idr',case when (m->>'metric_eligible')::boolean then (m->>'realized_pnl_idr')::numeric else null end,'holding_sessions',(m->>'holding_sessions')::integer)) order by f->>'signal_id') from paired),'[]')
    into common_ids,fixed_ids,ma_ids,pairs;
  return sides||jsonb_build_object('cohort_basis','exit_session_and_active','common_entry_signal_ids',common_ids,
    'fixed_only_entry_signal_ids',fixed_ids,'sma_only_entry_signal_ids',ma_ids,'paired',pairs);
end $$;
revoke all on function public.paper_experiment_comparison_v1(uuid,text,date,date,text,date) from public,anon,authenticated,service_role;

alter function public.read_trade_reporting_v1(text,date,date,text,text,integer,text,jsonb) rename to read_trade_reporting_before011;
revoke all on function public.read_trade_reporting_before011(text,date,date,text,text,integer,text,jsonb) from public,anon,authenticated,service_role;
create function public.read_trade_reporting_v1(p_mode text default 'paper',p_from date default null,p_to date default null,p_strategy text default null,
  p_exit_key text default 'fixed2r',p_page integer default 1,p_exit_version text default null,p_exit_snapshot jsonb default null)
returns jsonb language plpgsql stable security definer set search_path='' as $$
declare r jsonb; owner uuid:=auth.uid(); dm text; trades jsonb; excluded jsonb; reasons jsonb; sl_rows jsonb; tp_rows jsonb; statuses jsonb;
begin
  r:=public.read_trade_reporting_before011(p_mode,p_from,p_to,p_strategy,p_exit_key,p_page,p_exit_version,p_exit_snapshot);
  dm:=r->>'data_mode';statuses:=r->'statuses';
  select coalesce(jsonb_agg(public.reporting_trade_enrichment_v1(x,owner,p_mode,dm,(r->>'as_of_session')::date)),'[]') into trades from jsonb_array_elements(r->'trades')x;
  if p_mode='paper' then
    with rows as(select t,public.paper_exclusion_reason_v1(t) why from public.paper_trades t where t.owner_id=owner and t.data_mode=dm and t.model_version='close-signal-risk-v1'
      and ((p_exit_key='fixed2r' and t.exit_mode='fixed_rr') or(p_exit_key='ma10' and t.exit_mode='ma_close'))
      and(p_strategy is null or t.strategy=p_strategy) and t.state in ('closed','ambiguous_review')
      and(p_from is null or t.exit_session>=p_from) and(p_to is null or t.exit_session<=p_to))
    select jsonb_build_object('closed_excluded',count(*) filter(where why is not null),'reasons',coalesce((select jsonb_object_agg(why,n) from(select why,count(*) n from rows where why is not null group by why)x),'{}'))
      into excluded from rows;
    with rows as(select t,public.paper_exclusion_reason_v1(t) why from public.paper_trades t where t.owner_id=owner and t.data_mode=dm and t.model_version='close-signal-risk-v1'
      and ((p_exit_key='fixed2r' and t.exit_mode='fixed_rr') or(p_exit_key='ma10' and t.exit_mode='ma_close'))
      and(p_strategy is null or t.strategy=p_strategy) and t.state in ('closed','ambiguous_review')
      and(p_from is null or t.exit_session>=p_from) and(p_to is null or t.exit_session<=p_to))
    select coalesce(jsonb_agg(jsonb_build_object('realized_pnl_idr',(t).net_pnl_idr,'realized_r',(t).realized_r) order by (t).exit_session,(t).id),'[]'),
      coalesce(jsonb_agg(jsonb_build_object('realized_pnl_idr',case when why='ambiguous_order' then ((t).details->>'alternate_net_pnl')::numeric else (t).net_pnl_idr end,
        'realized_r',case when why='ambiguous_order' then (t).alternate_r else (t).realized_r end) order by (t).exit_session,(t).id),'[]')
      into sl_rows,tp_rows from rows where why is null or why='ambiguous_order';
    r:=r||jsonb_build_object('sensitivities',jsonb_build_object('sl_first',public.trade_reporting_summary_v1(sl_rows),'tp_first',public.trade_reporting_summary_v1(tp_rows)),
      'experiment_comparison',public.paper_experiment_comparison_v1(owner,dm,p_from,p_to,p_strategy,(r->>'as_of_session')::date));
  else
    excluded:=jsonb_build_object('closed_excluded',0,'reasons','{}'::jsonb);
    statuses:=statuses||jsonb_build_object('pending_entry',0,'draft',(select count(*) from public.actual_trades where owner_id=owner and data_mode=dm and status='draft'
      and(p_strategy is null or primary_strategy=p_strategy) and(p_exit_version is null or exit_policy_snapshot->>'version'=p_exit_version) and(p_exit_snapshot is null or exit_policy_snapshot=p_exit_snapshot)));
  end if;
  return r||jsonb_build_object('trades',trades,'statuses',statuses,'status_scope','all_history','exclusions',excluded,
    'processing_health',case when p_mode='paper' then public.paper_processing_health_v1(owner,dm,now()) else null end);
end $$;
revoke all on function public.read_trade_reporting_v1(text,date,date,text,text,integer,text,jsonb) from public,anon,authenticated,service_role;
grant execute on function public.read_trade_reporting_v1(text,date,date,text,text,integer,text,jsonb) to authenticated;

alter function public.read_signal_evaluation_v1(date,date,text,integer) rename to read_signal_evaluation_before011;
revoke all on function public.read_signal_evaluation_before011(date,date,text,integer) from public,anon,authenticated,service_role;
create function public.read_signal_evaluation_v1(p_from date default null,p_to date default null,p_strategy text default null,p_page integer default 1)
returns jsonb language plpgsql stable security definer set search_path='' as $$
declare r jsonb; begin
  r:=public.read_signal_evaluation_before011(p_from,p_to,p_strategy,p_page);
  return r||jsonb_build_object('processing_health',public.paper_processing_health_v1(auth.uid(),r->>'data_mode',now()));
end $$;
revoke all on function public.read_signal_evaluation_v1(date,date,text,integer) from public,anon,authenticated,service_role;
grant execute on function public.read_signal_evaluation_v1(date,date,text,integer) to authenticated;

alter function public.read_paper_trade_v1(text) rename to read_paper_trade_before011;
revoke all on function public.read_paper_trade_before011(text) from public,anon,authenticated,service_role;
create function public.read_paper_trade_v1(p_trade_id text) returns jsonb
language plpgsql stable security definer set search_path='' as $$
declare r jsonb; checkpoint date; begin
  r:=public.read_paper_trade_before011(p_trade_id);
  if r is null then return null; end if;
  select last_session into checkpoint from public.paper_models where owner_id=auth.uid() and data_mode=r->>'data_mode' and model_version='close-signal-risk-v1';
  return r||jsonb_build_object('trade',public.reporting_trade_enrichment_v1(r->'trade',auth.uid(),'paper',r->>'data_mode',checkpoint));
end $$;
revoke all on function public.read_paper_trade_v1(text) from public,anon,authenticated,service_role;
grant execute on function public.read_paper_trade_v1(text) to authenticated;

commit;
