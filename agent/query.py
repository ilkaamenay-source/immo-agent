"""Analyse à la demande depuis Telegram : tu envoies un lien d'annonce OU une adresse / une ville.
Lancé par .github/workflows/telegram.yml (le message arrive via le relais Cloudflare)."""
import argparse, os, re, yaml
from . import commune, extractor, filters, mail_reader, neighborhood, notifier, scoring

URL_RE = re.compile(r"https?://[^\s<>\"]+")
PRICE_RE = re.compile(r"\d\s*€|€\s*\d")
AREA_RE = re.compile(r"\d\s*m\s?[²2]", re.I)
HELP = ("👋 Envoie-moi :\n"
        "• le lien d'une annonce → je l'analyse (filtres, quartier, transport futur, commune)\n"
        "• si le site est protégé (SeLoger, Leboncoin…), ajoute après le lien le texte copié de l'annonce (prix, surface, étage, DPE…)\n"
        "• une adresse ou une ville (ex : « 12 rue de la Paroisse Versailles » ou « Poissy ») → analyse du quartier et de la commune\n\n"
        "La réponse arrive en 30 à 90 secondes.")

def run(text, chat_id, cfg, dry_run=False):
    send = lambda t: notifier.send(t, dry_run, chat_id)
    t = text.strip()
    if t.lower().startswith(("/start", "/aide", "/help")) or not t:
        send(HELP); return
    cache = {}
    m = URL_RE.search(t)
    pasted = URL_RE.sub(" ", t).strip()                      # texte éventuellement collé avec le lien
    verdict = None
    if m or (PRICE_RE.search(t) and AREA_RE.search(t) and len(t) > 60):
        url = m.group(0).rstrip(".,)") if m else None
        name = (mail_reader._source_for(url, cfg["sources"])[0] if url else None)
        text_ctx = pasted[:4000] if (m and len(pasted) > 20) or not m else ""
        listing = extractor.build_listing({"url": url, "source": name or "manuel", "email_text": text_ctx}, cfg)
        ok, why = filters.evaluate(listing, cfg["filters"])
        if listing.get("transaction") and listing["transaction"] != cfg["mode"]:
            ok, why = False, why + [f"annonce de type {listing['transaction']} (ton mode : {cfg['mode']})"]
        verdict = "✅ Cette annonce passe tes filtres." if ok else "❌ Elle ne passe pas tes filtres : " + ", ".join(why)
        short = url.split("?")[0].split("#")[0] if url else None
        if listing.get("unparsed"):
            loc = " ".join(filter(None, [listing.get("zipcode"), listing.get("city")])) or "inconnue"
            head = ["🔎 ANALYSE DE L'ANNONCE", "",
                    "⚠️ Page protégée (illisible pour un robot) : je me base sur le lien (type, ville, code postal).",
                    "💡 Pour une analyse complète, renvoie le lien suivi du texte copié de l'annonce (prix, surface, étage, DPE…).",
                    f"📍 Localisation lue dans le lien : {loc}"] + ([f"🔗 {short}"] if short else [])
            verdict = ("ℹ️ Prix et surface inconnus : seuls le type, la ville et le code postal ont été contrôlés. "
                       + ("✅ Rien d'incompatible avec tes filtres." if ok else "❌ " + ", ".join(why)))
        else:
            head = ["🔎 ANALYSE DE L'ANNONCE", ""] + notifier.listing_lines({**listing, "url": short or listing.get("url")}, cfg)
        head += ["", verdict]
        send("\n".join(head))
    else:
        listing = {"address": t, "url": None}
    analysis = neighborhood.analyze(listing, cfg, cache)
    if not analysis:
        send("ℹ️ Je n'ai pas pu localiser cette adresse. Essaie avec le code postal ou la ville (ex : « 12 rue Hoche 78000 Versailles »).")
        return
    geo = analysis["geo"]
    if analysis.get("osm"):
        score, parts = scoring.compute(listing, analysis, cfg)
        lines = [f"📍 {geo.get('label')}"] + notifier.quartier_lines(analysis, score, parts)
    else:
        lines = [f"📍 {geo.get('label')}", "", notifier.analysis_missing_line(analysis)]
    send("\n".join(lines))
    send(notifier.format_commune(commune.analyze(geo, analysis, cfg, cache)))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text"); ap.add_argument("--chat-id"); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--config", default="config.yaml")
    a = ap.parse_args()
    text = a.text if a.text is not None else os.environ.get("QUERY_TEXT", "")
    chat_id = a.chat_id or os.environ.get("CHAT_ID", "")
    allowed = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not a.dry_run and (not chat_id or chat_id != allowed):    # seul le propriétaire du bot peut lancer une analyse
        print("Chat non autorisé : requête ignorée."); return
    cfg = yaml.safe_load(open(a.config, encoding="utf-8"))
    try:
        run(text, chat_id, cfg, a.dry_run)
    except Exception as e:
        print(f"erreur: {e!r}")
        notifier.send(f"⚠️ L'analyse a échoué ({type(e).__name__}). Réessaie dans un instant.", a.dry_run, chat_id)

if __name__ == "__main__":
    main()
