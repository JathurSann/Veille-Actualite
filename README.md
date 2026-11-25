# Veille-Actualite

Veille d'actualité hebdomadaire pour le QCM d'actualité (Sup de Pub) : fiches de révision sur les sujets traités à la fois par la presse écrite, la télévision et la radio, sur deux semaines glissantes (semaine en cours + semaine passée).

## Contenu

- `index.html` : la page (une seule page, sans dépendance). Elle lit `data/fiches.json` quand elle n'est pas ouverte dans l'artefact Claude.
- `data/fiches.json` : les fiches, mises à jour chaque matin (tableau d'objets, une fiche par sujet).
- `collecteur/collecteur.py` : collecte les flux RSS de 17 médias (presse, tv, radio) et regroupe les articles par sujet. Bibliothèque standard uniquement.

```
python3 collecteur/collecteur.py 12 60 > sujets.json
```

## Format d'une fiche

`id`, `titre`, `rubrique` (politique, economie, societe, international, sciences, culture, sport, medias, environnement), `date` (AAAA-MM-JJ), `ajoute`, `croise` (bool), `resume`, `retenir[]`, `contexte`, `acteurs[]`, `echeances[{date,label}]`, `sources[{nom,type,url}]`.

## Mise à jour

Une tâche planifiée tourne chaque matin à 6h34 (Paris) : collecte, rédaction des fiches, suppression de celles qui sortent de la fenêtre de deux semaines, puis écriture de `data/fiches.json`.

## Suite prévue

Comptes utilisateurs, suivi par personne, questionnaire de test après lecture des fiches, classement quotidien.
