# Veille-Actualite

Veille d'actualité hebdomadaire pour le QCM d'actualité (Sup de Pub) : fiches de révision sur les sujets traités à la fois par la presse écrite, la télévision et la radio, sur deux semaines glissantes (semaine en cours + semaine passée). Comptes, suivi de révision par personne, test d'actualité avec score et classement quotidien.

## Architecture

```
tâche planifiée 6h34  →  data/fiches.json (main)  →  GitHub Action  →  Supabase  ←  index.html (GitHub Pages)
```

- `index.html` : la page, publiée sur GitHub Pages. Elle se connecte à Supabase avec la clé **publishable** (publique par conception ; la sécurité vient des règles d'accès RLS).
- `vendor/supabase.js` : bibliothèque supabase-js copiée dans le repo (pas de CDN externe).
- `data/fiches.json` : export quotidien des fiches, écrit par la tâche planifiée.
- `collecteur/collecteur.py` : collecte les flux RSS de 17 médias. Bibliothèque standard uniquement.
- `collecteur/sync_supabase.py` + `.github/workflows/sync-supabase.yml` : à chaque changement de `data/fiches.json`, copie les fiches et leurs questions dans Supabase, calcule le rang « les plus couverts » et supprime les fiches sorties de la fenêtre.

```
python3 collecteur/collecteur.py 12 60 > sujets.json
```

## Base Supabase

Tables : `profiles` (pseudo), `fiches`, `questions` (fermée : bonnes réponses jamais envoyées au navigateur), `revisions` (suivi par personne), `tests`, `test_questions` (fermée), `config` (code d'accès, fermée).
Fonctions : `demarrer_test`, `soumettre_test` (le score est calculé en base), `classement`, `pseudo_disponible`, `verifier_inscription`.

- Inscription : email + mot de passe (10 caractères minimum) + pseudo + code d'accès. Pas de confirmation par email (pas de domaine pour un SMTP propre). Pour changer le code : `update public.config set valeur = '...' where cle = 'code_acces';`
- Secret GitHub requis : `SUPABASE_SERVICE_KEY` (clé secrète `sb_secret_...` du projet). Ne jamais la mettre dans le code ni dans le chat.
- Test manuel de la synchronisation : onglet Actions → « Synchroniser les fiches vers Supabase » → Run workflow (champ `fichier`, par exemple `data/exemple-fiches.json`).

## Format d'une fiche

`id`, `titre`, `rubrique` (politique, economie, societe, international, sciences, culture, sport, medias, environnement), `date` (AAAA-MM-JJ), `ajoute`, `croise` (bool), `resume`, `retenir[]`, `contexte`, `acteurs[]`, `echeances[{date,label}]`, `sources[{nom,type,url}]`.

Champ optionnel `questions[]` : `{enonce, choix[2 à 5], bonne (index du bon choix), explication}`. Une question par fiche suffit : le test en tire une par sujet parmi les 20 plus couverts.

## Test et classement

Le test comporte 5, 10 ou 20 questions au choix, une par sujet. On peut le lancer à tout moment. Le classement du jour retient le meilleur test de chaque personne (ratio de bonnes réponses, puis nombre de bonnes réponses, puis temps).
