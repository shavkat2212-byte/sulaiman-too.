-- Необязательно. Дополнительные данные клиента для бланка обязательства.
-- Приложение работает и без этой миграции (поля просто останутся пустыми линиями).
alter table if exists public.clients add column if not exists pin text;
alter table if exists public.clients add column if not exists passport_issued_by text;
alter table if exists public.clients add column if not exists passport_date date;
-- passport уже есть в таблице clients
