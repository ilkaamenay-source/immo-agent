"""Page d'annonce -> dict normalisé.
Étape 1 (gratuite) : JSON-LD / balises og: / regex.
Étape 2 (Gemini)   : complète les champs manquants, seulement pour les annonces qui ont passé le pré-filtre."""
import json, re
import requests
from bs4 import BeautifulSoup
from . import llm
from .util import HEADERS, to_number

FIELDS = ["title", "price", "charges", "surface", "rooms", "floor", "has_elevator", "dpe",
          "address", "city", "zipcode", "furnished", "description"]

def fetch_page(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200 or len(r.text) < 500:
            print(f"  [page] HTTP {r.status_code} -> repli sur le texte de l'email")
            return None
        return r.text
    except requests.RequestException as e:
        print(f"  [page] {e}")
        return None

def _jsonld(soup):
    out = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        out.extend(data if isinstance(data, list) else [data])
    return out

def heuristics(text):
    """Regex simples sur un texte brut. Renvoie ce qu'on trouve, sans rien inventer."""
    d = {}
    t = text.replace("\u202f", " ").replace("\xa0", " ")
    m = re.search(r"(\d{1,3}(?:[ .]\d{3})+|\d{3,8})\s*€", t)
    if m: d["price"] = to_number(m.group(1))
    m = re.search(r"(\d{1,3}(?:[,.]\d+)?)\s*m[²2]", t)
    if m: d["surface"] = to_number(m.group(1))
    m = re.search(r"(\d+)\s*pi[èe]ces?", t, re.I)
    if m: d["rooms"] = int(m.group(1))
    if re.search(r"rez[- ]de[- ]chauss[ée]e|\brdc\b", t, re.I): d["floor"] = 0
    m = re.search(r"(\d+)\s*(?:er|e|ème|eme)?\s*[ée]tage", t, re.I)
    if m and "floor" not in d: d["floor"] = int(m.group(1))
    m = re.search(r"\bDPE\b[^A-G\n]{0,25}\b([A-G])\b", t)
    if m: d["dpe"] = m.group(1)
    m = re.search(r"\b(75|77|78|91|92|93|94|95|\d{2})\d{3}\b", t)
    if m: d["zipcode"] = m.group(0)
    return d

def _llm_fill(page_text, jsonld, known, model, mode):
    prompt = f"""Tu extrais les données d'une annonce immobilière française.
Réponds UNIQUEMENT par un JSON avec ces clés (null si l'info est absente, n'invente rien) :
title (str), price (nombre en euros, {'loyer mensuel' if mode == 'rent' else "prix de vente"}),
charges (nombre €/mois ou null), surface (nombre m²), rooms (nombre de pièces), floor (entier, 0 = rez-de-chaussée),
has_elevator (true/false/null), dpe (lettre A-G ou null), address (str), city (str), zipcode (str),
furnished (true/false/null), description (résumé factuel en 300 caractères max).

Déjà trouvé (à vérifier/compléter) : {json.dumps(known, ensure_ascii=False)}
Données structurées : {json.dumps(jsonld, ensure_ascii=False)[:2500]}
Texte de la page :
{page_text[:6500]}"""
    return llm.generate_json(prompt, model) or {}

def build_listing(cand, cfg, quick_filter=None):
    """cand = {url, source, email_text}. quick_filter(listing)->bool permet d'éviter l'appel Gemini."""
    html = fetch_page(cand["url"])
    listing = {"url": cand["url"], "source": cand["source"], "email_text": cand["email_text"], "from_page": bool(html)}
    jsonld, page_text = [], ""
    if html:
        soup = BeautifulSoup(html, "html.parser")
        jsonld = _jsonld(soup)
        og = {m.get("property"): m.get("content") for m in soup.find_all("meta", property=True)}
        listing["title"] = og.get("og:title") or (soup.title.string.strip() if soup.title and soup.title.string else None)
        for s in soup(["script", "style", "noscript"]): s.decompose()
        page_text = soup.get_text(" ", strip=True)
    base_text = " ".join(filter(None, [listing.get("title"), page_text[:4000] if page_text else cand["email_text"]]))
    listing.update({k: v for k, v in heuristics(base_text).items() if v is not None})

    if quick_filter and not quick_filter(listing):
        listing["rejected_early"] = True
        return listing

    missing = [f for f in ("price", "surface", "rooms", "floor", "dpe", "city", "zipcode") if listing.get(f) is None]
    if cfg["gemini"]["use_for_extraction"] and (missing or html) and (page_text or cand["email_text"]):
        known = {k: listing.get(k) for k in FIELDS if listing.get(k) is not None}
        got = _llm_fill(page_text or cand["email_text"], jsonld, known, cfg["gemini"]["model"], cfg["mode"])
        for k in FIELDS:
            if got.get(k) is not None:
                if k in ("price", "charges", "surface"): got[k] = to_number(got[k])
                listing[k] = got[k]   # Gemini lit la page entière : il prime sur les regex
    return listing
