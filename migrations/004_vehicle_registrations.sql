begin;

alter table collector.datasets drop constraint datasets_domain_check;
alter table collector.datasets add constraint datasets_domain_check
  check (domain in ('생활여가', '문화', '체육', '교통'));

insert into collector.datasets (
  dataset_id, display_name, domain, provider, portal_url, access_method,
  source_url, update_frequency, full_snapshot, active, unique_key_columns,
  required_columns, reference_date_column, check_interval_days, metadata
) values (
  'vehicle_registrations', '경기도 용인시_자동차 등록현황', '교통',
  '경기도 용인시', 'https://www.data.go.kr/data/3035912/fileData.do',
  'file', 'https://www.data.go.kr/data/3035912/fileData.do', '연간', true,
  true, array['시군구','읍면동'],
  array['시군구','읍면동','용도별 관용','용도별 자가용','용도별 영업용',
        '차종별 승용','차종별 승합','차종별 화물','차종별 특수','데이터기준일자'],
  '데이터기준일자', 365,
  '{"scope":"사용자가 승인한 교통 데이터 확장","spatial_unit":"시군구·읍면동","temporal_unit":"데이터기준일자"}'::jsonb
)
on conflict (dataset_id) do nothing;

create or replace view analytics.vehicle_registrations as
select
  r.record_key,
  r.payload ->> '시군구' as district,
  r.payload ->> '읍면동' as town,
  (r.payload ->> '용도별 관용')::integer as government_count,
  (r.payload ->> '용도별 자가용')::integer as private_count,
  (r.payload ->> '용도별 영업용')::integer as commercial_count,
  (r.payload ->> '차종별 승용')::integer as passenger_count,
  (r.payload ->> '차종별 승합')::integer as van_count,
  (r.payload ->> '차종별 화물')::integer as truck_count,
  (r.payload ->> '차종별 특수')::integer as special_count,
  r.reference_date,
  d.portal_url as source_url,
  d.last_success_at
from collector.dataset_records r
join collector.datasets d using (dataset_id)
where r.dataset_id = 'vehicle_registrations' and r.active;

grant select on analytics.vehicle_registrations to yongin_analysis_reader;

commit;
