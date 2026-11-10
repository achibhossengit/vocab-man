import json
import threading
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

TONES = ("Funny", "Professional", "Casual", "Balanced")


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

    raw_pair = params.get("pair", "en-bn").strip().split("-", 1)
    if (
        len(raw_pair) == 2
        and raw_pair[0] in LANGUAGE_NAMES
        and raw_pair[1] in LANGUAGE_NAMES
        and raw_pair[0] != raw_pair[1]
    ):
        pair = f"{raw_pair[0]}-{raw_pair[1]}"
    else:
        pair = "en-bn"
    known, learn = pair.split("-", 1)

    return {
        "tone": tone,
        "pair": pair,
        "known": known,
        "learn": learn,
        "synonyms": count("synonyms", 3),
        "antonyms": count("antonyms", 3),
        "examples": count("examples", 2),
    }


def _prompt(word, source_lan, target_lan, known):
    source_name = LANGUAGE_NAMES[source_lan]
    target_name = LANGUAGE_NAMES[target_lan]
    lines = [
        f"The looked-up word is in {source_name}.\nLooked-up word: {word}\n",
        f"source.lan is {source_lan} ({source_name}). source.word is exactly the looked-up word.\n",
        f"target.lan is {target_lan} ({target_name}). target.word translates source.word.\n",
        "Each word has one part of speech, one short definition, and one example sentence, all in that word's own language.\n",
        "source.synonyms and source.antonyms are other words in the source language.\n",
        "Each target synonym and antonym has of: the source-language word it translates.\n",
        "A target synonym's of is source.word or one source synonym. A target antonym's of is one source antonym.\n",
        "At most 5 synonyms and 5 antonyms on each side.\n",
        "Use a real translation. If you cannot, return empty strings and empty lists.",
    ]
    if known:
        lines.insert(
            2,
            "These source words already exist. Copy them exactly and only fill the target side.\n"
            f"Known head: {known['word']} ({known['pos']}).\n"
            f"Known synonyms: {', '.join(known['synonyms']) or '(none)'}.\n"
            f"Known antonyms: {', '.join(known['antonyms']) or '(none)'}.\n",
        )
    return "".join(lines)


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
        raise ProviderDown("Could not load this card.") from exc


_ENTRY = {
    "type": "object",
    "properties": {
        "word": {"type": "string"},
        "pos": {"type": "string"},
        "definition": {"type": "string"},
        "example": {"type": "string"},
    },
    "required": ["word", "pos", "definition", "example"],
    "additionalProperties": False,
}
_LINKED = {
    "type": "object",
    "properties": {
        "of": {"type": "string"},
        "word": {"type": "string"},
        "pos": {"type": "string"},
        "definition": {"type": "string"},
        "example": {"type": "string"},
    },
    "required": ["of", "word", "pos", "definition", "example"],
    "additionalProperties": False,
}
CARD_SCHEMA = {
    "type": "object",
    "properties": {
        "source": {
            "type": "object",
            "properties": {
                "lan": {"type": "string"},
                "word": {"type": "string"},
                "pos": {"type": "string"},
                "definition": {"type": "string"},
                "example": {"type": "string"},
                "synonyms": {"type": "array", "items": _ENTRY},
                "antonyms": {"type": "array", "items": _ENTRY},
            },
            "required": ["lan", "word", "pos", "definition", "example", "synonyms", "antonyms"],
            "additionalProperties": False,
        },
        "target": {
            "type": "object",
            "properties": {
                "lan": {"type": "string"},
                "word": {"type": "string"},
                "pos": {"type": "string"},
                "definition": {"type": "string"},
                "example": {"type": "string"},
                "synonyms": {"type": "array", "items": _LINKED},
                "antonyms": {"type": "array", "items": _LINKED},
            },
            "required": ["lan", "word", "pos", "definition", "example", "synonyms", "antonyms"],
            "additionalProperties": False,
        },
    },
    "required": ["source", "target"],
    "additionalProperties": False,
}
LANGUAGES = (
    ("en", "English"),
    ("bn", "Bangla"),
    ("ar", "Arabic"),
)
LANGUAGE_NAMES = dict(LANGUAGES)


def _generate_gemini(prompt):
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        raise ProviderDown("Card lookup is not configured.")
    model = settings.GEMINI_MODEL
    payload = _post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
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
        raise ProviderDown("Could not load this card.") from exc


def _generate_openai(prompt):
    api_key = settings.OPENAI_API_KEY
    if not api_key:
        raise ProviderDown("Card lookup is not configured.")
    payload = _post(
        "https://api.openai.com/v1/chat/completions",
        {
            "model": settings.OPENAI_MODEL,
            "temperature": 0.4,
            "messages": [{"role": "user", "content": prompt}],
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
        raise ProviderDown("Could not load this card.") from exc


def _available_providers():
    preferred = settings.LLM_PROVIDER if settings.LLM_PROVIDER in PROVIDERS else "gemini"
    ordered = [preferred, *[name for name in PROVIDERS if name != preferred]]
    keys = {"gemini": settings.GEMINI_API_KEY, "openai": settings.OPENAI_API_KEY}
    return [name for name in ordered if keys[name]]


def generate_graph(prompt):
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
            payload = generators[name](prompt)
        except ProviderDown as exc:
            last = exc
            continue
        with _active_lock:
            _active = name
        return payload
    raise LookupFailed("Could not load this card.") from last


def lookup_card(word, options):
    from .words import lookup_word

    return lookup_word(word, options)
