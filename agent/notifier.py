import os, requests

def format_message(l, analysis, score, parts, cfg):
    mode_label = "Loyer" if cfg["mode"] == "rent" else "Prix"
    lines = ["🏠 NOUVELLE ANNONCE", ""]
    if l.get("title"): lines.append(f"📌 {l['title'][:120]}")
    loc = " ".join(filter(None, [l.get("zipcode"), l.get("city")]))
    lines.append(f"📍 {loc or 'Localisation inconnue'}")
    price = f"{l['price']:.0f} €" if l.get("price") else "?"
    if l.get("charges"): price += f" (+{l['charges']:.0f} € charges)"
    surf = f"{l['surface']:.0f} m²" if l.get("surface") else "? m²"
    lines.append(f"💶 {mode_label} : {price}  |  📐 {surf}" + (f"  |  🚪 {l['rooms']:.0f} p." if l.get("rooms") else ""))
    extra = []
    if l.get("floor") is not None: extra.append(f"étage {l['floor']}")
    if l.get("has_elevator") is not None: extra.append("ascenseur" if l["has_elevator"] else "sans ascenseur")
    if l.get("dpe"): extra.append(f"DPE {l['dpe']}")
    if extra: lines.append("🏷️ " + ", ".join(extra))
    lines.append(f"🔗 {l['url']}")
    if analysis and analysis.get("osm"):
        o, s = analysis["osm"], analysis.get("summary") or {}
        lines += ["", f"⭐ NOTE QUARTIER : {score}/10" if score is not None else "⭐ Note indisponible"]
        if parts:
            lines.append("   " + " · ".join(f"{k} {v:.0f}" for k, v in parts.items() if v is not None))
        if o["transit"]:
            lines.append("🚇 " + "; ".join(f"{t['name']} ({t['kind']}, {t['walk_min']} min à pied)" for t in o["transit"][:3]))
        lines.append(f"🛒 Autour : {o['shops']} commerces, {o['pharmacies']} pharmacie(s), {o['schools']} école(s), {o['parks']} parc(s), {o['bus_stops']} arrêts de bus")
        if analysis.get("median_m2"): lines.append(f"💹 Médiane DVF du secteur : {analysis['median_m2']} €/m²")
        if analysis.get("risks"): lines.append("⚠️ Risques officiels : " + ", ".join(analysis["risks"]))
        if s:
            lines += ["", "🧭 Avis (estimation IA, non vérifiée) :", s.get("ambiance", "")]
            if s.get("securite"): lines.append(f"🔒 {s['securite']}")
            for p in s.get("points_forts", [])[:3]: lines.append(f"✅ {p}")
            for p in s.get("points_attention", [])[:3]: lines.append(f"⚠️ {p}")
    else:
        lines += ["", "ℹ️ Analyse du quartier indisponible (adresse introuvable)."]
    if not l.get("from_page"): lines.append("\n⚠️ Page non lisible : infos tirées de l'email seulement.")
    return "\n".join(lines)

def send(text, dry_run=False):
    if dry_run or not os.environ.get("TELEGRAM_BOT_TOKEN"):
        print("----- MESSAGE (dry-run) -----\n" + text + "\n-----------------------------")
        return True
    url = f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage"
    for i in range(0, len(text), 4000):
        r = requests.post(url, json={"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": text[i:i + 4000]}, timeout=30)
        if not r.ok:
            print("  [telegram]", r.status_code, r.text[:200]); return False
    return True
