import yaml, sys
sys.path.insert(0, ".")
from agent import filters, scoring, notifier, mail_reader, extractor
from agent.util import url_key

cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
f = cfg["filters"]

# --- filtres
good = {"title": "Bel appartement lumineux", "price": 1100, "surface": 38, "rooms": 2, "floor": 3, "has_elevator": True, "dpe": "C", "city": "Paris", "zipcode": "75011", "description": "Balcon"}
assert filters.evaluate(good, f)[0]
assert not filters.evaluate({**good, "price": 1500}, f)[0]
assert not filters.evaluate({**good, "floor": 0}, f)[0]
assert not filters.evaluate({**good, "dpe": "G"}, f)[0]
assert not filters.evaluate({**good, "floor": 5, "has_elevator": False}, f)[0]
assert not filters.evaluate({**good, "description": "Appartement en rez-de-chaussée sur cour"}, f)[0]
assert not filters.evaluate({**good, "title": "Studio en colocation"}, f)[0]
# info manquante => gardé par défaut
assert filters.evaluate({"title": "x", "price": 900}, f)[0]
assert not filters.evaluate({"title": "x", "price": 900}, {**f, "on_missing": "reject"})[0]
print("filtres OK")

# --- heuristiques
h = extractor.heuristics("Appartement 2 pièces 38,5 m² 1 150 € /mois 3ème étage DPE : C 75011 Paris")
assert h["price"] == 1150 and h["surface"] == 38.5 and h["rooms"] == 2 and h["floor"] == 3 and h["dpe"] == "C" and h["zipcode"] == "75011", h
print("heuristiques OK", h)

# --- liens dans un faux email
html = """<table><tr><td><a href="https://www.seloger.com/annonces/locations/appartement/paris-11eme-75/123456789.htm?utm_source=x">Voir</a>
Appartement 2 pièces 38 m² 1 100 €</td></tr>
<tr><td><a href="https://www.bienici.com/annonce/location/paris/appartement/2pieces/ag1-abc">Bien'ici</a></td></tr>
<tr><td><a href="https://www.seloger.com/unsubscribe">stop</a></td></tr></table>"""
c = mail_reader.extract_candidates([{"html": html, "text": ""}], cfg["sources"])
assert len(c) == 2 and c[0]["source"] == "seloger" and "38 m²" in c[0]["email_text"], c
assert url_key(c[0]["url"]) == url_key("https://seloger.com/annonces/locations/appartement/paris-11eme-75/123456789.htm")
print("liens OK", [x["url"] for x in c])

# --- note + message
osm = {"transit": [{"name": "Oberkampf", "kind": "métro/RER/train", "dist_m": 200, "walk_min": 4}], "bus_stops": 8, "shops": 12, "pharmacies": 2, "schools": 3, "food": 15, "parks": 1}
an = {"geo": {}, "osm": osm, "risks": ["Inondation"], "median_m2": None, "summary": {"ambiance": "Quartier vivant.", "calme_estime": 5, "securite": "Plutôt sûr.", "points_forts": ["Transports"], "points_attention": ["Bruit le soir"]}}
score, parts = scoring.compute(good, an, cfg)
print("note", score, parts)
assert 0 < score <= 10
print(notifier.format_message({**good, "url": "https://x", "from_page": True}, an, score, parts, cfg))
