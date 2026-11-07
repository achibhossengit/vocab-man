import json
import threading
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

from .wiktionary import is_bangla

TONES = ("Funny", "Professional", "Casual", "Balanced")
TONE_NOTES = {
    "Funny": "light and playful, still clear",
    "Professional": "formal and precise",
    "Casual": "everyday and conversational",
    "Balanced": "plain and natural",
}


class LookupFailed(Exception):
    pass


class ProviderDown(LookupFailed):
    pass


PROVIDERS = ("gemini", "openai")
_active = None
_active_lock = threading.Lock()


def card_options(params):
    tone = params.get("tone", "Balanced").strip()
    if tone not in TONES:
        tone = "Balanced"

    def count(name, default):
        raw = params.get(name, "")
        if raw in (None, ""):
            return default
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return default
        return max(0, min(value, 10))

    return {
        "tone": tone,
        "synonyms": count("synonyms", 3),
        "antonyms": count("antonyms", 3),
        "examples": count("examples", 2),
    }


def _strings(value, limit):
    if not isinstance(value, list):
        return []
    items = []
    for item in value:
        if not isinstance(item, str):
            continue
        item = " ".join(item.split())
        if not item or is_bangla(item):
            continue
        items.append(item)
        if len(items) == limit:
            break
    return items


def _text(value):
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def present_card(word, payload, options):
    if not isinstance(payload, dict):
        return None
    english = _text(payload.get("en"))
    bangla = _text(payload.get("bn"))
    if is_bangla(word):
        meaning, meaning_bn = english, False
    else:
        meaning, meaning_bn = bangla, True
    if not meaning or not english or not bangla:
        return None
    return {
        "en": english,
        "bn": bangla,
        "meaning": meaning,
        "meaning_bn": meaning_bn,
        "pos": _strings(payload.get("pos"), 4),
        "synonyms": _strings(payload.get("synonyms"), options["synonyms"]),
        "antonyms": _strings(payload.get("antonyms"), options["antonyms"]),
        "examples": _strings(payload.get("examples"), options["examples"]),
    }


def _prompt(word, options):
    tone = TONE_NOTES[options["tone"]]
    return (
        "Build one flashcard for this dictionary headword.\n"
        f"Headword: {word}\n"
        "Return JSON with exactly these keys: en, bn, pos, synonyms, antonyms, examples.\n"
        "en is the English word or short phrase. bn is the Bangla word or short phrase in Bengali script.\n"
        "pos, synonyms, antonyms, and examples are always English, never Bangla.\n"
        "pos is a list of parts of speech such as Noun, Verb, Adjective, Adverb, or Phrase.\n"
        f"synonyms: at most {options['synonyms']} English synonyms.\n"
        f"antonyms: at most {options['antonyms']} English antonyms.\n"
        f"examples: at most {options['examples']} English sentences that use the English word. Tone: {tone}.\n"
        "If a list limit is 0, return an empty list for that key.\n"
        "Use a real translation. If you cannot, return empty strings and empty lists."
    )


def _post(url, body, headers):
    request = Request(
        url,
        data=json.dumps(body).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode())
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ProviderDown("Could not load this card. Try Refresh.") from exc


CARD_SCHEMA = {
    "type": "object",
    "properties": {
        "en": {"type": "string"},
        "bn": {"type": "string"},
        "pos": {"type": "array", "items": {"type": "string"}},
        "synonyms": {"type": "array", "items": {"type": "string"}},
        "antonyms": {"type": "array", "items": {"type": "string"}},
        "examples": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["en", "bn", "pos", "synonyms", "antonyms", "examples"],
    "additionalProperties": False,
}


def _generate_gemini(word, options):
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        raise ProviderDown("Card lookup is not configured.")
    model = settings.GEMINI_MODEL
    payload = _post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        {
            "contents": [{"role": "user", "parts": [{"text": _prompt(word, options)}]}],
            "generationConfig": {
                "temperature": 0.4,
                "responseMimeType": "application/json",
                "responseJsonSchema": CARD_SCHEMA,
            },
        },
        {"Content-Type": "application/json", "x-goog-api-key": api_key},
    )
    try:
        return json.loads(payload["candidates"][0]["content"]["parts"][0]["text"])
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise ProviderDown("Could not load this card. Try Refresh.") from exc


def _generate_openai(word, options):
    api_key = settings.OPENAI_API_KEY
    if not api_key:
        raise ProviderDown("Card lookup is not configured.")
    payload = _post(
        "https://api.openai.com/v1/chat/completions",
        {
            "model": settings.OPENAI_MODEL,
            "temperature": 0.4,
            "messages": [{"role": "user", "content": _prompt(word, options)}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "flashcard",
                    "strict": True,
                    "schema": CARD_SCHEMA,
                },
            },
        },
        {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    try:
        return json.loads(payload["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise ProviderDown("Could not load this card. Try Refresh.") from exc


def _available_providers():
    preferred = settings.LLM_PROVIDER if settings.LLM_PROVIDER in PROVIDERS else "gemini"
    ordered = [preferred, *[name for name in PROVIDERS if name != preferred]]
    keys = {"gemini": settings.GEMINI_API_KEY, "openai": settings.OPENAI_API_KEY}
    return [name for name in ordered if keys[name]]


def _generate(word, options):
    global _active
    available = _available_providers()
    if not available:
        raise LookupFailed("Card lookup is not configured.")
    with _active_lock:
        active = _active if _active in available else None
    ordered = [active, *[name for name in available if name != active]] if active else available
    generators = {"gemini": _generate_gemini, "openai": _generate_openai}
    last = None
    for name in ordered:
        try:
            payload = generators[name](word, options)
        except ProviderDown as exc:
            last = exc
            continue
        with _active_lock:
            _active = name
        return payload
    raise LookupFailed("Could not load this card. Try Refresh.") from last


def lookup_card(word, options):
    word = " ".join(word.split())
    if not word:
        return None
    return present_card(word, _generate(word, options), options)
