"""Lit la boîte Gmail (IMAP) et extrait les liens d'annonces."""
import datetime as dt, email, imaplib, re
from email.header import decode_header, make_header
from email.utils import parseaddr
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
from .util import HEADERS

JUNK = re.compile(r"unsubscribe|desinscri|desabonn|mailto:|facebook\.|instagram\.|twitter\.|linkedin\.|"
                  r"youtube\.|apple\.com|play\.google|privacy|confidential|mentions-legales|\.(png|jpe?g|gif)(\?|$)", re.I)

def _decode_part(part):
    payload = part.get_payload(decode=True) or b""
    return payload.decode(part.get_content_charset() or "utf-8", errors="replace")

def _bodies(msg):
    html, text = "", ""
    for part in (msg.walk() if msg.is_multipart() else [msg]):
        ctype = part.get_content_type()
        if ctype == "text/html": html += _decode_part(part)
        elif ctype == "text/plain": text += _decode_part(part)
    return html, text

def fetch_emails(user, password, cfg):
    M = imaplib.IMAP4_SSL(cfg["imap_host"])
    M.login(user, password)
    M.select(f'"{cfg["folder"]}"', readonly=True)
    since = (dt.date.today() - dt.timedelta(days=cfg["days_back"])).strftime("%d-%b-%Y")
    _, data = M.search(None, "SINCE", since)
    senders = [s.lower() for s in cfg.get("sender_contains", [])]
    out = []
    for num in data[0].split():
        _, md = M.fetch(num, "(BODY.PEEK[])")
        msg = email.message_from_bytes(md[0][1])
        sender = parseaddr(msg.get("From", ""))[1].lower()
        if senders and not any(s in sender for s in senders):
            continue
        html, text = _bodies(msg)
        subject = str(make_header(decode_header(msg.get("Subject", ""))))
        out.append({"sender": sender, "subject": subject, "html": html, "text": text})
    M.logout()
    return out

def _source_for(url, sources):
    host = urlparse(url).netloc.lower()
    for name, s in sources.items():
        if any(host.endswith(h) for h in s["hosts"]):
            return name, s
    return None, None

def _is_listing(url, sources):
    name, s = _source_for(url, sources)
    p = urlparse(url)
    return bool(s and re.search(s["url_regex"], p.path + "?" + p.query))

def _resolve(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=6, stream=True, allow_redirects=True)
        final = r.url; r.close()
        return final
    except requests.RequestException:
        return None

def extract_candidates(mails, sources, max_resolve_per_mail=25):
    """Retourne [{url, source, email_text}] (liens d'annonces uniques).
    On ne suit les redirections que pour les liens de tracking (domaine inconnu), en parallèle et en nombre limité."""
    from concurrent.futures import ThreadPoolExecutor
    found, seen, resolved_cache = [], set(), {}
    for m in mails:
        soup = BeautifulSoup(m["html"] or m["text"], "html.parser")
        anchors = []
        for a in soup.find_all("a", href=True)[:300]:
            href = a["href"].strip()
            if href.startswith("http") and not JUNK.search(href):
                anchors.append((a, href))
        # liens à résoudre : domaine inconnu (tracking) et pas déjà vus
        def _has_price(a):                          # le bloc de l'annonce contient un prix : lien prioritaire
            node = a.find_parent(["td", "tr", "li", "div"])
            return bool(node and "€" in node.get_text(" ", strip=True)[:700])
        to_resolve, prio = [], {}
        for a, href in anchors:
            name, _s = _source_for(href, sources)
            if name is None and href not in resolved_cache:
                if href not in prio: to_resolve.append(href)
                prio[href] = prio.get(href, False) or _has_price(a)
        to_resolve = sorted(to_resolve, key=lambda h: not prio[h])[:max_resolve_per_mail]
        if to_resolve:
            with ThreadPoolExecutor(max_workers=8) as ex:
                for href, final in zip(to_resolve, ex.map(_resolve, to_resolve)):
                    resolved_cache[href] = final
        for a, href in anchors:
            url = href if _source_for(href, sources)[0] else resolved_cache.get(href)
            if not url or not _is_listing(url, sources):
                continue
            url = url.split("#")[0]
            ctx = a.get_text(" ", strip=True)
            node = a
            for _ in range(8):                      # on remonte dans l'email jusqu'au bloc de l'annonce
                node = node.find_parent(["td", "tr", "table", "div", "li"])
                if node is None: break
                t = node.get_text(" ", strip=True)
                if len(t) > 700: break              # on a dépassé le bloc : on garde le précédent
                ctx = t
                if "€" in t and re.search(r"m\s?[²2]", t): break
            name, _s = _source_for(url, sources)
            if url not in seen:
                seen.add(url)
                found.append({"url": url, "source": name, "email_text": ctx[:500]})
    return found
