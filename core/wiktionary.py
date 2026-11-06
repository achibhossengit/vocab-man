import http.client
import json
import threading
from urllib.parse import urlencode

USER_AGENT = "vocab-man/1.0 (bilingual flashcard search)"
HOSTS = {
    "bn": "bn.wiktionary.org",
    "en": "en.wiktionary.org",
}

_lock = threading.Lock()
_connections = {}


def is_bangla(text):
    return any("\u0980" <= char <= "\u09ff" for char in text)


def _host_for(term):
    return HOSTS["bn"] if is_bangla(term) else HOSTS["en"]


def _read(host, path):
    with _lock:
        connection = _connections.get(host)
        if connection is None:
            connection = http.client.HTTPSConnection(host, timeout=4)
            _connections[host] = connection
        try:
            connection.request(
                "GET",
                path,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
            response = connection.getresponse()
            body = response.read()
        except Exception:
            connection.close()
            _connections.pop(host, None)
            raise
        if response.status != 200:
            connection.close()
            _connections.pop(host, None)
            raise http.client.HTTPException(response.status)
        return body


def suggest_words(term):
    term = " ".join(term.split())
    if not term:
        return []
    host = _host_for(term)
    path = "/w/api.php?" + urlencode({
        "action": "opensearch",
        "format": "json",
        "limit": 5,
        "search": term[:80],
    })
    try:
        raw = _read(host, path)
    except Exception:
        try:
            raw = _read(host, path)
        except Exception:
            return []
    try:
        payload = json.loads(raw.decode())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []
    titles = payload[1] if isinstance(payload, list) and len(payload) > 1 else []
    words = []
    for title in titles:
        if not isinstance(title, str):
            continue
        title = title.strip()
        if not title or ":" in title:
            continue
        words.append({"word": title, "bn": is_bangla(title)})
        if len(words) == 5:
            break
    return words
