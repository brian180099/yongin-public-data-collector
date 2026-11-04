begin;

create or replace view analytics.dataset_sources as
select d.dataset_id, d.display_name, d.provider, d.portal_url,
       r.reference_date, r.collected_at, d.last_success_at
from collector.datasets d
left join lateral (
  select reference_date, collected_at
  from collector.collection_runs
  where dataset_id=d.dataset_id and status in ('success','no_change')
  order by finished_at desc limit 1
) r on true;

grant select on analytics.dataset_sources to yongin_analysis_reader;

commit;
