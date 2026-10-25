"""Filtres 100 % déterministes (gratuits, reproductibles)."""
import re
from .util import norm

def evaluate(l, f, quick=False):
    """Retourne (ok, [raisons de rejet]). quick=True : on ignore les infos absentes."""
    why = []
    missing_reject = (f.get("on_missing", "keep") == "reject") and not quick

    def num(field, label, ok):
        v = l.get(field)
        if v is None:
            if missing_reject: why.append(f"{label} inconnu")
        elif not ok(v):
            why.append(f"{label} ({v})")

    if f.get("price_min") is not None: num("price", "prix trop bas", lambda v: v >= f["price_min"])
    if f.get("price_max") is not None: num("price", "prix trop haut", lambda v: v <= f["price_max"])
    if f.get("surface_min") is not None: num("surface", "surface trop petite", lambda v: v >= f["surface_min"])
    if f.get("surface_max") is not None: num("surface", "surface trop grande", lambda v: v <= f["surface_max"])
    if f.get("rooms_min") is not None: num("rooms", "pas assez de pièces", lambda v: v >= f["rooms_min"])
    if f.get("rooms_max") is not None: num("rooms", "trop de pièces", lambda v: v <= f["rooms_max"])
    if f.get("charges_max") is not None: num("charges", "charges trop hautes", lambda v: v <= f["charges_max"])
    if f.get("floor_min") is not None: num("floor", "étage trop bas", lambda v: v >= f["floor_min"])
    if f.get("exclude_ground_floor"): num("floor", "rez-de-chaussée", lambda v: v != 0)

    p, s, c = l.get("price"), l.get("surface"), l.get("charges")
    if f.get("price_per_m2_max") is not None and p and s and p / s > f["price_per_m2_max"]:
        why.append(f"prix/m² trop haut ({p/s:.0f})")
    if f.get("total_max") is not None and p is not None and c is not None and p + c > f["total_max"]:
        why.append(f"loyer+charges trop haut ({p+c:.0f})")

    n = f.get("elevator_required_from_floor")
    if n is not None and l.get("floor") is not None and l["floor"] >= n and l.get("has_elevator") is False:
        why.append(f"étage {l['floor']} sans ascenseur")

    if f.get("dpe_allowed") and l.get("dpe"):
        if str(l["dpe"]).upper() not in [x.upper() for x in f["dpe_allowed"]]:
            why.append(f"DPE {l['dpe']}")
    elif f.get("dpe_allowed") and missing_reject:
        why.append("DPE inconnu")

    if f.get("parking_required"):
        hp = l.get("has_parking")
        if hp is False or (hp is None and missing_reject):
            why.append("pas de parking" if hp is False else "parking inconnu")

    if f.get("furnished") is not None and l.get("furnished") is not None and l["furnished"] != f["furnished"]:
        why.append("meublé/non meublé ne correspond pas")

    # "78" accepte tout le département (78700, 78100...) ; "75011" accepte uniquement ce code exact
    if f.get("zipcodes_allowed") and l.get("zipcode"):
        if not any(str(l["zipcode"]).startswith(str(z)) for z in f["zipcodes_allowed"]):
            why.append(f"code postal {l['zipcode']}")
    if f.get("cities_allowed") and l.get("city"):
        if norm(l["city"]) not in [norm(x) for x in f["cities_allowed"]]:
            why.append(f"ville {l['city']}")

    blob = norm(" ".join(str(l.get(k) or "") for k in ("title", "description", "email_text")))
    for kw in f.get("exclude_keywords") or []:
        k = norm(kw)
        if k and re.search(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])", blob):
            why.append(f"mot exclu « {kw} »"); break
    req = f.get("require_any_keywords") or []
    if req and not quick and not any(norm(k) in blob for k in req):
        why.append("aucun mot requis trouvé")

    return (not why), why
