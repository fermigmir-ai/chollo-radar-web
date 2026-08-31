alter table public.bot_runs
  drop constraint if exists bot_runs_source_check;

alter table public.bot_runs
  add constraint bot_runs_source_check
  check (source in ('demo', 'amazon', 'bootstrap')) not valid;

alter table public.bot_runs
  validate constraint bot_runs_source_check;

