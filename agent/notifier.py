import os, requests

STATUS_LABEL = {"date_officielle": "date officielle", "en_travaux": "chantier en cours",
                "finance": "financé", "etude": "à l'étude"}

def future_lines(fut):
    if not fut or (not fut["items"] and not fut["commune_projects"] and not fut["osm_unmatched"]):
        return []
    lines = [""]
    if fut["score_future"] is not None:
        sign = f" (+{fut['bonus']})" if fut["bonus"] else ""
        lines.append(f"🔮 TRANSPORT FUTUR : {fut['score_future']}/10  (actuel {fut['score_now']}/10{sign})")
    for i in fut["items"][:4]:
        lines.append(f"  • {i['station']} – {i['project']}\n    {i['walk_min']} min à pied · prévu {i['open_label']} · {STATUS_LABEL.get(i['status'], '')}")
        if i.get("benefit"): lines.append(f"    ↳ {i['benefit']}")
    for c in fut["commune_projects"][:3]:
        lines.append(f"  📍 Dans la commune : {c['project']} ({c['open_label']}) – gare non localisée précisément")
    for u in fut["osm_unmatched"][:2]:
        lines.append(f"  🏗️ Gare en chantier/projet repérée sur la carte : {u['name']} ({u['walk_min']} min à pied, statut non vérifié)")
    lines.append(f"  ℹ️ Calendriers du catalogue au {fut.get('catalog_date', '?')}, susceptibles d'évoluer.")
    return lines

def quartier_lines(analysis, score, parts):
    o, s = analysis["osm"], analysis.get("summary") or {}
    lines = ["", f"⭐ NOTE QUARTIER : {score}/10" if score is not None else "⭐ Note indisponible"]
    if parts:
        lines.append("   " + " · ".join(f"{k} {v:.0f}" for k, v in parts.items() if v is not None and k != "transport_futur"))
    if o["transit"]:
        lines.append("🚇 " + "; ".join(f"{t['name']} ({t['kind']}, {t['walk_min']} min à pied)" for t in o["transit"][:3]))
    else:
        lines.append("🚇 Aucune station à proximité dans le temps de marche choisi")
    if o.get("partial"):
        lines.append("🛒 Commerces et services : données indisponibles (serveur OpenStreetMap occupé), note calculée sans eux")
    else:
        lines.append(f"🛒 Autour : {o['shops']} commerces, {o['pharmacies']} pharmacie(s), {o['schools']} école(s), {o['parks']} parc(s), {o['bus_stops']} arrêts de bus")
    if analysis.get("median_m2"): lines.append(f"💹 Médiane DVF du secteur : {analysis['median_m2']} €/m²")
    if analysis.get("risks"): lines.append("⚠️ Risques officiels : " + ", ".join(analysis["risks"]))
    lines += future_lines(analysis.get("future"))
    if s:
        lines += ["", "🧭 Avis (estimation IA, non vérifiée) :", s.get("ambiance", "")]
        if s.get("securite"): lines.append(f"🔒 {s['securite']}")
        for p in s.get("points_forts", [])[:3]: lines.append(f"✅ {p}")
        for p in s.get("points_attention", [])[:3]: lines.append(f"⚠️ {p}")
    return lines

def analysis_missing_line(analysis):
    if analysis is None:
        return "ℹ️ Analyse du quartier indisponible (adresse introuvable dans l'annonce)."
    return "ℹ️ Analyse du quartier indisponible (serveur de cartes OpenStreetMap injoignable à cet instant)."

def listing_lines(l, cfg):
    mode_label = "Loyer" if cfg["mode"] == "rent" else "Prix"
    lines = []
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
    if l.get("has_parking"): extra.append("parking")
    if extra: lines.append("🏷️ " + ", ".join(extra))
    lines.append(f"🔗 {l['url']}")
    return lines

def format_message(l, analysis, score, parts, cfg):
    if l.get("unparsed") and not (l.get("zipcode") or l.get("city")):
        return ("🏠 ANNONCE NON ANALYSÉE\n\n⚠️ Le contenu de la page n'a pas pu être lu : aucun filtre n'a pu être "
                "appliqué. À vérifier à la main :\n🔗 " + l["url"])
    title = "🏠 ANNONCE PARTIELLEMENT LUE" if l.get("unparsed") else "🏠 NOUVELLE ANNONCE"
    lines = [title, ""] + listing_lines(l, cfg)
    if l.get("unparsed"):
        lines += ["", "⚠️ Page protégée : prix et surface inconnus, donc non vérifiés avec tes filtres (seuls le type, la ville "
                  "et le code postal tirés du lien ont été contrôlés). Ouvre le lien pour vérifier."]
    if analysis and analysis.get("osm"):
        lines += quartier_lines(analysis, score, parts)
    else:
        lines += ["", analysis_missing_line(analysis)]
    if not l.get("from_page") and not l.get("unparsed"): lines.append("\n⚠️ Page non lisible : infos tirées de l'email seulement.")
    return "\n".join(lines)

def format_commune(c):
    if not c: return "ℹ️ Fiche de la commune indisponible."
    lines = [f"🏘️ COMMUNE : {c.get('nom') or '?'}", ""]
    st = c.get("stats")
    if st:
        bits = []
        if st.get("population"): bits.append(f"{st['population']:,} habitants".replace(",", " "))
        if st.get("densite"): bits.append(f"{st['densite']} hab/km²".replace(",", " "))
        if st.get("departement"): bits.append(f"{st['departement']} ({st.get('region') or ''})".replace(" ()", ""))
        lines.append("📊 " + " · ".join(bits))
    if c.get("median_m2"): lines.append(f"💹 Prix de vente médian du secteur (DVF, appartements) : {c['median_m2']} €/m²")
    s = c.get("summary")
    if s:
        lines += ["", "🧭 Présentation (estimation IA, non vérifiée) :", s.get("profil", "")]
        if s.get("vie_quotidienne"): lines.append(s["vie_quotidienne"])
        for a in s.get("atouts", [])[:3]: lines.append(f"✅ {a}")
        for a in s.get("limites", [])[:3]: lines.append(f"⚠️ {a}")
        if s.get("immobilier"): lines.append(f"🏷️ Marché : {s['immobilier']}")
    return "\n".join(lines)

def send(text, dry_run=False, chat_id=None):
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
    if dry_run or not os.environ.get("TELEGRAM_BOT_TOKEN") or not chat_id:
        print("----- MESSAGE (dry-run) -----\n" + text + "\n-----------------------------")
        return True
    url = f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage"
    for i in range(0, len(text), 4000):
        r = requests.post(url, json={"chat_id": chat_id, "text": text[i:i + 4000], "disable_web_page_preview": True}, timeout=30)
        if not r.ok:
            print("  [telegram]", r.status_code, r.text[:200]); return False
    return True
