-- Correction immédiate après chaque question (test du jour + entraînement)
-- À coller UNE FOIS dans Supabase > SQL Editor, puis Run. Ne supprime aucune donnée.
--
--  * repondre_question : enregistre la réponse (définitive) et renvoie juste/faux + bonne réponse + explication
--  * soumettre_test    : score calculé en base à partir des réponses déjà enregistrées
--  * demarrer_test(20) : si un test du jour est déjà commencé et pas fini, on le reprend là où il s'est arrêté

alter table public.test_questions add column if not exists reponse int;

create or replace function public.repondre_question(p_test uuid, p_question uuid, p_choix int) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
  uid uuid := auth.uid();
  r record;
begin
  if uid is null then raise exception 'Connexion requise'; end if;
  if not exists (select 1 from public.tests where id = p_test and user_id = uid and finished_at is null) then
    raise exception 'Test introuvable ou terminé';
  end if;
  select tq.* into r from public.test_questions tq where tq.test_id = p_test and tq.question_id = p_question;
  if not found then raise exception 'Question introuvable'; end if;
  if r.reponse is null then
    update public.test_questions set reponse = p_choix
     where test_id = p_test and question_id = p_question and reponse is null;
    r.reponse := p_choix;
  end if;
  return jsonb_build_object('juste', r.reponse = r.bonne, 'reponse', r.reponse, 'bonne', r.bonne, 'explication', r.explication);
end $$;
revoke execute on function public.repondre_question(uuid, uuid, int) from public, anon;
grant execute on function public.repondre_question(uuid, uuid, int) to authenticated;

drop function if exists public.soumettre_test(uuid, jsonb);
create function public.soumettre_test(p_test uuid, p_reponses jsonb default null) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
  uid uuid := auth.uid();
  t record;
  sc int;
begin
  if uid is null then raise exception 'Connexion requise'; end if;
  select * into t from public.tests where id = p_test and user_id = uid;
  if not found then raise exception 'Test introuvable'; end if;
  if t.finished_at is null then
    -- anciennes pages : on complète seulement les questions pas encore répondues
    if p_reponses is not null then
      update public.test_questions tq
         set reponse = (p_reponses ->> tq.question_id::text)::int
       where tq.test_id = p_test and tq.reponse is null and p_reponses ? tq.question_id::text;
    end if;
    select count(*) into sc from public.test_questions where test_id = p_test and reponse = bonne;
    update public.tests set score = sc, finished_at = now() where id = p_test;
  end if;
  return jsonb_build_object(
    'score', (select score from public.tests where id = p_test),
    'total', t.total,
    'detail', (select jsonb_agg(jsonb_build_object('enonce', enonce, 'choix', choix, 'bonne', bonne,
                 'reponse', reponse, 'explication', explication) order by position)
               from public.test_questions where test_id = p_test));
end $$;
revoke execute on function public.soumettre_test(uuid, jsonb) from public, anon;
grant execute on function public.soumettre_test(uuid, jsonb) to authenticated;

-- demarrer_test : reprise du test du jour commencé
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

  if off then
    select id into tid from public.tests
     where user_id = uid and officiel and finished_at is null
       and jour = (now() at time zone 'Europe/Paris')::date
     order by started_at desc limit 1;
    if tid is not null then
      return jsonb_build_object(
        'test_id', tid,
        'questions', (select jsonb_agg(jsonb_build_object('id', question_id, 'position', position, 'enonce', enonce, 'choix', choix) order by position)
                        from public.test_questions where test_id = tid),
        'deja', (select coalesce(jsonb_agg(jsonb_build_object('id', question_id, 'reponse', reponse, 'bonne', bonne, 'explication', explication, 'juste', reponse = bonne) order by position), '[]'::jsonb)
                   from public.test_questions where test_id = tid and reponse is not null));
    end if;
  end if;

  if (select count(*) from public.tests
      where user_id = uid and jour = (now() at time zone 'Europe/Paris')::date) >= 30 then
    raise exception 'Trop de tests aujourd''hui';
  end if;

  insert into public.tests (user_id, format, officiel) values (uid, n, off) returning id into tid;

  if off then
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
    'questions', (select jsonb_agg(jsonb_build_object('id', question_id, 'position', position, 'enonce', enonce, 'choix', choix) order by position)
                    from public.test_questions where test_id = tid),
    'deja', '[]'::jsonb);
end $$;
revoke execute on function public.demarrer_test(int) from public, anon;
grant execute on function public.demarrer_test(int) to authenticated;
