"""Note de transport FUTUR : projets (data/projects.yaml) à proximité de l'annonce.

Principe : note_future = note_actuelle + bonus, plafonné à 10.
  bonus d'un projet = bonus_max(kind) x valeur ; valeur = (note de marche 0-10) x fiabilité du projet x facteur délai
  - on garde la meilleure gare de chaque projet (pas de double comptage) ; bonus total plafonné (max_bonus).
"""
import datetime as dt, math, re
import yaml
from .util import norm
from . import scoring

CERT = {"date_officielle": 1.0, "en_travaux": 0.85, "finance": 0.6, "etude": 0.3}
CERT_LABEL = {"date_officielle": "date officielle", "en_travaux": "chantier en cours",
              "finance": "financé", "etude": "à l'étude"}
KIND_MAX = {"new": 3.0, "upgrade": 2.0}
KIND_LABEL = {"new": "nouvelle gare", "upgrade": "gare existante mieux desservie"}

def load_projects(path):
    try:
        return yaml.safe_load(open(path, encoding="utf-8")) or {}
    except (FileNotFoundError, yaml.YAMLError):
        return {}

def _date(s):
    m = re.match(r"(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?", str(s))
    if not m: return None
    y, mo, d = int(m.group(1)), int(m.group(2) or 12), int(m.group(3) or 28)
    try: return dt.date(y, mo, d)
    except ValueError: return dt.date(y, 12, 28)

def time_factor(open_date, today):
    yrs = (open_date - today).days / 365
    return 1.0 if yrs <= 1 else 0.9 if yrs <= 3 else 0.75 if yrs <= 5 else 0.55 if yrs <= 8 else 0.4

def walk_score(wm, ideal, mx):
    if wm > mx: return 0.0
    return 10.0 if wm <= ideal else 10 - 5 * (wm - ideal) / max(1, mx - ideal)

def _clean(s):
    s = norm(s)
    for p in ("gare de ", "gare d ", "gare ", "station "):
        if s.startswith(p): s = s[len(p):]
    return s.strip()

def name_match(a, b):
    na, nb = _clean(a), _clean(b)
    if not na or not nb: return False
    if na == nb: return True
    short, long_ = (na, nb) if len(na) <= len(nb) else (nb, na)
    return len(short) >= 6 and f" {short} " in f" {long_} "

def _hav(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = 0.5 - math.cos((lat2 - lat1) * p) / 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lon2 - lon1) * p)) / 2
    return 12742000 * math.asin(math.sqrt(a))

def evaluate(geo, listing, osm, cfg, today=None):
    ft = cfg.get("future_transport") or {}
    data = load_projects(ft.get("projects_file", "data/projects.yaml"))
    projects = data.get("projects") or []
    today = today or dt.date.today()
    tcfg, speed = cfg["transport"], cfg["scoring"]["walking_speed_m_per_min"]
    mx, ideal = tcfg["max_walk_min"], tcfg["ideal_walk_min"]
    score_now = scoring.transport_score(osm, tcfg)
    city = norm(listing.get("city") or geo.get("city") or "")
    cands = list(osm.get("all_transit", [])) + list(osm.get("future", []))
    matched_names = set()
    items, commune_projects = [], []

    for p in projects:
        od = _date(p.get("open"))
        if od is None or od < today:       # déjà ouvert (ou date illisible) : déjà dans les données actuelles
            continue
        best = None
        in_commune = False
        for st in p.get("stations", []):
            wm, how = None, None
            if st.get("lat") and st.get("lon"):
                wm = round(_hav(geo["lat"], geo["lon"], st["lat"], st["lon"]) * 1.25 / speed)
                how = "coordonnées du catalogue"
            else:
                hits = [c for c in cands if name_match(st["name"], c["name"])]
                if hits:
                    c = min(hits, key=lambda x: x["dist_m"])
                    wm, how = c["walk_min"], "OpenStreetMap"
                    matched_names.add(norm(c["name"]))
            if wm is not None and wm <= mx:
                value = walk_score(wm, ideal, mx) * CERT.get(p.get("status"), 0.3) * time_factor(od, today)
                bonus = KIND_MAX.get(st.get("kind"), 2.0) * value / 10
                if best is None or bonus > best["bonus"]:
                    best = {"project": p["name"], "project_id": p["id"], "station": st["name"], "kind": st.get("kind", "upgrade"),
                            "walk_min": wm, "open_label": p.get("open_label", str(od.year)), "status": p.get("status"),
                            "bonus": round(bonus, 2), "benefit": p.get("benefit"), "how": how, "source": p.get("source")}
            if city and any(norm(c) == city for c in st.get("communes", [])):
                in_commune = True
        if best: items.append(best)
        elif in_commune:
            commune_projects.append({"project": p["name"], "open_label": p.get("open_label", str(od.year)),
                                     "status": p.get("status"), "benefit": p.get("benefit")})

    items.sort(key=lambda x: -x["bonus"])
    total = min(ft.get("max_bonus", 4.0), sum(i["bonus"] for i in items))
    unmatched = [f for f in osm.get("future", []) if norm(f["name"]) not in matched_names][:3]
    return {"score_now": None if score_now is None else round(score_now, 1),
            "bonus": round(total, 1),
            "score_future": None if score_now is None else round(min(10, score_now + total), 1),
            "items": items, "commune_projects": commune_projects, "osm_unmatched": unmatched,
            "catalog_date": data.get("updated")}
