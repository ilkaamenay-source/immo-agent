"""Note /10 calculée en code à partir des données mesurées (reproductible, 0 quota)."""

def transport_score(osm, tcfg):
    """Note selon le temps de marche jusqu'à la station la plus proche (réglable dans config.yaml)."""
    if not osm: return None
    ideal, mx = tcfg["ideal_walk_min"], tcfg["max_walk_min"]
    t = osm["transit"]
    if not t:
        base = 3 if osm["bus_stops"] >= 3 else 1
    else:
        wm = t[0]["walk_min"]
        if wm <= ideal: base = 10
        elif wm <= mx: base = 10 - 5 * (wm - ideal) / max(1, mx - ideal)   # 10 -> 5
        else: base = 3
        if len(t) >= 2: base += 0.5
    return min(10, base + min(1.5, osm["bus_stops"] / 6))

def shops_score(osm):
    if not osm: return None
    n = osm["shops"] + osm["pharmacies"] + osm["food"] // 3 + osm["parks"]
    return min(10, round(n / 2.5, 1))

def price_score(price, surface, median):
    if not (price and surface and median): return None
    r = (price / surface) / median
    return 9 if r <= 0.9 else 7 if r <= 1.0 else 5 if r <= 1.1 else 3

def compute(listing, analysis, cfg):
    w = cfg["scoring"]["weights"]
    osm, summ = analysis["osm"], analysis.get("summary") or {}
    parts = {
        "transport": transport_score(osm, cfg["transport"]),
        "calme": summ.get("calme_estime"),
        "commerces": shops_score(osm),
        "prix": price_score(listing.get("price"), listing.get("surface"), analysis.get("median_m2")),
        "transport_futur": ((analysis.get("future") or {}).get("score_future")),
    }
    used = {k: v for k, v in parts.items() if v is not None and w.get(k)}
    if not used: return None, parts
    total = sum(w[k] for k in used)
    score = sum(used[k] * w[k] for k in used) / total
    score -= min(1.5, 0.5 * len(analysis.get("risks") or []))   # pénalité risques officiels
    return round(max(0, score), 1), parts
