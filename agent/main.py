import argparse, os, time, yaml
from . import extractor, filters, mail_reader, neighborhood, notifier, scoring, store
from .util import url_key

SEEN, QUARTIERS = "state/seen.json", "state/quartiers.json"

def process(cand, cfg, cache, dry_run):
    f = cfg["filters"]
    quick = lambda l: filters.evaluate(l, f, quick=True)[0]
    l = extractor.build_listing(cand, cfg, quick_filter=quick)
    if l.get("rejected_early"):
        return "rejeté (pré-filtre)", filters.evaluate(l, f, quick=True)[1]
    ok, why = filters.evaluate(l, f)
    if not ok:
        return "rejeté", why
    analysis = neighborhood.analyze(l, cfg, cache)
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
