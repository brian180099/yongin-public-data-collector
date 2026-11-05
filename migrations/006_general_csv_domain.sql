begin;

alter table collector.datasets drop constraint datasets_domain_check;
alter table collector.datasets add constraint datasets_domain_check
  check (domain in ('생활여가', '문화', '체육', '교통', '기타'));

commit;
