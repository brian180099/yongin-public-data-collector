begin;

update collector.datasets
set unique_key_columns = array['insttCode','openFcltyNm','openLcNm'],
    required_columns = array['insttCode','openFcltyNm','openLcNm','referenceDate'],
    metadata = metadata || '{"api_call_verified":true,"scope":"용인시 도로명·지번 주소","key_note":"기관코드·시설명·장소명 조합; 공식 시설 ID 아님"}'::jsonb,
    updated_at = now()
where dataset_id = 'public_facilities';

create or replace view analytics.public_facilities as
select
  r.record_key,
  r.payload ->> 'openFcltyNm' as facility_name,
  r.payload ->> 'openLcNm' as place_name,
  r.payload ->> 'openFcltyType' as facility_type,
  case when r.payload ->> 'rdnmadr' like '%용인시%'
    then r.payload ->> 'rdnmadr'
    else r.payload ->> 'lnmadr' end as address,
  substring(
    case when r.payload ->> 'rdnmadr' like '%용인시%'
      then r.payload ->> 'rdnmadr'
      else r.payload ->> 'lnmadr' end
    from '용인시[[:space:]]+(처인구|기흥구|수지구)'
  ) as district,
  r.payload ->> 'institutionNm' as provider_name,
  r.payload ->> 'homepageUrl' as homepage_url,
  r.payload ->> 'latitude' as latitude,
  r.payload ->> 'longitude' as longitude,
  r.reference_date,
  d.portal_url as source_url,
  d.last_success_at
from collector.dataset_records r
join collector.datasets d using (dataset_id)
where r.dataset_id = 'public_facilities' and r.active;

grant select on analytics.public_facilities to yongin_analysis_reader;

commit;
