"""Données réelles et gratuites autour d'une position (BAN, OpenStreetMap, DVF, Géorisques)
+ résumé rédigé par Gemini, mis en cache par secteur."""
import json, math, statistics, time
import requests
from . import llm, future
from .util import HEADERS

OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
RAIL = ("station", "halt", "subway_entrance", "tram_stop")

def reverse(lat, lon):
    try:
        r = requests.get("https://api-adresse.data.gouv.fr/reverse/", params={"lat": lat, "lon": lon}, headers=HEADERS, timeout=15)
        feats = r.json().get("features") or []
        return feats[0]["properties"] if feats else None
    except (requests.RequestException, ValueError, KeyError):
        return None

def geocode(l):
    if l.get("lat") and l.get("lon"):   # position fournie par la source (ex. Bien'ici)
        pr = reverse(l["lat"], l["lon"]) or {}
        label = pr.get("label") or " ".join(filter(None, [l.get("zipcode"), l.get("city")])) or "position de l'annonce"
        return {"lat": l["lat"], "lon": l["lon"], "citycode": pr.get("citycode"), "city": pr.get("city") or l.get("city"),
                "label": label, "score": None}
    q = " ".join(filter(None, [l.get("address"), l.get("zipcode"), l.get("city")]))
    if not q.strip(): return None
    try:
        r = requests.get("https://api-adresse.data.gouv.fr/search/", params={"q": q, "limit": 1}, headers=HEADERS, timeout=15)
        feats = r.json().get("features") or []
        if not feats: return None
        lon, lat = feats[0]["geometry"]["coordinates"]
        pr = feats[0]["properties"]
        return {"lat": lat, "lon": lon, "citycode": pr.get("citycode"), "city": pr.get("city"),
                "label": pr.get("label"), "score": pr.get("score")}
    except (requests.RequestException, ValueError, KeyError):
        return None

def _dist(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = 0.5 - math.cos((lat2 - lat1) * p) / 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lon2 - lon1) * p)) / 2
    return 12742000 * math.asin(math.sqrt(a))

def _is_future_station(t):
    return any(t.get(k) == "station" for k in ("construction", "proposed", "proposed:railway", "construction:railway"))

def osm_around(lat, lon, radius, walk_speed, max_walk_min=15):
    # rayon de recherche des stations déduit du temps de marche (avec 25 % de détour)
    t_radius = int(max_walk_min * walk_speed / 1.25)
    a = f"around:{t_radius},{lat},{lon}"
    q = f"""[out:json][timeout:25];(
      nwr({a})[railway~"^(station|halt|subway_entrance|tram_stop)$"];
      nwr({a})["name"]["construction"="station"];
      nwr({a})["name"]["proposed"="station"];
      nwr({a})["name"]["proposed:railway"="station"];
      nwr({a})["name"]["construction:railway"="station"];
      nwr(around:{radius},{lat},{lon})[highway=bus_stop];
      nwr(around:{radius},{lat},{lon})[shop~"^(supermarket|convenience|bakery|butcher|greengrocer)$"];
      nwr(around:{radius},{lat},{lon})[amenity~"^(pharmacy|school|kindergarten|restaurant|cafe)$"];
      nwr(around:{radius},{lat},{lon})[leisure=park];
    );out tags center;"""
    data = None
    for ep in OVERPASS:
        try:
            r = requests.post(ep, data={"data": q}, headers=HEADERS, timeout=40)
            if r.status_code == 200:
                data = r.json(); break
        except (requests.RequestException, ValueError):
            pass
        time.sleep(2)
    if data is None: return None
    out = {"transit": [], "all_transit": [], "future": [], "bus_stops": 0, "shops": 0, "pharmacies": 0,
           "schools": 0, "food": 0, "parks": 0}
    seen_names = set()
    for el in data.get("elements", []):
        t = el.get("tags", {})
        la = el.get("lat") or el.get("center", {}).get("lat"); lo = el.get("lon") or el.get("center", {}).get("lon")
        if la is None: continue
        d = _dist(lat, lon, la, lo)
        wm = max(1, round(d * 1.25 / walk_speed))
        if _is_future_station(t) and t.get("name"):
            if wm <= max_walk_min and (t["name"], "f") not in seen_names:
                seen_names.add((t["name"], "f"))
                out["future"].append({"name": t["name"], "dist_m": round(d), "walk_min": wm})
            continue
        if t.get("railway") in RAIL:
            name = t.get("name") or t.get("ref") or "?"
            kind = "tram" if t.get("railway") == "tram_stop" else "métro/RER/train"
            if (name, kind) not in seen_names and wm <= max_walk_min:
                seen_names.add((name, kind))
                out["all_transit"].append({"name": name, "kind": kind, "dist_m": round(d), "walk_min": wm})
            continue
        if d > radius: continue
        if t.get("highway") == "bus_stop": out["bus_stops"] += 1
        elif t.get("shop"): out["shops"] += 1
        elif t.get("amenity") == "pharmacy": out["pharmacies"] += 1
        elif t.get("amenity") in ("school", "kindergarten"): out["schools"] += 1
        elif t.get("amenity") in ("restaurant", "cafe"): out["food"] += 1
        elif t.get("leisure") == "park": out["parks"] += 1
    out["all_transit"].sort(key=lambda x: x["dist_m"])
    out["future"].sort(key=lambda x: x["dist_m"])
    out["transit"] = out["all_transit"][:5]
    return out

