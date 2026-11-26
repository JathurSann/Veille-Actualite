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
Fonctions : `demarrer_test`, `repondre_question` (correction immédiate), `soumettre_test` (le score est calculé en base), `classement`, `pseudo_disponible`, `verifier_inscription`.

- Inscription : email + mot de passe (10 caractères minimum) + pseudo + code d'accès. Pas de confirmation par email (pas de domaine pour un SMTP propre). Pour changer le code : `update public.config set valeur = '...' where cle = 'code_acces';`
- Secret GitHub requis : `SUPABASE_SERVICE_KEY` (clé secrète `sb_secret_...` du projet). Ne jamais la mettre dans le code ni dans le chat.
- Test manuel de la synchronisation : onglet Actions → « Synchroniser les fiches vers Supabase » → Run workflow (champ `fichier`, par exemple `data/exemple-fiches.json`).

## Format d'une fiche

`id`, `titre`, `rubrique` (politique, economie, societe, international, sciences, culture, sport, medias, environnement), `date` (AAAA-MM-JJ), `ajoute`, `croise` (bool), `resume`, `retenir[]`, `contexte`, `acteurs[]`, `echeances[{date,label}]`, `sources[{nom,type,url}]`.

Champ optionnel `questions[]` : `{enonce, choix[2 à 5], bonne (index du bon choix), explication}`. Une question par fiche suffit : le test en tire une par sujet parmi les 20 plus couverts.

## Test et classement

Deux modes, à lancer à tout moment :

- **Test du jour** : 20 questions, les mêmes pour tout le monde (une par sujet parmi les plus couverts, choisies et ordonnées de façon fixe pour la journée). C'est le seul test classé.
- **Entraînement** : 5 ou 10 questions tirées au hasard, sans classement.

Classement du jour : 1 bonne réponse = 1 point. Le premier test terminé de chaque personne compte. À égalité de points, celui qui a terminé en premier passe devant. Une personne qui refait le test du jour reçoit le tag « Refait ×N ». Le SQL est dans `supabase/2026-11-25-test-du-jour.sql` (à lancer une fois dans Supabase > SQL Editor ; la page reste compatible avec l'ancienne version tant que ce n'est pas fait).

## Apparence

Mode clair ou sombre : automatique par défaut (réglage de l'appareil), modifiable avec le bouton soleil/lune ou dans le menu du compte. Le choix est gardé dans le navigateur.

**Correction immédiate** : on choisit une réponse, on valide, la page dit Juste/Faux avec la bonne réponse et une courte explication. La réponse est définitive (pas de retour en arrière) et enregistrée en base. Un test du jour commencé mais pas fini est repris à la première question sans réponse. SQL à coller une fois : `supabase/2026-11-26-correction-immediate.sql`. Sans ce SQL, la page retombe sur l'ancien fonctionnement (correction à la fin).
