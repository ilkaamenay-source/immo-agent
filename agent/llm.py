"""Appels Gemini (API REST, clé gratuite AI Studio).
Les noms de modèles changent vite et certains deviennent inaccessibles aux nouveaux projets (erreur 404) :
le code essaie le modèle de config.yaml puis découvre tout seul un modèle "flash" disponible pour ta clé."""
import json, os, re, time, requests

BASE = "https://generativelanguage.googleapis.com/v1beta"
SKIP = ("image", "tts", "live", "audio", "embedding", "robotics", "computer", "native", "imagen", "veo",
        "lyria", "omni", "translate", "aqa", "learnlm", "gemma", "vision", "thinking")
RETIRED = object()                       # modèle indisponible pour cette clé (404, quota 0, ...)
_state = {"model": None, "bad": set(), "dead": False, "listed": None}

def _h():
    return {"x-goog-api-key": os.environ["GEMINI_API_KEY"]}

def discover():
    """Liste les modèles 'flash' utilisables avec generateContent, du plus adapté au moins adapté."""
    if _state["listed"] is not None: return _state["listed"]
    names, token = [], None
    try:
        for _ in range(5):
            params = {"pageSize": 100, **({"pageToken": token} if token else {})}
            r = requests.get(f"{BASE}/models", headers=_h(), params=params, timeout=20)
            if r.status_code != 200:
                print(f"  [gemini] liste des modèles impossible : HTTP {r.status_code} {r.text[:150]}"); break
            js = r.json()
            for m in js.get("models", []):
                n = m.get("name", "").removeprefix("models/")
                if ("generateContent" in m.get("supportedGenerationMethods", []) and n.startswith("gemini")
                        and "flash" in n and not any(x in n for x in SKIP)):
                    names.append(n)
            token = js.get("nextPageToken")
            if not token: break
    except (requests.RequestException, ValueError) as e:
        print(f"  [gemini] liste des modèles impossible : {type(e).__name__}")
    def rank(n):
        stable = not re.search(r"preview|exp|latest", n)
        mv = re.match(r"gemini-(\d+(?:\.\d+)?)", n)
        return (not stable, "lite" not in n, -(float(mv.group(1)) if mv else 0), n)
    _state["listed"] = sorted(set(names), key=rank)
    print(f"  [gemini] modèles disponibles : {_state['listed'][:5]}")
    return _state["listed"]

def _call(prompt, model):
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}}
    delay = 6
    for attempt in range(3):
        try:
            r = requests.post(f"{BASE}/models/{model}:generateContent", headers=_h(), json=body, timeout=60)
        except requests.RequestException as e:
            print(f"  [gemini] {model}: {type(e).__name__}"); time.sleep(delay); delay *= 2; continue
        if r.status_code == 200:
            try:
                text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
                return json.loads(text)
            except (KeyError, IndexError, ValueError):
                print(f"  [gemini] {model}: réponse illisible"); continue
        txt = r.text[:200]
        if r.status_code == 429 and re.search(r'limit"?:\s*0', r.text):
            print(f"  [gemini] {model}: quota gratuit nul pour ce modèle"); return RETIRED
        if r.status_code in (429, 500, 503):
            print(f"  [gemini] {model}: HTTP {r.status_code}, nouvel essai"); time.sleep(delay); delay *= 2; continue
        print(f"  [gemini] {model}: HTTP {r.status_code} {txt}")
        if r.status_code in (400, 401, 403) and re.search(r"api key|API_KEY|permission", r.text, re.I):
            _state["dead"] = True                  # clé invalide : inutile d'essayer d'autres modèles
        return RETIRED
    return None

def generate_json(prompt, model="auto"):
    if not os.environ.get("GEMINI_API_KEY") or _state["dead"]:
        return None
    if _state["model"]:
        cands = [_state["model"]]
    else:
        cands = [m for m in ([model] if model and model != "auto" else []) if m not in _state["bad"]]
        cands += [n for n in discover() if n not in cands and n not in _state["bad"]][:4]
    for m in cands:
        res = _call(prompt, m)
        if res is RETIRED:
            _state["bad"].add(m); _state["model"] = None
            if _state["dead"]: return None
            continue
        if res is not None:
            if _state["model"] != m: print(f"  [gemini] modèle utilisé : {m}")
            _state["model"] = m
        return res                                  # None = panne passagère : on n'enchaîne pas les modèles
    if not _state["dead"]:
        print("  [gemini] aucun modèle utilisable avec cette clé : l'agent continue sans résumé IA")
    _state["dead"] = True
    return None
