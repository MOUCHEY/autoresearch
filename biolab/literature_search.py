"""
literature_search.py — Recherche bibliographique et vérification des références.

Sources interrogées (API publiques et gratuites, aucune clé nécessaire) :
  pubmed  : NCBI E-utilities (articles biomédicaux publiés)
  europepmc : Europe PMC, filtre "preprints" (couvre bioRxiv / medRxiv)
  arxiv   : arXiv (prépublications en informatique, physique, q-bio)
  crossref: vérification d'un DOI (titre, auteurs, année, revue)

Principe d'honnêteté : ce script récupère UNIQUEMENT des métadonnées
(titre, auteurs, année, DOI, résumé). Les champs d'analyse critique
(méthode, limites, hypothèse dérivée...) sont laissés "À COMPLÉTER APRÈS
LECTURE" : ils ne sont jamais générés automatiquement.

Exemples :
    python literature_search.py search "aqueous solubility prediction random forest" --source pubmed -n 5
    python literature_search.py search "solubility graph neural network" --source arxiv -n 5
    python literature_search.py search "cellular senescence transcriptomics" --source europepmc --preprints
    python literature_search.py verify 10.1021/ci034243x
    python literature_search.py verify-file literature_review.md   # vérifie tous les DOI d'un fichier

Remarque : ce script n'a PAS pu être testé contre les vrais serveurs depuis
l'environnement cloud où il a été écrit (réseau restreint). Testez-le d'abord
sur votre ordinateur avec une petite requête.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

USER_AGENT = "AutoResearchBiology/1.0 (projet pedagogique; python-urllib)"
OUT_DIR = Path(__file__).resolve().parent / "literature" / "search_results"
DOI_RE = re.compile(r"\b10\.\d{4,9}/[^\s\"<>|)\]]+", re.IGNORECASE)


def _get(url: str, params: dict | None = None, timeout: int = 30) -> bytes:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------
def search_pubmed(query: str, n: int = 5) -> list[dict]:
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    ids = json.loads(_get(f"{base}/esearch.fcgi", {"db": "pubmed", "term": query, "retmax": n,
                                                   "retmode": "json", "sort": "relevance"}))["esearchresult"]["idlist"]
    if not ids:
        return []
    time.sleep(0.4)  # NCBI demande au plus 3 requêtes/seconde sans clé
    summ = json.loads(_get(f"{base}/esummary.fcgi", {"db": "pubmed", "id": ",".join(ids), "retmode": "json"}))["result"]
    time.sleep(0.4)
    abstracts = _pubmed_abstracts(ids)
    out = []
    for pmid in ids:
        r = summ.get(pmid, {})
        doi = next((a["value"] for a in r.get("articleids", []) if a.get("idtype") == "doi"), "")
        out.append({"source": "PubMed", "id": f"PMID:{pmid}", "title": r.get("title", ""),
                    "authors": [a["name"] for a in r.get("authors", [])], "year": r.get("pubdate", "")[:4],
                    "venue": r.get("fulljournalname", ""), "doi": doi,
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", "abstract": abstracts.get(pmid, "")})
    return out


def _pubmed_abstracts(ids: list[str]) -> dict[str, str]:
    xml = _get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
               {"db": "pubmed", "id": ",".join(ids), "rettype": "abstract", "retmode": "xml"})
    out = {}
    for art in ET.fromstring(xml).iter("PubmedArticle"):
        pmid = art.findtext(".//PMID")
        parts = ["".join(t.itertext()) for t in art.iter("AbstractText")]
        out[pmid] = " ".join(parts)
    return out


def search_europepmc(query: str, n: int = 5, preprints_only: bool = False) -> list[dict]:
    q = f"({query}) AND SRC:PPR" if preprints_only else query
    data = json.loads(_get("https://www.ebi.ac.uk/europepmc/webservices/rest/search",
                           {"query": q, "format": "json", "pageSize": n, "resultType": "core"}))
    out = []
    for r in data.get("resultList", {}).get("result", []):
        doi = r.get("doi", "")
        out.append({"source": "Europe PMC" + (" (preprint)" if r.get("source") == "PPR" else ""),
                    "id": f"{r.get('source')}:{r.get('id')}", "title": r.get("title", ""),
                    "authors": [a.strip() for a in r.get("authorString", "").split(",") if a.strip()],
                    "year": r.get("pubYear", ""), "venue": r.get("journalTitle", "") or r.get("source", ""),
                    "doi": doi, "url": f"https://doi.org/{doi}" if doi else "",
                    "abstract": re.sub("<[^>]+>", "", r.get("abstractText", ""))})
    return out


def search_arxiv(query: str, n: int = 5) -> list[dict]:
    xml = _get("https://export.arxiv.org/api/query",
               {"search_query": f"all:{query}", "start": 0, "max_results": n, "sortBy": "relevance"})
    ns = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    out = []
    for e in ET.fromstring(xml).findall("a:entry", ns):
        url = e.findtext("a:id", default="", namespaces=ns)
        out.append({"source": "arXiv", "id": url.rsplit("/", 1)[-1], "title": " ".join(e.findtext("a:title", "", ns).split()),
                    "authors": [a.findtext("a:name", "", ns) for a in e.findall("a:author", ns)],
                    "year": e.findtext("a:published", "", ns)[:4], "venue": "arXiv (prépublication, non relue)",
                    "doi": e.findtext("arxiv:doi", "", ns), "url": url,
                    "abstract": " ".join(e.findtext("a:summary", "", ns).split())})
    return out


def verify_doi(doi: str) -> dict:
    """Interroge Crossref : renvoie les métadonnées officielles du DOI, ou une erreur."""
    try:
        msg = json.loads(_get(f"https://api.crossref.org/works/{urllib.parse.quote(doi)}"))["message"]
    except Exception as exc:  # DOI inexistant (404) ou réseau indisponible
        return {"doi": doi, "verified": False, "error": str(exc)}
    year = (msg.get("issued", {}).get("date-parts") or [[None]])[0][0]
    return {"doi": doi, "verified": True, "title": (msg.get("title") or [""])[0],
            "authors": [f"{a.get('given', '')} {a.get('family', '')}".strip() for a in msg.get("author", [])],
            "year": year, "venue": (msg.get("container-title") or [""])[0]}


# ---------------------------------------------------------------------------
# Fiches de lecture
# ---------------------------------------------------------------------------
CARD = """### {title}
- **Auteurs** : {authors}
- **Année** : {year} · **Revue/serveur** : {venue}
- **DOI / URL** : {doi} {url}
- **Statut de vérification** : métadonnées récupérées automatiquement depuis {source} ({id}) le {today}
- **Question scientifique** : À COMPLÉTER APRÈS LECTURE
- **Méthode** : À COMPLÉTER APRÈS LECTURE
- **Données disponibles ?** : À COMPLÉTER APRÈS LECTURE
- **Résultats principaux** : À COMPLÉTER APRÈS LECTURE (ne pas se fier au seul résumé)
- **Limites / risques de biais** : À COMPLÉTER APRÈS LECTURE
- **Reproductibilité (code, données, protocole)** : À COMPLÉTER APRÈS LECTURE
- **Hypothèse expérimentale dérivée** : À COMPLÉTER APRÈS LECTURE

