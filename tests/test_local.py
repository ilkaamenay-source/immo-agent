import yaml, sys
sys.path.insert(0, ".")
from agent import filters, scoring, notifier, mail_reader, extractor
from agent.util import url_key

cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
f = {**cfg["filters"], "price_max": 1300, "surface_min": 25, "furnished": None,
     "zipcodes_allowed": [], "parking_required": False, "require_any_keywords": []}

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

# --- transport en minutes
t=cfg["transport"]
mk=lambda wm: {"transit":[{"name":"X","kind":"métro","dist_m":wm*60,"walk_min":wm}],"bus_stops":0,"shops":0,"pharmacies":0,"schools":0,"food":0,"parks":0}
assert scoring.transport_score(mk(4),t)==10
assert round(scoring.transport_score(mk(15),t),1)==5.0
assert scoring.transport_score(mk(10),t) > scoring.transport_score(mk(15),t)
assert scoring.transport_score(mk(20),t)==3
print("transport OK", [round(scoring.transport_score(mk(m),t),1) for m in (3,5,8,10,12,15,20)])

# --- codes postaux par préfixe + parking
fz = {**f, "zipcodes_allowed": ["78", "95", "92"]}
assert filters.evaluate({**good, "zipcode": "78700"}, fz)[0]
assert filters.evaluate({**good, "zipcode": "92100"}, fz)[0]
assert not filters.evaluate({**good, "zipcode": "75011"}, fz)[0]
fp = {**f, "parking_required": True}
assert filters.evaluate({**good, "has_parking": True}, fp)[0]
assert filters.evaluate({**good}, fp)[0]                     # inconnu => gardé
assert not filters.evaluate({**good, "has_parking": False}, fp)[0]
assert not filters.evaluate({**good}, {**fp, "on_missing": "reject"})[0]
assert extractor.heuristics("Appartement avec parking en sous-sol")["has_parking"] is True
print("zip/parking OK")

# --- liens manuels
import os, tempfile
from agent import main as agent_main
tf = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
tf.write("# commentaire\n\nhttps://www.bienici.com/annonce/location/paris/appartement/2pieces/ag1-abc\nhttps://www.bienici.com/annonce/location/paris/appartement/2pieces/ag1-abc\n  https://www.pap.fr/annonces/appartement-paris-r123 \nn'importe quoi\n")
tf.close()
m = agent_main.load_manual_urls(tf.name, cfg["sources"])
assert [x["source"] for x in m] == ["bienici", "pap"], m
assert agent_main.load_manual_urls("inexistant.txt", cfg["sources"]) == []
print("liens manuels OK")

# --- Bien'ici : données directes (réponse simulée) + repli email
import json
fake = {"title": "T2 lumineux", "price": 820, "charges": 40, "surfaceArea": 38, "roomsQuantity": 2, "floor": 3,
        "energyClassification": "C", "city": "Versailles", "postalCode": "78000", "adType": "rent",
        "hasElevator": True, "parkingPlacesQuantity": 1, "description": "<p>Beau T2 proche gare</p>",
        "blurInfo": {"centroid": {"lat": 48.80, "lon": 2.13}}}
b = extractor.from_bienici_json(fake)
assert b["price"] == 820 and b["surface"] == 38 and b["zipcode"] == "78000" and b["has_parking"] and b["lat"] == 48.80 and b["transaction"] == "rent" and "<p>" not in b["description"], b
class R:  # fausse réponse HTTP
    status_code = 200
    def json(self): return fake
extractor.requests.get = lambda *a, **k: R()
cand = {"url": "https://www.bienici.com/annonce/immo-facile-61669475?at_canal=CRM", "source": "bienici", "email_text": ""}
l = extractor.build_listing(cand, cfg)
assert l["price"] == 820 and not l["unparsed"] and l["from_page"]
assert filters.evaluate(l, {**f, "zipcodes_allowed": ["78"], "price_max": 850, "surface_min": 35})[0]
# page vide + email contenant les infos -> les regex lisent l'email
extractor.requests.get = lambda *a, **k: (_ for _ in ()).throw(extractor.requests.RequestException("bloqué"))
l2 = extractor.build_listing({**cand, "email_text": "T2 38 m² 820 € Versailles 78000"}, {**cfg, "gemini": {**cfg["gemini"], "use_for_extraction": False}})
assert l2["price"] == 820 and l2["surface"] == 38 and not l2["unparsed"], l2
# rien du tout -> annonce illisible signalée
l3 = extractor.build_listing(cand, {**cfg, "gemini": {**cfg["gemini"], "use_for_extraction": False}})
assert l3["unparsed"]
assert "NON ANALYSÉE" in notifier.format_message(l3, None, None, None, cfg)
print("bienici/unparsed OK")

# ===================== transport futur =====================
import datetime as dt
from agent import future, commune, query, neighborhood
TODAY = dt.date(2026, 10, 25)
geo = {"lat": 48.9296, "lon": 2.0449, "city": "Poissy", "citycode": "78498", "label": "Poissy"}   # Poissy
osm_f = {"transit": [], "bus_stops": 4, "shops": 5, "pharmacies": 1, "schools": 1, "food": 6, "parks": 1,
         "all_transit": [{"name": "Gare de Poissy", "kind": "métro/RER/train", "dist_m": 500, "walk_min": 8}],
         "future": [{"name": "Gare Fantôme Projet", "dist_m": 600, "walk_min": 10}]}
