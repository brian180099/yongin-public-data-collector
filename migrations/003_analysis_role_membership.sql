begin;

-- The existing Supabase postgres login can temporarily switch to the
-- analytics-only group role. A dedicated login should replace this DSN.
grant yongin_analysis_reader to postgres;

commit;