<details><summary>Résumé (tel que fourni par la source)</summary>

{abstract}
</details>
"""


def to_cards(records: list[dict]) -> str:
    today = dt.date.today().isoformat()
    cards = []
    for r in records:
        authors = ", ".join(r["authors"][:6]) + (" et al." if len(r["authors"]) > 6 else "")
        cards.append(CARD.format(today=today, **{**r, "authors": authors or "?",
                                                "abstract": r["abstract"] or "(pas de résumé)"}))
    return "\n".join(cards)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search")
    s.add_argument("query")
    s.add_argument("--source", choices=["pubmed", "europepmc", "arxiv"], default="pubmed")
    s.add_argument("--preprints", action="store_true", help="Europe PMC : prépublications seulement (bioRxiv...)")
    s.add_argument("-n", type=int, default=5)
    v = sub.add_parser("verify"); v.add_argument("doi")
    vf = sub.add_parser("verify-file"); vf.add_argument("path")
    a = ap.parse_args()

    if a.cmd == "search":
        if a.source == "pubmed":
            recs = search_pubmed(a.query, a.n)
        elif a.source == "europepmc":
            recs = search_europepmc(a.query, a.n, a.preprints)
        else:
            recs = search_arxiv(a.query, a.n)
        text = f"# Recherche « {a.query} » ({a.source}, {dt.date.today()})\n\n" + to_cards(recs)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "_", a.query.lower())[:50]
        path = OUT_DIR / f"{dt.date.today()}_{a.source}_{slug}.md"
        path.write_text(text, encoding="utf-8")
        for r in recs:
            print(f"- [{r['year']}] {r['title']} — {r['doi'] or r['url']}")
        print(f"\n{len(recs)} fiches écrites dans {path}")
    elif a.cmd == "verify":
        print(json.dumps(verify_doi(a.doi), indent=1, ensure_ascii=False))
    else:
        dois = sorted(set(m.rstrip(".,;") for m in DOI_RE.findall(Path(a.path).read_text(encoding="utf-8"))))
        for d in dois:
            r = verify_doi(d)
            status = "OK " if r["verified"] else "ÉCHEC"
            print(f"[{status}] {d} — {r.get('title') or r.get('error')}")
            time.sleep(0.2)


if __name__ == "__main__":
    main()
