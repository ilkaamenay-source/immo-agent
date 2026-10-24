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

def extract_candidates(mails, sources, max_links_per_mail=40):
    """Retourne [{url, source, email_text}] (liens d'annonces uniques)."""
    found, seen = [], set()
    for m in mails:
        soup = BeautifulSoup(m["html"] or m["text"], "html.parser")
        links = soup.find_all("a", href=True)[:300]
        resolved = 0
        for a in links:
            href = a["href"].strip()
            if not href.startswith("http") or JUNK.search(href):
                continue
            url = href
            if not _is_listing(url, sources) and resolved < max_links_per_mail:
                # lien de tracking (ex: click.xxx.com) -> on suit la redirection
                try:
                    r = requests.get(url, headers=HEADERS, timeout=10, stream=True, allow_redirects=True)
                    url = r.url; r.close(); resolved += 1
                except requests.RequestException:
                    continue
            if not _is_listing(url, sources):
                continue
            url = url.split("#")[0]
            parent = a.find_parent(["td", "div", "tr", "li"])
            ctx = (parent.get_text(" ", strip=True) if parent else a.get_text(" ", strip=True))[:500]
            name, _ = _source_for(url, sources)
            if url not in seen:
                seen.add(url)
                found.append({"url": url, "source": name, "email_text": ctx})
    return found
