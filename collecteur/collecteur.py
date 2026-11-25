#!/usr/bin/env python3
"""Collecte les flux RSS de médias français, regroupe les articles par sujet et affiche
les sujets les plus couverts, avec la famille de chaque média (presse, tv, radio).
Usage : python3 collecteur.py [jours=10] [max_sujets=40]   (bibliothèque standard uniquement)"""
import sys, re, json, math, unicodedata, html, urllib.request, xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

FEEDS = [  # (média, famille, url)
 ("Le Monde","presse","https://www.lemonde.fr/rss/une.xml"),
 ("Libération","presse","https://www.liberation.fr/arc/outboundfeeds/rss-all/?outputType=xml"),
 ("Le Figaro","presse","https://www.lefigaro.fr/rss/figaro_actualites-a-la-une.xml"),
 ("Ouest-France","presse","https://www.ouest-france.fr/rss/une"),
 ("20 Minutes","presse","https://www.20minutes.fr/feeds/rss-une.xml"),
 ("Les Échos","presse","https://www.lesechos.fr/rss/rss_une.xml"),
 ("franceinfo","tv","https://www.franceinfo.fr/titres.rss"),
 ("France 24","tv","https://www.france24.com/fr/rss"),
 ("TF1 Info","tv","https://www.tf1info.fr/feeds/rss-une.xml"),
 ("BFMTV","tv","https://www.bfmtv.com/rss/news-24-7/"),
 ("LCP","tv","https://lcp.fr/rss.xml"),
 ("Public Sénat","tv","https://www.publicsenat.fr/rss"),
 ("Europe 1","radio","https://www.europe1.fr/rss.xml"),
 ("France Inter","radio","https://www.radiofrance.fr/franceinter/rss"),
 ("RMC","radio","https://rmc.bfmtv.com/rss/actualites/"),
 ("RFI","radio","https://www.rfi.fr/fr/rss"),
 ("Sud Radio","radio","https://www.sudradio.fr/feed"),
]
H = {"User-Agent": "Mozilla/5.0 (compatible; veille-etudiante/1.0)"}
STOP = set("""a au aux avec ce ces dans de des du elle en et il ils je la le les leur lui mais me mes moi mon ne nos notre nous on ou par pas pour qu que qui sa sans se ses si son sont sur te tes ton tu un une vos votre vous cette cet donc apres avant aussi alors ainsi entre depuis selon comme plus moins peut apres direct video live suivi france francais monde lundi mardi mercredi jeudi vendredi samedi dimanche octobre novembre ete etre fait font voici avoir tout tous toute toutes""".split())

def clean(t): return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]+>"," ",t or ""))).strip()
def tokens(t):
    n = unicodedata.normalize("NFKD", clean(t)).encode("ascii","ignore").decode().lower()
    out=set()
    for w in re.findall(r"[a-z0-9]{3,}", n):
        if w.isdigit(): continue
        w = w[:-1] if len(w)>4 and w.endswith("s") else w
        if w not in STOP: out.add(w)
    return out
def pdate(s):
    if not s: return None
    try:
        d = parsedate_to_datetime(s)
    except Exception:
        try: d = datetime.fromisoformat(s.replace("Z","+00:00"))
        except Exception: return None
    if d.tzinfo is None: d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)

def fetch(f):
    nom, fam, url = f
    try:
        raw = urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=20).read()
        root = ET.fromstring(raw)
    except Exception as e:
        return nom, [], f"{type(e).__name__}: {str(e)[:60]}"
    A = "{http://www.w3.org/2005/Atom}"; arts=[]
    for it in root.findall(".//item")+root.findall(f".//{A}entry"):
        def g(*names):
            for n in names:
                e = it.find(n)
                if e is not None and (e.text or e.get("href")): return e.text or e.get("href")
            return ""
        title = clean(g("title", A+"title")); link = g("link", A+"link", "guid").strip()
        d = pdate(g("pubDate", "{http://purl.org/dc/elements/1.1/}date", A+"published", A+"updated"))
        if title and link.startswith("http"):
            arts.append({"media":nom,"famille":fam,"titre":title,"url":link.split("?utm")[0],"date":d,"resume":clean(g("description",A+"summary"))[:300]})
    return nom, arts, ""

def main():
    jours = int(sys.argv[1]) if len(sys.argv)>1 else 10
    top = int(sys.argv[2]) if len(sys.argv)>2 else 40
    now = datetime.now(timezone.utc); debut = now - timedelta(days=jours)
    with ThreadPoolExecutor(8) as ex: res = list(ex.map(fetch, FEEDS))
    arts=[]; etat={}
    for nom, a, err in res:
        etat[nom] = err or f"{len(a)} articles"; arts += a
    arts = [a for a in arts if not a["date"] or a["date"] >= debut]
    for a in arts:
        a["tt"]=tokens(a["titre"]); a["ta"]=tokens(a["titre"]+" "+a["resume"])
    n=len(arts); df={}
    for a in arts:
        for t in a["ta"]: df[t]=df.get(t,0)+1
    idf={t:math.log(1+(n+1)/(f+1)) for t,f in df.items()}
    w=lambda s: sum(idf.get(t,1) for t in s)
    def liees(a,b):
        st=a["tt"]&b["tt"]; m=min(w(a["tt"]),w(b["tt"]))
        if len(st)>=2 and m and w(st)/m>=0.30: return True
        sa=a["ta"]&b["ta"]
        if len(sa)<3: return False
        m=min(w(a["ta"]),w(b["ta"])); u=w(a["ta"]|b["ta"])
        return bool(m and u and w(sa)/m>=0.34 and w(sa)/u>=0.10)
    P=list(range(n))
    def find(x):
        while P[x]!=x: P[x]=P[P[x]]; x=P[x]
        return x
    for i in range(n):
        for j in range(i+1,n):
            if liees(arts[i],arts[j]): P[find(j)]=find(i)
    g={}
    for i,a in enumerate(arts): g.setdefault(find(i),[]).append(a)
    sujets=[]
    for grp in g.values():
        medias=sorted({a["media"] for a in grp}); fams=sorted({a["famille"] for a in grp})
        sujets.append({"nb_medias":len(medias),"familles":fams,"croise":len(fams)==3,"medias":medias,
          "plus_recent":max((a["date"] for a in grp if a["date"]),default=now).isoformat(),
          "articles":[{"media":a["media"],"famille":a["famille"],"titre":a["titre"],"url":a["url"],"resume":a["resume"],"date":a["date"].isoformat() if a["date"] else None} for a in sorted(grp,key=lambda a:a["media"])]})
    sujets.sort(key=lambda s:(s["croise"],s["nb_medias"],s["plus_recent"]),reverse=True)
    print(json.dumps({"genere":now.isoformat(),"flux":etat,"nb_articles":n,"sujets":sujets[:top]},ensure_ascii=False,indent=1))
main()