def dvf_median_m2(lat, lon):
    """Médiane €/m² des ventes d'appartements à proximité (source DVF, API communautaire, best-effort)."""
    try:
        r = requests.get("https://api.cquest.org/dvf", params={"lat": lat, "lon": lon, "dist": 600}, headers=HEADERS, timeout=25)
        vals = []
        for x in r.json().get("resultats", []):
            if x.get("type_local") == "Appartement" and x.get("valeur_fonciere") and x.get("surface_relle_bati"):
                v = float(x["valeur_fonciere"]) / float(x["surface_relle_bati"])
                if 1500 < v < 30000: vals.append(v)
        return round(statistics.median(vals)) if len(vals) >= 5 else None
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None

def georisques(lat, lon):
    """Risques naturels/technologiques connus (Géorisques, best-effort)."""
    try:
        r = requests.get("https://georisques.gouv.fr/api/v1/gaspar/risques", params={"latlon": f"{lon},{lat}", "rayon": 1000}, headers=HEADERS, timeout=20)
        names = set()
        for item in r.json().get("data", []):
            for rk in item.get("risques_detail", []):
                if rk.get("libelle_risque_long"): names.add(rk["libelle_risque_long"])
        return sorted(names)[:6]
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None

def summarize(listing, geo, osm, risks, cache, cfg):
    """Résumé qualitatif du secteur par Gemini, mis en cache (1 appel par secteur ~1 km)."""
    key = f"{geo.get('citycode')}:{round(geo['lat'], 2)}:{round(geo['lon'], 2)}"
    if key in cache: return cache[key]
    if not cfg["gemini"]["use_for_neighborhood"]: return None
    prompt = f"""Tu es un expert en chasse immobilière en France. Secteur : {geo.get('label')}.
FAITS MESURÉS (fiables) : {json.dumps({'osm': {k: v for k, v in osm.items() if k not in ('all_transit', 'future')}, 'risques': risks}, ensure_ascii=False)}
Réponds en JSON avec : ambiance (2 phrases), calme_estime (0 à 10 ou null), securite (1 phrase prudente),
points_forts (liste de 3 max), points_attention (liste de 3 max : bruit, rez-de-chaussée, charges, etc.).
Règles : sépare ce qui vient des FAITS de ce qui vient de ta connaissance générale du quartier (impressions,
non vérifiées) ; n'invente AUCUN chiffre ; si tu ne connais pas le secteur, mets calme_estime à null."""
    res = llm.generate_json(prompt, cfg["gemini"]["model"])
    if res: cache[key] = res
    return res

def analyze(listing, cfg, cache):
    geo = geocode(listing)
    if not geo: return None
    osm = osm_around(geo["lat"], geo["lon"], cfg["limits"]["radius_m"], cfg["scoring"]["walking_speed_m_per_min"], cfg["transport"]["max_walk_min"])
    time.sleep(1)
    risks = georisques(geo["lat"], geo["lon"])
    median = dvf_median_m2(geo["lat"], geo["lon"]) if cfg["mode"] == "buy" else None
    summary = summarize(listing, geo, osm, risks, cache, cfg) if osm else None
    fut = None
    if osm and (cfg.get("future_transport") or {}).get("enabled"):
        try: fut = future.evaluate(geo, listing, osm, cfg)
        except Exception as e: print(f"  [transport futur] {e!r}")
    return {"geo": geo, "osm": osm, "risks": risks, "median_m2": median, "summary": summary, "future": fut}
