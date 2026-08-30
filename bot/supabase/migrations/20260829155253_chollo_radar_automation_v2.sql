create table if not exists public.bot_state (
  key text primary key,
  value text not null,
  updated_at timestamptz not null default now()
);

create table if not exists public.bot_runs (
  id bigint generated always as identity primary key,
  source text not null,
  dry_run boolean not null default true,
  status text not null default 'running',
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  queries integer not null default 0,
  fetched integer not null default 0,
  eligible integer not null default 0,
  published integer not null default 0,
  previewed integer not null default 0,
  skipped_recent integer not null default 0,
  errors jsonb not null default '[]'::jsonb,
  workflow_run_id text,
  constraint bot_runs_source_check check (source in ('demo', 'amazon')),
  constraint bot_runs_status_check
    check (status in ('running', 'completed', 'failed')),
  constraint bot_runs_counts_check check (
    queries >= 0 and fetched >= 0 and eligible >= 0 and published >= 0
    and previewed >= 0 and skipped_recent >= 0
  ),
  constraint bot_runs_errors_array_check
    check (jsonb_typeof(errors) = 'array')
);

create index if not exists bot_runs_started_at_idx
  on public.bot_runs (started_at desc);

alter table public.bot_state enable row level security;
alter table public.bot_runs enable row level security;

drop policy if exists deny_client_access on public.bot_state;
create policy deny_client_access on public.bot_state
  as restrictive for all to anon, authenticated
  using (false) with check (false);

drop policy if exists deny_client_access on public.bot_runs;
create policy deny_client_access on public.bot_runs
  as restrictive for all to anon, authenticated
  using (false) with check (false);

drop policy if exists deny_client_access on public.products;
create policy deny_client_access on public.products
  as restrictive for all to anon, authenticated
  using (false) with check (false);

drop policy if exists deny_client_access on public.price_observations;
create policy deny_client_access on public.price_observations
  as restrictive for all to anon, authenticated
  using (false) with check (false);

drop policy if exists deny_client_access on public.publications;
create policy deny_client_access on public.publications
  as restrictive for all to anon, authenticated
  using (false) with check (false);

drop policy if exists deny_client_access on public.watchlist_products;
create policy deny_client_access on public.watchlist_products
  as restrictive for all to anon, authenticated
  using (false) with check (false);

revoke all on public.bot_state, public.bot_runs,
  public.products, public.price_observations,
  public.publications, public.watchlist_products
  from anon, authenticated;

grant usage on schema public to service_role;
grant select, insert, update on public.bot_state to service_role;
grant select, insert, update on public.bot_runs to service_role;
grant usage, select on sequence public.bot_runs_id_seq to service_role;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'price_observations_price_nonnegative'
      and conrelid = 'public.price_observations'::regclass
  ) then
    alter table public.price_observations
      add constraint price_observations_price_nonnegative
      check (price >= 0) not valid;
  end if;

  if not exists (
    select 1 from pg_constraint
    where conname = 'publications_score_range'
      and conrelid = 'public.publications'::regclass
  ) then
    alter table public.publications
      add constraint publications_score_range
      check (score between 0 and 100) not valid;
  end if;

  if not exists (
    select 1 from pg_constraint
    where conname = 'publications_price_nonnegative'
      and conrelid = 'public.publications'::regclass
  ) then
    alter table public.publications
      add constraint publications_price_nonnegative
      check (price >= 0) not valid;
  end if;
end
$$;

alter table public.price_observations
  validate constraint price_observations_price_nonnegative;
alter table public.publications
  validate constraint publications_score_range;
alter table public.publications
  validate constraint publications_price_nonnegative;
