-- Niveau de difficulté des questions (1 facile, 2 moyen, 3 difficile)
-- À coller UNE FOIS dans Supabase > SQL Editor, puis Run. Ne supprime aucune donnée.
-- À lancer APRÈS 2026-11-26-correction-immediate.sql.
--
--  * Test du jour : 20 questions mêlant 7 faciles, 7 moyennes, 6 difficiles (complété par d'autres niveaux si besoin),
--    prises parmi les 40 sujets les plus couverts, mêmes pour tout le monde
--  * Entraînement : au hasard, avec en option un niveau (1, 2 ou 3). Sans niveau : mélange comme avant.

alter table public.questions add column if not exists difficulte int not null default 2;
alter table public.test_questions add column if not exists difficulte int;

drop function if exists public.demarrer_test(int);
drop function if exists public.demarrer_test(int, int);
create function public.demarrer_test(p_nombre int default 20, p_niveau int default null) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
  uid uuid := auth.uid();
  tid uuid;
  n int := case when p_nombre in (5, 10, 20) then p_nombre else 10 end;
  off boolean := (case when p_nombre in (5, 10, 20) then p_nombre else 10 end) = 20;
  niv int := case when p_niveau in (1, 2, 3) then p_niveau else null end;
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
        'questions', (select jsonb_agg(jsonb_build_object('id', question_id, 'position', position, 'enonce', enonce, 'choix', choix, 'difficulte', difficulte) order by position)
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
    -- Test du jour : réservoir = les 40 sujets les plus couverts qui ont une question ; quotas 7 / 7 / 6 par niveau
    insert into public.test_questions (test_id, position, question_id, enonce, choix, bonne, explication, difficulte)
    select tid, row_number() over (order by md5(s.fiche_id::text || j)), s.id, s.enonce, s.choix, s.bonne, s.explication, s.difficulte
    from (
      select * from (
        select r.*, row_number() over (partition by r.difficulte order by r.rang nulls last, r.fiche_id) as rn
        from (
          select distinct on (qq.fiche_id) qq.id, qq.fiche_id, qq.enonce, qq.choix, qq.bonne, qq.explication, qq.difficulte, f.rang
            from public.questions qq
            join (select id, rang from public.fiches
                   where exists (select 1 from public.questions z where z.fiche_id = fiches.id)
                   order by rang nulls last, date desc limit 40) f on f.id = qq.fiche_id
           order by qq.fiche_id, md5(qq.id::text || j)
        ) r
      ) x
      order by (x.rn <= case x.difficulte when 1 then 7 when 2 then 7 else 6 end) desc, x.rang nulls last, x.fiche_id
      limit 20
    ) s;
  else
    -- Entraînement : au hasard parmi les 20 sujets les plus couverts (ou 40 si un niveau est choisi)
    insert into public.test_questions (test_id, position, question_id, enonce, choix, bonne, explication, difficulte)
    select tid, row_number() over (), q.id, q.enonce, q.choix, q.bonne, q.explication, q.difficulte
    from (
      select * from (
        select distinct on (qq.fiche_id) qq.*
          from public.questions qq
          join (select id from public.fiches order by rang nulls last, date desc limit (case when niv is null then 20 else 40 end)) f
            on f.id = qq.fiche_id
         where niv is null or qq.difficulte = niv
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
    'questions', (select jsonb_agg(jsonb_build_object('id', question_id, 'position', position, 'enonce', enonce, 'choix', choix, 'difficulte', difficulte) order by position)
                    from public.test_questions where test_id = tid),
    'deja', '[]'::jsonb);
end $$;
revoke execute on function public.demarrer_test(int, int) from public, anon;
grant execute on function public.demarrer_test(int, int) to authenticated;

-- soumettre_test : renvoie aussi le niveau de chaque question (détail par niveau en fin de test)
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
                 'reponse', reponse, 'explication', explication, 'difficulte', difficulte) order by position)
               from public.test_questions where test_id = p_test));
end $$;
revoke execute on function public.soumettre_test(uuid, jsonb) from public, anon;
grant execute on function public.soumettre_test(uuid, jsonb) to authenticated;
