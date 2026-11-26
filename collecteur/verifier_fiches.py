#!/usr/bin/env python3
"""Contrôle qualité de data/fiches.json, à lancer par la tâche quotidienne AVANT l'export.

Usage : python3 collecteur/verifier_fiches.py [data/fiches.json] [--json]
Code de sortie : 0 si aucun point bloquant, 1 sinon (la tâche corrige puis relance le script).
Bibliothèque standard seulement. Le rang des sujets reprend la règle de sync_supabase.py.
"""
import json, re, sys, collections, datetime as dt

RUBRIQUES = {"politique", "economie", "societe", "international", "sciences",
             "culture", "sport", "medias", "environnement"}
QUOTA = {1: 7, 2: 7, 3: 6}  # test du jour : 20 questions parmi les 40 sujets les plus couverts


def media_key(nom):
    return re.split(r"\s[:(]|\s–\s", str(nom or ""))[0].strip().lower()


def score(f):
    srcs = [s for s in f.get("sources", []) if isinstance(s, dict)]
    fam = {s.get("type") for s in srcs} & {"presse", "tv", "radio"}
    medias = {media_key(s.get("nom")) for s in srcs if s.get("nom")} - {""}
    return (1000 if f.get("croise") is True else 0) + len(fam) * 100 + len(medias)


def phrases(txt):
    return [p for p in re.split(r"(?<=[.!?])\s+", (txt or "").strip()) if p]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    path = args[0] if args else "data/fiches.json"
    as_json = "--json" in sys.argv
    fiches = json.load(open(path, encoding="utf-8"))
    bloquants, avertissements = [], []

    ranked = sorted(sorted(fiches, key=lambda f: f.get("date", ""), reverse=True), key=lambda f: -score(f))
    avec_q = [f for f in ranked if f.get("questions")]
    top40 = avec_q[:40]
    top20 = ranked[:20]

    niveaux_all, niveaux_top = collections.Counter(), collections.Counter()
    nb_q = 0
    for f in fiches:
        fid = f.get("id") or f.get("titre")
        if f.get("rubrique") not in RUBRIQUES:
            bloquants.append(f"{fid} : rubrique inconnue")
        for i, q in enumerate(f.get("questions") or []):
            nb_q += 1
            ch, b = q.get("choix"), q.get("bonne")
            if not (isinstance(ch, list) and len(ch) == 4 and all(isinstance(c, str) and c for c in ch)):
                bloquants.append(f"{fid} q{i+1} : il faut 4 choix")
            if not (isinstance(b, int) and 0 <= b < 4):
                bloquants.append(f"{fid} q{i+1} : `bonne` invalide")
            if q.get("difficulte") not in (1, 2, 3):
                bloquants.append(f"{fid} q{i+1} : `difficulte` manquant (1, 2 ou 3)")
            else:
                niveaux_all[q["difficulte"]] += 1
            ex = q.get("explication") or ""
            if len(phrases(ex)) < 2 or len(ex) < 120:
                bloquants.append(f"{fid} q{i+1} : explication trop courte (2 phrases, 150-260 caractères)")
            elif len(ex) > 330:
                avertissements.append(f"{fid} q{i+1} : explication longue ({len(ex)} car.)")
            if isinstance(ch, list) and isinstance(b, int) and 0 <= b < len(ch):
                lens = [len(str(c)) for c in ch]
                if lens[b] == max(lens) and max(lens) > 1.8 * (sum(lens) - max(lens)) / 3:
                    avertissements.append(f"{fid} q{i+1} : la bonne réponse est bien plus longue que les autres (devinable)")
                if len({str(c).strip().lower() for c in ch}) < 4:
                    bloquants.append(f"{fid} q{i+1} : choix en double")
            if re.search(r"récemment|actuellement|cette semaine|aujourd'hui", q.get("enonce", ""), re.I):
                avertissements.append(f"{fid} q{i+1} : énoncé non daté (récemment / actuellement / cette semaine)")
            if i == 1 and (f["questions"][0].get("enonce") == q.get("enonce") or f["questions"][0].get("bonne") == b and ch == f["questions"][0].get("choix")):
                bloquants.append(f"{fid} : les 2 questions sont des doublons")

    for f in top40:
        q = f["questions"][0]
        if q.get("difficulte") in (1, 2, 3):
            niveaux_top[q["difficulte"]] += 1
    manque = {n: max(0, QUOTA[n] - niveaux_top[n]) for n in QUOTA}
    for n, m in manque.items():
        if m:
            bloquants.append(f"top 40 : il manque {m} question(s) de niveau {n} (objectif {QUOTA[n]}, actuel {niveaux_top[n]})")

    for f in top20:
        if not f.get("questions"):
            bloquants.append(f"{f.get('id')} : sujet du top 20 sans question")
    for f in fiches:
        if f.get("croise") is True and not f.get("questions"):
            bloquants.append(f"{f.get('id')} : fiche croisée sans question")
    if sum(1 for f in fiches if f.get("questions")) < 25:
        bloquants.append("moins de 25 fiches avec questions")

    jours = collections.Counter(f.get("date") for f in fiches)
    rubs = collections.Counter(f.get("rubrique") for f in fiches)
    for r in sorted(RUBRIQUES):
        if rubs[r] < 3:
            avertissements.append(f"rubrique {r} : {rubs[r]} fiche(s) (minimum 3)")
    if jours:
        d0 = dt.date.fromisoformat(min(jours))
        d1 = dt.date.fromisoformat(max(jours))
        d = d0
        while d <= d1:
            if jours[d.isoformat()] < 6:
                avertissements.append(f"jour {d.isoformat()} : {jours[d.isoformat()]} fiche(s) (minimum 6)")
            d += dt.timedelta(days=1)

    # Rotation d'audit : un tiers des fiches non croisées à relire chaque jour (par numéro de jour)
    reste = [f for f in fiches if f.get("questions") and f not in top20]
    tranche = [f.get("id") for k, f in enumerate(reste) if k % 3 == dt.date.today().toordinal() % 3]

    res = {
        "fiches": len(fiches), "fiches_avec_questions": sum(1 for f in fiches if f.get("questions")),
        "questions": nb_q, "niveaux_toutes": dict(sorted(niveaux_all.items())),
        "niveaux_top40": dict(sorted(niveaux_top.items())),
        "bloquants": bloquants, "avertissements": avertissements,
        "a_relire_aujourdhui": tranche,
        "top20": [f.get("id") for f in top20],
    }
    if as_json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        print(f"{res['fiches']} fiches, {res['fiches_avec_questions']} avec questions, {nb_q} questions")
        print(f"Niveaux (toutes) : {res['niveaux_toutes']} ; top 40 : {res['niveaux_top40']} (objectif 7/7/6)")
        print(f"\nBLOQUANTS ({len(bloquants)})"); [print(" -", b) for b in bloquants]
        print(f"\nAVERTISSEMENTS ({len(avertissements)})"); [print(" -", a) for a in avertissements]
        print(f"\nÀ relire aujourd'hui (rotation, hors top 20) : {len(tranche)} fiches")
        [print(" -", t) for t in tranche]
    sys.exit(1 if bloquants else 0)


if __name__ == "__main__":
    main()
