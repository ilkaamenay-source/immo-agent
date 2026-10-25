import argparse, os, time, yaml
from . import extractor, filters, mail_reader, neighborhood, notifier, scoring, store
from .util import url_key

SEEN, QUARTIERS = "state/seen.json", "state/quartiers.json"
MANUAL = "manual_urls.txt"

def load_manual_urls(path, sources):
    """Liens collés à la main (annonces déjà en ligne avant la création des alertes)."""
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except FileNotFoundError:
        return []
    out, seen = [], set()
    for ln in lines:
        url = ln.strip().split()[0].split("#")[0] if ln.strip() else ""
        if not url.startswith("http") or url in seen:
            continue
        seen.add(url)
        name, _ = mail_reader._source_for(url, sources)
        out.append({"url": url, "source": name or "manuel", "email_text": ""})
    return out

def process(cand, cfg, cache, dry_run):
    f = cfg["filters"]
    quick = lambda l: filters.evaluate(l, f, quick=True)[0]
    l = extractor.build_listing(cand, cfg, quick_filter=quick)
    if l.get("rejected_early"):
        return "rejeté (pré-filtre)", filters.evaluate(l, f, quick=True)[1]
    if l.get("transaction") and l["transaction"] != cfg["mode"]:
        return "rejeté", [f"annonce de type {l['transaction']} (mode {cfg['mode']})"]
    if l.get("unparsed") and cfg.get("on_unparsed", "notify") == "skip":
        return "non analysée (page illisible)", []
    ok, why = filters.evaluate(l, f)
    if not ok:
        return "rejeté", why
    analysis = neighborhood.analyze(l, cfg, cache)
    if cfg["transport"]["reject_if_no_station"] and analysis and analysis.get("osm") and not analysis["osm"]["transit"]:
        return "rejeté", [f"aucune station à moins de {cfg['transport']['max_walk_min']} min à pied"]
    score, parts = scoring.compute(l, analysis, cfg) if analysis and analysis.get("osm") else (None, None)
    mn = cfg["scoring"].get("min_score_to_notify")
    if mn is not None and score is not None and score < mn:
        return "note trop basse", [f"{score}/10"]
    notifier.send(notifier.format_message(l, analysis, score, parts, cfg), dry_run)
    return "envoyé", [f"{score}/10" if score is not None else "sans note"]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test-url", help="traite une seule annonce sans lire les emails")
    ap.add_argument("--dry-run", action="store_true", help="affiche au lieu d'envoyer sur Telegram")
    ap.add_argument("--config", default="config.yaml")
    a = ap.parse_args()
    cfg = yaml.safe_load(open(a.config, encoding="utf-8"))
    seen, cache = store.load(SEEN, {}), store.load(QUARTIERS, {})

    if a.test_url:
        cands = [{"url": a.test_url, "source": "test", "email_text": ""}]
    else:
        mails = mail_reader.fetch_emails(os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"], cfg["mail"])
        cands = mail_reader.extract_candidates(mails, cfg["sources"])
        print(f"{len(mails)} email(s) lus, {len(cands)} lien(s) d'annonce")
        manual = load_manual_urls(MANUAL, cfg["sources"])
        print(f"{len(manual)} lien(s) dans {MANUAL}")
        known = {c["url"] for c in cands}
        cands += [m for m in manual if m["url"] not in known]
        cands = [c for c in cands if url_key(c["url"]) not in seen]
        print(f"{len(cands)} nouvelle(s) annonce(s)")

    for c in cands[: cfg["limits"]["max_new_per_run"]]:
        print(f"→ {c['url']}")
        try:
            status, info = process(c, cfg, cache, a.dry_run)
        except Exception as e:           # une annonce en erreur ne bloque pas les autres
            print(f"  erreur: {e!r}"); continue
        print(f"  {status} {info}")
        seen[url_key(c["url"])] = {"url": c["url"], "status": status, "ts": int(time.time())}
        time.sleep(2)

    if not a.test_url:
        store.save(SEEN, seen)
    store.save(QUARTIERS, cache)

if __name__ == "__main__":
    main()
