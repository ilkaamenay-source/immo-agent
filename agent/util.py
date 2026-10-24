import hashlib, re, unicodedata
from urllib.parse import urlparse

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9"}

def norm(s):
    """minuscule + sans accents + tirets/espaces unifiés (pour comparer des mots-clés)."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[\s_]+", " ", s.replace("-", " "))

def url_key(url):
    p = urlparse(url)
    host = p.netloc.lower()
    if host.startswith("www."): host = host[4:]
    return hashlib.sha1((host + p.path.rstrip("/")).encode()).hexdigest()[:16]

def to_number(s):
    if s is None: return None
    if isinstance(s, (int, float)): return float(s)
    s = re.sub(r"[^\d,\.]", "", str(s).replace("\u202f", "").replace("\xa0", ""))
    s = s.replace(",", ".")
    if s.count(".") > 1: s = s.replace(".", "")
    try: return float(s) if s else None
    except ValueError: return None
