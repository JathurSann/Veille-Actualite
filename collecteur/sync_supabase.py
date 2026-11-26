#!/usr/bin/env python3
"""Copie data/fiches.json dans Supabase (fiches + questions de test).

Variables d'environnement :
  SUPABASE_URL         ex. https://xxxx.supabase.co
  SUPABASE_SECRET_KEY  clé secrète (sb_secret_...), à garder dans les secrets GitHub
Argument optionnel : chemin du fichier JSON (par défaut data/fiches.json).

Règles :
- On ne garde que la fenêtre « semaine en cours + semaine passée » (comme la page).
- Le rang (1 = sujet le plus couvert) est calculé ici, avec la même règle que la page :
  recoupé presse/télé/radio d'abord, puis nombre de familles de médias, puis nombre de médias.
- Les fiches sorties de la fenêtre sont supprimées de la base (leurs questions aussi).
- Si le JSON d'une fiche contient « questions », elles remplacent celles de la base pour cette fiche.
  Sans « questions », celles déjà en base sont conservées.
- Un fichier vide ou illisible ne supprime jamais rien.
"""
import datetime as dt
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

RUBRIQUES = {"politique", "economie", "societe", "international", "sciences",
             "culture", "sport", "medias", "environnement"}
URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
KEY = os.environ.get("SUPABASE_SECRET_KEY", "")


def api(method, path, body=None, prefer=None):
    headers = {"apikey": KEY, "Content-Type": "application/json"}
    if prefer:
        headers["Prefer"] = prefer
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(f"{URL}/rest/v1/{path}", data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        sys.exit(f"Erreur Supabase {e.code} sur {method} {path} : {detail}")


_DIFF = None


def has_difficulte():
    """Vrai si la colonne questions.difficulte existe (SQL du 26/11 lancé). Sinon on n'envoie pas le champ."""
    global _DIFF
    if _DIFF is None:
        req = urllib.request.Request(f"{URL}/rest/v1/questions?select=difficulte&limit=1", headers={"apikey": KEY})
        try:
            urllib.request.urlopen(req, timeout=30).read()
            _DIFF = True
        except urllib.error.HTTPError:
            _DIFF = False
            print("Colonne questions.difficulte absente : niveau ignoré (lancer le SQL du 26/11).", file=sys.stderr)
    return _DIFF


def media_key(nom):
    return re.split(r"\s[:(]|\s–\s", str(nom or ""))[0].strip().lower()


def score(f):
    fam = {s.get("type") for s in f.get("sources", []) if isinstance(s, dict)} & {"presse", "tv", "radio"}
    medias = {media_key(s.get("nom")) for s in f.get("sources", []) if isinstance(s, dict) and s.get("nom")} - {""}
    return (1000 if f.get("croise") is True else 0) + len(fam) * 100 + len(medias)


def fiche_id(f):
    if f.get("id"):
        return str(f["id"])
    return hashlib.sha1(f"{f.get('date')}|{f.get('titre')}".encode("utf-8")).hexdigest()[:12]


def clean_questions(f):
    out = []
    for q in f.get("questions") or []:
        choix = q.get("choix")
        bonne = q.get("bonne")
        if (isinstance(q.get("enonce"), str) and isinstance(choix, list) and 2 <= len(choix) <= 5
                and all(isinstance(c, str) and c for c in choix)
                and isinstance(bonne, int) and 0 <= bonne < len(choix)):
            row = {"fiche_id": fiche_id(f), "enonce": q["enonce"].strip(), "choix": choix,
                   "bonne": bonne, "explication": (q.get("explication") or "").strip() or None}
            if has_difficulte():
                d = q.get("difficulte")
                row["difficulte"] = d if d in (1, 2, 3) else 2
            out.append(row)
        else:
            print(f"Question ignorée (format invalide) sur la fiche {fiche_id(f)}", file=sys.stderr)
    return out


def main():
    if not URL or not KEY:
        sys.exit("SUPABASE_URL et SUPABASE_SECRET_KEY sont requis.")
    path = sys.argv[1] if len(sys.argv) > 1 else "data/fiches.json"
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError) as e:
        sys.exit(f"Fichier illisible ({e}) : rien n'est modifié.")
    fiches = raw if isinstance(raw, list) else (raw or {}).get("fiches", [])

    today = dt.datetime.now(ZoneInfo("Europe/Paris")).date()
    limite = today - dt.timedelta(days=today.weekday() + 7)  # lundi de la semaine précédente
    ok = []
    for f in fiches:
        if not (isinstance(f, dict) and f.get("titre") and f.get("date")):
            continue
        if f.get("rubrique") not in RUBRIQUES:
            print(f"Fiche ignorée (rubrique inconnue) : {f.get('titre')}", file=sys.stderr)
            continue
        try:
            if dt.date.fromisoformat(f["date"]) < limite:
                continue
        except ValueError:
            continue
        ok.append(f)

    if not ok:
        print("Aucune fiche dans la fenêtre : rien n'est modifié.")
        return

    # Rang : score décroissant, puis date la plus récente (même règle que la page)
    ranked = sorted(sorted(ok, key=lambda f: f["date"], reverse=True), key=lambda f: -score(f))
    rang = {fiche_id(f): i + 1 for i, f in enumerate(ranked)}

    rows = [{
        "id": fiche_id(f), "titre": f["titre"], "rubrique": f["rubrique"], "date": f["date"],
        "ajoute": f.get("ajoute"), "croise": f.get("croise") is True,
        "resume": f.get("resume"), "retenir": f.get("retenir") or [], "contexte": f.get("contexte"),
        "acteurs": f.get("acteurs") or [], "echeances": f.get("echeances") or [],
        "sources": f.get("sources") or [], "rang": rang[fiche_id(f)],
        "maj": dt.datetime.now(dt.timezone.utc).isoformat(),
    } for f in ok]
    api("POST", "fiches?on_conflict=id", rows, prefer="resolution=merge-duplicates,return=minimal")

    # Fiches sorties de la fenêtre : on les supprime (les questions suivent en cascade)
    ids = [r["id"] for r in rows]
    in_list = "(" + ",".join('"' + i.replace('"', "") + '"' for i in ids) + ")"
    api("DELETE", "fiches?id=not.in." + urllib.parse.quote(in_list, safe="(),\""), prefer="return=minimal")

    # Questions : remplacées uniquement pour les fiches qui en fournissent
    avec = [f for f in ok if f.get("questions")]
    for f in avec:
        qs = clean_questions(f)
        if not qs:
            continue
        api("DELETE", "questions?fiche_id=eq." + urllib.parse.quote(fiche_id(f), safe=""), prefer="return=minimal")
        api("POST", "questions", qs, prefer="return=minimal")

    print(f"{len(rows)} fiches synchronisées, questions mises à jour pour {len(avec)} fiches.")


if __name__ == "__main__":
    main()
