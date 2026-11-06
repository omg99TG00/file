-- Run once in Supabase SQL Editor (Dashboard → SQL Editor → New query)

create table if not exists users (
  id bigserial primary key,
  username text unique not null,
  password_hash text not null,
  role text not null default 'user',
  disabled boolean not null default false,
  created_at timestamptz not null default now()
);

create table if not exists sessions (
  id text primary key,
  user_id bigint not null references users(id) on delete cascade,
  created_at timestamptz not null default now(),
  expires_at timestamptz
);

create table if not exists deployments (
  id bigserial primary key,
  user_id bigint not null references users(id) on delete cascade,
  name text not null,
  token_enc text not null,
  channel_id text not null,
  huntbot boolean not null default false,
  speed text not null default 'lifetime',
  farm_on boolean not null default false,
  farm_started_at timestamptz,
  farm_ends_at timestamptz,
  cooldown_ends_at timestamptz,
  created_at timestamptz not null default now(),
  unique(user_id)
);

create unique index if not exists deployments_token_enc_uidx on deployments(token_enc);

create table if not exists app_meta (
  key text primary key,
  value text not null,
  updated_at timestamptz not null default now()
);

create table if not exists audit_log (
  id bigserial primary key,
  actor text,
  action text not null,
  detail text,
  created_at timestamptz not null default now()
);

insert into app_meta (key, value)
values ('global_pause', 'false')
on conflict (key) do nothing;
