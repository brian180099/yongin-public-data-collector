begin;

create extension if not exists pgcrypto;

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'yongin_collector_writer') then
    create role yongin_collector_writer nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'yongin_analysis_reader') then
    create role yongin_analysis_reader nologin;
  end if;
end
$$;

create schema if not exists collector;
create schema if not exists analytics;
revoke all on schema collector from public;
revoke all on schema analytics from public;

create table if not exists collector.datasets (
  dataset_id text primary key check (dataset_id ~ '^[a-z0-9_]+$'),
  display_name text not null,
  domain text not null check (domain in ('생활여가', '문화', '체육')),
  provider text not null,
  portal_url text not null,
  access_method text not null check (access_method in ('file', 'api', 'page')),
  source_url text not null,
  update_frequency text not null,
  full_snapshot boolean not null default true,
  active boolean not null default false,
  unique_key_columns text[] not null check (cardinality(unique_key_columns) > 0),
  required_columns text[] not null check (cardinality(required_columns) > 0),
  reference_date_column text,
  check_interval_days integer not null default 7 check (check_interval_days > 0),
  next_check_at timestamptz not null default now(),
  last_success_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists collector.collection_runs (
  run_id uuid primary key default gen_random_uuid(),
  dataset_id text not null references collector.datasets(dataset_id),
  trigger_type text not null check (trigger_type in ('manual', 'schedule', 'retry')),
  status text not null check (status in ('running', 'success', 'no_change', 'failed', 'blocked')),
  is_baseline boolean not null default false,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  collected_at timestamptz,
  reference_date date,
  source_record_count integer check (source_record_count >= 0),
  baseline_count integer not null default 0 check (baseline_count >= 0),
  added_count integer not null default 0 check (added_count >= 0),
  modified_count integer not null default 0 check (modified_count >= 0),
  deleted_candidate_count integer not null default 0 check (deleted_candidate_count >= 0),
  unchanged_count integer not null default 0 check (unchanged_count >= 0),
  raw_sha256 char(64),
  raw_path text,
  quality_summary jsonb not null default '{}'::jsonb,
  change_examples jsonb not null default '[]'::jsonb,
  error_code text,
  error_message text
);

create index if not exists collection_runs_dataset_started_idx
  on collector.collection_runs (dataset_id, started_at desc);
create index if not exists collection_runs_status_started_idx
  on collector.collection_runs (status, started_at desc);

create table if not exists collector.raw_artifacts (
  artifact_id uuid primary key default gen_random_uuid(),
  run_id uuid not null references collector.collection_runs(run_id) on delete cascade,
  dataset_id text not null references collector.datasets(dataset_id),
  sha256 char(64) not null,
  byte_count bigint not null check (byte_count > 0),
  content_type text,
  original_filename text,
  collected_at timestamptz not null,
  reference_date date,
  local_path text,
  storage_bucket text,
  storage_object_path text,
  created_at timestamptz not null default now(),
  unique (dataset_id, sha256)
);

create table if not exists collector.dataset_records (
  dataset_id text not null references collector.datasets(dataset_id),
  record_key text not null,
  payload jsonb not null,
  payload_hash char(64) not null,
  reference_date date,
  active boolean not null default true,
  first_seen_run_id uuid not null references collector.collection_runs(run_id),
  last_changed_run_id uuid not null references collector.collection_runs(run_id),
  last_seen_run_id uuid not null references collector.collection_runs(run_id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (dataset_id, record_key)
);

create index if not exists dataset_records_active_idx
  on collector.dataset_records (dataset_id, active);

create table if not exists collector.change_history (
  change_id bigint generated always as identity primary key,
  run_id uuid not null references collector.collection_runs(run_id) on delete cascade,
  dataset_id text not null references collector.datasets(dataset_id),
  record_key text not null,
  change_type text not null check (
    change_type in ('baseline', 'added', 'modified', 'delete_candidate')
  ),
  old_payload jsonb,
  new_payload jsonb,
  changed_at timestamptz not null default now()
);

create index if not exists change_history_dataset_changed_idx
  on collector.change_history (dataset_id, changed_at desc);
create index if not exists change_history_run_idx
  on collector.change_history (run_id);

create or replace view analytics.current_dataset_records as
select
  r.dataset_id,
  d.display_name,
  d.domain,
  r.record_key,
  r.payload,
  r.reference_date,
  d.portal_url,
  d.last_success_at,
  r.updated_at
from collector.dataset_records r
join collector.datasets d using (dataset_id)
where r.active;

create or replace view analytics.giheung_events as
select
  r.record_key as management_id,
  r.payload ->> '제목' as title,
  case when (r.payload ->> '시작일') ~ '^\d{4}-\d{2}-\d{2}$'
    then (r.payload ->> '시작일')::date end as start_date,
  case when (r.payload ->> '종료일') ~ '^\d{4}-\d{2}-\d{2}$'
    then (r.payload ->> '종료일')::date end as end_date,
  r.reference_date,
  d.portal_url as source_url,
  d.last_success_at
from collector.dataset_records r
join collector.datasets d using (dataset_id)
where r.dataset_id = 'giheung_events' and r.active;

grant usage on schema collector to yongin_collector_writer;
grant select, insert, update, delete on all tables in schema collector
  to yongin_collector_writer;
grant usage, select on all sequences in schema collector
  to yongin_collector_writer;
alter default privileges in schema collector
  grant select, insert, update, delete on tables to yongin_collector_writer;
alter default privileges in schema collector
  grant usage, select on sequences to yongin_collector_writer;

grant usage on schema analytics to yongin_analysis_reader;
grant select on all tables in schema analytics to yongin_analysis_reader;
alter default privileges in schema analytics
  grant select on tables to yongin_analysis_reader;

insert into collector.datasets (
  dataset_id, display_name, domain, provider, portal_url, access_method,
  source_url, update_frequency, full_snapshot, active, unique_key_columns,
  required_columns, reference_date_column, check_interval_days, metadata
) values
  (
    'giheung_events', '경기도 용인시_기흥구 이벤트 정보', '문화',
    '경기도 용인시', 'https://www.data.go.kr/data/15136583/fileData.do',
    'file', 'https://www.data.go.kr/data/15136583/fileData.do', '연간', true,
    true, array['관리번호'],
    array['관리번호','제목','시작일','종료일','데이터기준일자'],
    '데이터기준일자', 365,
    '{"spatial_unit":"용인시 기흥구","temporal_unit":"행사 기간","license":"이용허락범위 제한 없음"}'::jsonb
  ),
  (
    'public_facilities', '전국공공시설개방정보표준데이터', '생활여가',
    '지방자치단체', 'https://www.data.go.kr/data/15013117/standard.do',
    'api', 'https://api.data.go.kr/openapi/tn_pubr_public_pblfclt_opn_info_api',
    '분기', true, false, array['openFcltyNm','rdnmadr'],
    array['openFcltyNm','rdnmadr','lnmadr','referenceDate'],
    'referenceDate', 90,
    '{"spatial_unit":"용인시 주소 필터","temporal_unit":"데이터 기준일","api_call_verified":false}'::jsonb
  ),
  (
    'library_new_books', '경기도 용인시_도서관 신간도서 정보', '문화',
    '경기도 용인시', 'https://www.data.go.kr/data/3038399/fileData.do',
    'file', 'https://www.data.go.kr/data/3038399/fileData.do', '반기', true,
    false, array['도서관명','도서명','저자'],
    array['도서관명','도서명','저자'], null, 180,
    '{"contract_status":"후보; 실제 컬럼·고유키 재검증 필요"}'::jsonb
  )
on conflict (dataset_id) do update set
  display_name = excluded.display_name,
  domain = excluded.domain,
  provider = excluded.provider,
  portal_url = excluded.portal_url,
  access_method = excluded.access_method,
  source_url = excluded.source_url,
  update_frequency = excluded.update_frequency,
  full_snapshot = excluded.full_snapshot,
  unique_key_columns = excluded.unique_key_columns,
  required_columns = excluded.required_columns,
  reference_date_column = excluded.reference_date_column,
  check_interval_days = excluded.check_interval_days,
  metadata = excluded.metadata,
  updated_at = now();

commit;