osm_f["transit"] = osm_f["all_transit"]
cfg2 = {**cfg, "future_transport": {"enabled": True, "projects_file": "data/projects.yaml", "max_bonus": 4.0}}
fut = future.evaluate(geo, {"city": "Poissy"}, osm_f, cfg2, today=TODAY)
assert fut["items"] and fut["items"][0]["station"] == "Poissy" and fut["items"][0]["project_id"] == "rer-e-eole", fut
assert fut["score_future"] > fut["score_now"] and fut["bonus"] <= 4 and fut["score_future"] <= 10
assert [u["name"] for u in fut["osm_unmatched"]] == ["Gare Fantôme Projet"]
print("transport futur OK : actuel", fut["score_now"], "-> futur", fut["score_future"], "| bonus", fut["bonus"], "|", fut["items"][0]["walk_min"], "min,", fut["items"][0]["open_label"])
# projet déjà ouvert -> ignoré ; hors du temps de marche -> seulement info commune
fut2 = future.evaluate(geo, {"city": "Poissy"}, {**osm_f, "all_transit": [{"name": "Poissy", "kind": "x", "dist_m": 1500, "walk_min": 25}]}, cfg2, today=TODAY)
assert not fut2["items"] and any("Eole" in c["project"] for c in fut2["commune_projects"]), fut2
fut3 = future.evaluate(geo, {"city": "Poissy"}, osm_f, cfg2, today=dt.date(2027, 3, 1))
assert not any(i["project_id"] == "rer-e-eole" for i in fut3["items"])   # RER E ouvert le 28/02/2027
# gare avec coordonnées du catalogue (La Défense) : on se place à ~400 m
geo_ld = {"lat": 48.8925, "lon": 2.2361, "city": "Puteaux"}
f4 = future.evaluate(geo_ld, {"city": "Puteaux"}, {**osm_f, "all_transit": [], "future": []}, cfg2, today=TODAY)
assert any(i["station"] == "La Défense" and i["how"] == "coordonnées du catalogue" for i in f4["items"]), f4
assert future.name_match("Houilles - Carrières-sur-Seine", "Houilles-Carrières-sur-Seine")
assert not future.name_match("Poissy", "Villepinte")
print("catalogue / dates / coordonnées OK")

# message avec bloc futur
an = {"geo": geo, "osm": osm_f, "risks": None, "median_m2": None, "summary": None, "future": fut}
sc, pa = scoring.compute({"price": 800, "surface": 40}, an, cfg2)
txt = notifier.format_message({**good, "url": "https://x", "from_page": True}, an, sc, pa, cfg2)
assert "TRANSPORT FUTUR" in txt and "Eole" in txt and "28 février 2027" in txt
print(txt.split("🔮")[1][:420])

# ===================== requête Telegram (réseau simulé) =====================
sent = []
notifier.send = lambda t, dry_run=False, chat_id=None: sent.append(t) or True
neighborhood.geocode = lambda l: {**geo, "label": "12 Rue de Paris 78300 Poissy"}
neighborhood.osm_around = lambda *a, **k: osm_f
neighborhood.georisques = lambda *a, **k: ["Inondation"]
neighborhood.dvf_median_m2 = lambda *a, **k: 3900
commune.info = lambda c: {"nom": "Poissy", "population": 39000, "surface": 2800, "departement": {"nom": "Yvelines"}, "region": {"nom": "Île-de-France"}}
neighborhood.llm.generate_json = lambda *a, **k: None
commune.llm.generate_json = lambda *a, **k: {"profil": "Ville des bords de Seine.", "atouts": ["RER A", "Pôle d'emploi"], "limites": ["Trafic"], "immobilier": "Marché dynamique.", "vie_quotidienne": "Commerces en centre-ville."}
query.run("12 rue de Paris Poissy", "42", cfg2, dry_run=True)
assert len(sent) == 2 and "NOTE QUARTIER" in sent[0] and "TRANSPORT FUTUR" in sent[0] and "COMMUNE : Poissy" in sent[1] and "39 000 habitants" in sent[1] and "1393 hab/km²" in sent[1], sent
sent.clear(); query.run("/start", "42", cfg2, dry_run=True); assert "lien d'une annonce" in sent[0]
# lien d'annonce
extractor.build_listing = lambda c, cfg, quick_filter=None: {**good, "url": c["url"], "from_page": True, "unparsed": False, "lat": None}
sent.clear(); query.run("regarde ça https://www.bienici.com/annonce/immo-facile-61669475?x=1", "42", cfg2, dry_run=True)
assert len(sent) == 3 and "ANALYSE DE L'ANNONCE" in sent[0] and ("passe tes filtres" in sent[0] or "ne passe pas" in sent[0]), sent[0]
print("requête Telegram OK (", len(sent), "messages )")
