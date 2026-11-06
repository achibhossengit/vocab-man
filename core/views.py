from urllib.parse import urlencode

from django.shortcuts import render
from django.urls import reverse

from .placeholders import (
    BANGLA_SUGGESTIONS,
    ENGLISH_SUGGESTIONS,
    PACK_CHOICES,
    RECENT,
    WORD_DETAILS,
    WORDPACKS,
)


def search_url(**params):
    clean = {key: value for key, value in params.items() if value}
    if not clean:
        return reverse("home")
    return f"{reverse('home')}?{urlencode(clean)}"


def is_bangla(text):
    return any("\u0980" <= char <= "\u09ff" for char in text)


def home(request):
    query = request.GET.get("q", "").strip()
    word = request.GET.get("word", "").strip()
    added = request.GET.get("added") == "1"
    show_pack = request.GET.get("pack") == "1" and bool(word)

    detail = WORD_DETAILS.get(word)
    if word and detail is None:
        detail = WORD_DETAILS["ancestor"]
    if query and not word:
        source = BANGLA_SUGGESTIONS if is_bangla(query) else ENGLISH_SUGGESTIONS
        suggestions = [{"word": item, "bn": is_bangla(item)} for item in source]
    else:
        suggestions = []

    stage = "empty"
    if word and detail:
        stage = "added" if added else "selected"
    elif query:
        stage = "preview"

    field_value = word or query
    selected_url = search_url(q=query, word=word) if word else ""
    return render(request, "core/home.html", {
        "nav": "home",
        "query": query,
        "word": word,
        "stage": stage,
        "field_value": field_value,
        "field_bn": is_bangla(field_value),
        "suggestions": suggestions,
        "detail": detail,
        "show_pack": show_pack,
        "pack_choices": PACK_CHOICES,
        "recent": RECENT if stage != "empty" else [],
        "wordpacks": WORDPACKS if stage != "empty" else [],
        "clear_url": reverse("home"),
        "pack_url": search_url(q=query, word=word, pack="1"),
        "added_url": search_url(q=query, word=word, added="1"),
        "selected_url": selected_url,
    })
