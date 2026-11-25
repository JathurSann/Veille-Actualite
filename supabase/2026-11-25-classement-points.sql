-- Classement par points, départage à l'heure de fin, tag « Refait »
-- À coller dans Supabase > SQL Editor, puis Run. Sans risque : ne change que la fonction classement.
--
-- Règles :
--  * 1 bonne réponse = 1 point
--  * on retient le meilleur test de chaque personne (pour le format et le jour)
--  * à égalité de points, celui qui a terminé son test en premier passe devant
--  * nb_essais > 1 : la personne a refait le test ; la page affiche le tag « Refait »

drop function if exists public.classement(int, date);

create function public.classement(p_format int, p_jour date default null)
returns table (rang bigint, pseudo text, points int, total int, termine_a timestamptz, nb_essais int, moi boolean)
language sql stable security definer set search_path = '' as $$
  with fin as (
    select t.user_id, t.score, t.total, t.finished_at
      from public.tests t
     where t.finished_at is not null
       and t.format = p_format
       and t.jour = coalesce(p_jour, (now() at time zone 'Europe/Paris')::date)
  ),
  best as (
    select distinct on (f.user_id)
           f.user_id, f.score, f.total, f.finished_at,
           (select count(*) from fin x where x.user_id = f.user_id)::int as essais
      from fin f
     order by f.user_id, f.score desc, f.finished_at asc
  )
  select row_number() over (order by b.score desc, b.finished_at asc, p.pseudo)::bigint,
         p.pseudo, b.score, b.total, b.finished_at, b.essais, (b.user_id = auth.uid())
    from best b join public.profiles p on p.id = b.user_id
   order by 1
   limit 100;
$$;
revoke execute on function public.classement(int, date) from public, anon;
grant execute on function public.classement(int, date) to authenticated;
