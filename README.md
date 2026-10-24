# Agent immo gratuit : alertes email → filtres → analyse du quartier → Telegram

Fonctionnement : tes alertes SeLoger / Bien'ici / PAP / Leboncoin arrivent dans Gmail.
Toutes les 3 h, GitHub Actions lance l'agent qui :
1. lit les emails récents et extrait les liens d'annonces ;
2. ignore les annonces déjà vues (`state/seen.json`) ;
3. lit chaque page (JSON-LD, regex, puis Gemini seulement si nécessaire) ;
4. applique **tes filtres** (`config.yaml`) ;
5. analyse le quartier (BAN, OpenStreetMap, Géorisques, DVF en achat) + résumé Gemini mis en cache ;
6. calcule une note /10 selon **tes pondérations** et envoie le tout sur Telegram.

## Mise en route (≈ 15 min)
1. **Gmail** : active la validation en 2 étapes, puis crée un *mot de passe d'application*
   (compte Google → Sécurité → Mots de passe des applications). IMAP est activé par défaut.
   Crée tes alertes (ville + budget large) sur chaque site vers cette adresse.
   Astuce : un filtre Gmail qui applique un libellé `alertes-immo`, puis `folder: alertes-immo` dans la config.
2. **Gemini** : clé gratuite sur https://aistudio.google.com (vérifie ton quota dans AI Studio).
3. **Telegram** : réutilise ton bot (BotFather) et ton chat id.
4. **GitHub** : crée un dépôt **privé**, pousse ce dossier, puis
   Settings → Secrets and variables → Actions → New repository secret :
   `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
5. Onglet Actions → *immo-agent* → **Run workflow** pour un premier test.

## À ajuster après ton premier email réel
`sources.*.url_regex` dans `config.yaml` est un point de départ : regarde l'URL d'une vraie annonce dans
tes emails (ou le log « 0 lien d'annonce ») et corrige le motif si besoin. Les liens de tracking
(click.xxx.com) sont suivis automatiquement.

## Tester en local
```bash
pip install -r requirements.txt
export GEMINI_API_KEY=...            # optionnel
python -m agent.main --test-url "https://www.bienici.com/annonce/..." --dry-run
python tests/test_local.py           # tests des filtres / liens / note
```

## Limites connues
- Certains sites (SeLoger, Leboncoin) peuvent refuser l'accès à la page depuis GitHub : l'agent se replie alors
  sur le texte de l'email (le message l'indique).
- « Calme » et « ambiance » sont des **estimations de Gemini** (marquées comme telles) ; transports, commerces,
  risques et prix DVF sont des **données mesurées**.
- DVF (API communautaire) et Géorisques sont en « best-effort » : s'ils ne répondent pas, la ligne est omise.
- Repo privé : ~2000 min/mois gratuites ; ce workflow en consomme ~1-2 min par passage.
