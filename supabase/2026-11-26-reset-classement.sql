-- Remise à zéro du classement d'aujourd'hui (tests du jour de la date de Paris).
-- À coller une fois dans Supabase > SQL Editor. Ne touche ni aux fiches, ni aux comptes, ni aux révisions.
delete from public.test_questions
 where test_id in (select id from public.tests
                    where jour = (now() at time zone 'Europe/Paris')::date);
delete from public.tests
 where jour = (now() at time zone 'Europe/Paris')::date;
