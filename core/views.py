from urllib.parse import urlencode

from django.shortcuts import render
from django.urls import reverse

from .placeholders import PACK_CHOICES, RECENT, WORD_DETAILS, WORDPACKS
from .wiktionary import is_bangla, suggest_words


def search_url(**params):
    clean = {key: value for key, value in params.items() if value}
    if not clean:
        return reverse("home")
    return f"{reverse('home')}?{urlencode(clean)}"


def home(request):
    query = request.GET.get("q", "").strip()
    word = request.GET.get("word", "").strip()
    added = request.GET.get("added") == "1"
    show_pack = request.GET.get("pack") == "1" and bool(word)

    detail = WORD_DETAILS.get(word)
    if word and detail is None:
        detail = WORD_DETAILS["ancestor"]
    suggestions = suggest_words(query) if query and not word else []

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


def suggest(request):
    query = (request.GET.get("q") or request.GET.get("word") or "").strip()
    return render(request, "core/partials/word_preview.html", {
        "query": query,
        "suggestions": suggest_words(query),
    })
