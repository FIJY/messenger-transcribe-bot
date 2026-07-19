# SQL-запросы для проверки таблицы платежных уведомлений

Ниже — готовые SQL-запросы, которые можно по очереди выполнить в Supabase SQL Editor / Postgres, если Telegram-listener запущен, но таблица с платежными уведомлениями не обновляется.

> Если в вашем backend уже используется другое имя таблицы, замените `payment_telegram_ingest_events` на фактическое имя таблицы из обработчика `PAYMENT_INGEST_URL`.

## 1. Создать таблицу для сырых Telegram-уведомлений

```sql
create extension if not exists pgcrypto;

create table if not exists public.payment_telegram_ingest_events (
  id uuid primary key default gen_random_uuid(),
  telegram_message_id bigint not null,
  telegram_chat_id bigint not null,
  telegram_sender_id bigint not null,
  message_date timestamptz,
  raw_text text not null,
  payload jsonb not null default '{}'::jsonb,
  processed_at timestamptz,
  processing_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint payment_telegram_ingest_events_message_unique
    unique (telegram_chat_id, telegram_message_id)
);
```

## 2. Включить автообновление `updated_at`

```sql
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists set_payment_telegram_ingest_events_updated_at
  on public.payment_telegram_ingest_events;

create trigger set_payment_telegram_ingest_events_updated_at
before update on public.payment_telegram_ingest_events
for each row
execute function public.set_updated_at();
```

## 3. Дать backend-ключу право писать в таблицу

Если backend пишет через Supabase `service_role`, RLS можно оставить включенным: `service_role` обходит политики. Для диагностики важно проверить, что RLS не блокирует обычный `anon`/`authenticated` ключ.

```sql
alter table public.payment_telegram_ingest_events enable row level security;

-- Только если ingest endpoint реально пишет НЕ service_role-ключом.
-- Для production лучше сузить policy под вашу роль/claim.
drop policy if exists "payment ingest insert" on public.payment_telegram_ingest_events;

create policy "payment ingest insert"
on public.payment_telegram_ingest_events
for insert
to authenticated
with check (true);
```

## 4. Проверить ручную вставку

```sql
insert into public.payment_telegram_ingest_events (
  telegram_message_id,
  telegram_chat_id,
  telegram_sender_id,
  message_date,
  raw_text,
  payload
)
values (
  999999001,
  -1001234567890,
  123456789,
  now(),
  '$1.00 paid by Test User (*1234) on test via ABA PAY test Trx. ID: TEST123, APV: OK.',
  jsonb_build_object('source', 'manual_sql_check')
)
on conflict (telegram_chat_id, telegram_message_id) do update
set
  raw_text = excluded.raw_text,
  payload = excluded.payload,
  updated_at = now();
```

## 5. Посмотреть последние события

```sql
select
  id,
  telegram_message_id,
  telegram_chat_id,
  telegram_sender_id,
  message_date,
  raw_text,
  processed_at,
  processing_error,
  created_at,
  updated_at
from public.payment_telegram_ingest_events
order by created_at desc
limit 20;
```

## 6. Проверить, не приходят ли дубликаты

```sql
select
  telegram_chat_id,
  telegram_message_id,
  count(*) as duplicates
from public.payment_telegram_ingest_events
group by telegram_chat_id, telegram_message_id
having count(*) > 1;
```

## 7. Быстро очистить тестовую запись

```sql
delete from public.payment_telegram_ingest_events
where telegram_message_id = 999999001
  and payload->>'source' = 'manual_sql_check';
```

## Что проверить, если ручной `insert` работает, а listener всё равно не обновляет таблицу

1. `KHMER_PAYMENT_LISTENER_ENABLED` должен быть `true` на worker-сервисе.
2. `PAYMENT_INGEST_URL` должен указывать на backend endpoint, который действительно делает `insert`/`upsert` в эту таблицу.
3. `PAYMENT_INGEST_SECRET` в listener и backend должен совпадать, иначе endpoint может отклонять запрос до записи в БД.
4. `TELEGRAM_PAYMENT_CHAT_ID` и `TELEGRAM_PAYWAY_USER_ID` должны быть числами и совпадать с реальным чатом/ботом PayWay.
5. Текст PayWay-сообщения должен совпадать с ожидаемым форматом, иначе listener отфильтрует событие до отправки в endpoint.
