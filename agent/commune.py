"""Fiche de la commune : données officielles (geo.api.gouv.fr) + prix DVF + résumé Gemini (estimation)."""
import json, re
import requests
from . import llm, neighborhood
from .util import HEADERS

def info(citycode):
    if not citycode or not re.fullmatch(r"\d{5}|2[AB]\d{3}", str(citycode)): return None
    try:
        r = requests.get(f"https://geo.api.gouv.fr/communes/{citycode}", headers=HEADERS, timeout=15,
                         params={"fields": "nom,code,population,surface,codesPostaux,departement,region"})
        return r.json() if r.status_code == 200 else None
    except (requests.RequestException, ValueError):
        return None

def analyze(geo, analysis, cfg, cache):
    ci = info(geo.get("citycode"))
    out = {"nom": geo.get("city"), "stats": None, "summary": None}
    if ci:
        pop, surf = ci.get("population"), ci.get("surface")      # surface en hectares
        out["nom"] = ci.get("nom") or out["nom"]
        out["stats"] = {"population": pop, "departement": (ci.get("departement") or {}).get("nom"),
                        "region": (ci.get("region") or {}).get("nom"),
                        "densite": round(pop / (surf / 100)) if pop and surf else None}
    median = analysis.get("median_m2") if analysis else None
    if median is None:
        median = neighborhood.dvf_median_m2(geo["lat"], geo["lon"])
    out["median_m2"] = median
    key = f"commune:{geo.get('citycode') or out['nom']}"
    if key in cache:
        out["summary"] = cache[key]
    elif cfg["gemini"]["use_for_neighborhood"] and out["nom"]:
        facts = {"commune": out["nom"], "stats": out["stats"], "prix_vente_median_m2_secteur": median,
                 "risques_officiels": (analysis or {}).get("risks"),
                 "transports_futurs": [i["project"] for i in ((analysis or {}).get("future") or {}).get("items", [])]}
        prompt = f"""Tu es un conseiller immobilier en France. Présente la commune « {out['nom']} » à quelqu'un qui cherche à y habiter.
FAITS MESURÉS (fiables) : {json.dumps(facts, ensure_ascii=False)}
Réponds en JSON avec : profil (2 phrases : taille, caractère, public), atouts (3 max), limites (3 max),
immobilier (1-2 phrases prudentes sur le marché local, sans inventer de chiffre), vie_quotidienne (1 phrase : commerces,
équipements, emploi à proximité).
Règles : distingue ce qui vient des FAITS de ce qui vient de ta connaissance générale (impressions non vérifiées) ;
n'invente aucun chiffre ; si tu connais mal cette commune, dis-le dans profil."""
        res = llm.generate_json(prompt, cfg["gemini"]["model"])
        if res:
            cache[key] = res; out["summary"] = res
    return out
