-- Test du jour (20 questions, mêmes questions pour tous, classé) + entraînement (5 ou 10, au hasard, non classé)
-- À coller UNE FOIS dans Supabase > SQL Editor, puis Run. Ne supprime aucune donnée.
--
-- Règles :
--  * format 20 = test du jour : les 20 sujets les plus couverts qui ont une question, une question par sujet,
--    choisie et ordonnée de façon fixe pour la journée (même chose pour tout le monde, même en refaisant le test)
--  * format 5 ou 10 = entraînement : tirage au hasard, jamais dans le classement
--  * classement : 1 bonne réponse = 1 point, c'est le PREMIER test terminé du jour qui compte,
--    à égalité de points celui qui a fini en premier passe devant, nb_essais > 1 = tag « Refait »

alter table public.tests add column if not exists format int;
alter table public.tests add column if not exists officiel boolean not null default false;

create or replace function public.demarrer_test(p_nombre int default 20) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
  uid uuid := auth.uid();
  tid uuid;
  n int := case when p_nombre in (5, 10, 20) then p_nombre else 10 end;
  off boolean := (case when p_nombre in (5, 10, 20) then p_nombre else 10 end) = 20;
  j text := (now() at time zone 'Europe/Paris')::date::text;
begin
  if uid is null then raise exception 'Connexion requise'; end if;
  if (select count(*) from public.tests
      where user_id = uid and jour = (now() at time zone 'Europe/Paris')::date) >= 30 then
    raise exception 'Trop de tests aujourd''hui';
  end if;

  insert into public.tests (user_id, format, officiel) values (uid, n, off) returning id into tid;

  if off then
    -- Test du jour : sélection et ordre déterministes pour la journée
    insert into public.test_questions (test_id, position, question_id, enonce, choix, bonne, explication)
    select tid, row_number() over (order by md5(s.fiche_id::text || j)), s.id, s.enonce, s.choix, s.bonne, s.explication
    from (
      select * from (
        select distinct on (qq.fiche_id) qq.id, qq.fiche_id, qq.enonce, qq.choix, qq.bonne, qq.explication, f.rang
          from public.questions qq
          join public.fiches f on f.id = qq.fiche_id
         order by qq.fiche_id, md5(qq.id::text || j)
      ) one
      order by one.rang nulls last, one.fiche_id
      limit 20
    ) s;
  else
    -- Entraînement : au hasard parmi les 20 sujets les plus couverts
    insert into public.test_questions (test_id, position, question_id, enonce, choix, bonne, explication)
    select tid, row_number() over (), q.id, q.enonce, q.choix, q.bonne, q.explication
    from (
      select * from (
        select distinct on (qq.fiche_id) qq.*
          from public.questions qq
          join (select id from public.fiches order by rang nulls last, date desc limit 20) f
            on f.id = qq.fiche_id
         order by qq.fiche_id, random()
      ) one
      order by random() limit n
    ) q;
  end if;

  update public.tests
     set total = (select count(*) from public.test_questions where test_id = tid)
   where id = tid;

  if (select total from public.tests where id = tid) = 0 then
    raise exception 'Aucune question disponible';
  end if;

  return jsonb_build_object(
    'test_id', tid,
    'questions', (select jsonb_agg(jsonb_build_object(
        'id', question_id, 'position', position, 'enonce', enonce, 'choix', choix)
        order by position)
      from public.test_questions where test_id = tid)
  );
end $$;
revoke execute on function public.demarrer_test(int) from public, anon;
grant execute on function public.demarrer_test(int) to authenticated;

-- Classement du test du jour (un seul classement)
drop function if exists public.classement(int, date);
drop function if exists public.classement(date);
create function public.classement(p_jour date default null)
returns table (rang bigint, pseudo text, points int, total int, termine_a timestamptz, nb_essais int, moi boolean)
language sql stable security definer set search_path = '' as $$
  with fin as (
    select t.user_id, t.score, t.total, t.finished_at
      from public.tests t
     where t.finished_at is not null
       and t.officiel
       and t.jour = coalesce(p_jour, (now() at time zone 'Europe/Paris')::date)
  ),
  prem as (
    select distinct on (f.user_id)
           f.user_id, f.score, f.total, f.finished_at,
           (select count(*) from fin x where x.user_id = f.user_id)::int as essais
      from fin f
     order by f.user_id, f.finished_at asc
  )
  select row_number() over (order by b.score desc, b.finished_at asc, p.pseudo)::bigint,
         p.pseudo, b.score, b.total, b.finished_at, b.essais, (b.user_id = auth.uid())
    from prem b join public.profiles p on p.id = b.user_id
   order by 1
   limit 100;
$$;
revoke execute on function public.classement(date) from public, anon;
grant execute on function public.classement(date) to authenticated;
