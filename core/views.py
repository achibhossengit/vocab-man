from urllib.parse import urlencode

from django.shortcuts import redirect, render
from django.urls import reverse

from .llm import LANGUAGES, LookupFailed, card_options
from .placeholders import PACK_CHOICES, RECENT, WORDPACKS
from .words import lookup_word, split_pair, suggest_words, word_language


def search_url(**params):
    clean = {key: value for key, value in params.items() if value or value == 0}
    if not clean:
        return reverse("home")
    return f"{reverse('home')}?{urlencode(clean)}"


def card_state(request):
    query = request.GET.get("q", "").strip()
    word = request.GET.get("word", "").strip()
    added = request.GET.get("added") == "1"
    options = card_options(request.GET)
    detail = None
    card_error = ""
    card_params = {
        "word": word,
        "pair": options["pair"],
    }
    selected_url = search_url(**card_params) if word else ""
    fresh = request.GET.get("new") == "1"
    if word:
        try:
            detail = lookup_word(word, options)
        except LookupFailed as exc:
            card_error = str(exc)
        if not detail and not card_error:
            card_error = "Not found."

    stage = "empty"
    if word and detail:
        stage = "added" if added else "selected"
    elif word and card_error:
        stage = "selected"
    elif query:
        stage = "preview"

    return {
        "query": query,
        "word": word,
        "added": added,
        "options": options,
        "detail": detail,
        "card_error": card_error,
        "stage": stage,
        "selected_url": selected_url,
        "added_url": search_url(**card_params, added="1"),
        "added_get": f"{reverse('card')}?{urlencode({**card_params, 'added': '1'})}" if word else "",
        "redirect_fresh": bool(detail and fresh and request.headers.get("HX-Request") != "true"),
    }


def home(request):
    state = card_state(request)
    if state["redirect_fresh"]:
        return redirect(state["selected_url"])
    field_value = state["word"] or state["query"]
    options = state["options"]
    known, learn = split_pair(options["pair"])
    names = dict(LANGUAGES)
    field_lan = word_language(field_value, known, learn) if field_value else known
    suggest_lan = word_language(state["query"], known, learn) if state["query"] else known
    return render(request, "core/home.html", {
        "nav": "home",
        "query": state["query"],
        "word": state["word"],
        "stage": state["stage"],
        "field_value": field_value,
        "field_bn": field_lan == "bn",
        "card_pair": options["pair"],
        "known_name": names[known],
        "learn_name": names[learn],
        "languages": [{"code": code, "name": name} for code, name in LANGUAGES],
        "suggestions": suggest_words(state["query"], suggest_lan) if state["query"] and not state["word"] else [],
        "detail": state["detail"],
        "card_error": state["card_error"],
        "pack_choices": PACK_CHOICES,
        "recent": RECENT,
        "wordpacks": WORDPACKS,
        "clear_url": reverse("home"),
        "added_url": state["added_url"],
        "added_get": state["added_get"],
        "selected_url": state["selected_url"],
    })


def card(request):
    state = card_state(request)
    added = state["added"] and bool(state["detail"])
    response = render(request, "core/partials/word_card.html", {
        "detail": state["detail"],
        "card_error": state["card_error"],
        "stage": "added" if added else "selected",
        "pack_choices": PACK_CHOICES,
        "added_url": state["added_url"],
        "added_get": state["added_get"],
    })
    push = state["added_url"] if added else state["selected_url"]
    if push:
        response["HX-Push-Url"] = push
    return response


def suggest(request):
    query = (request.GET.get("q") or request.GET.get("word") or "").strip()
    options = card_options(request.GET)
    known, learn = split_pair(options["pair"])
    return render(request, "core/partials/word_preview.html", {
        "query": query,
        "card_pair": options["pair"],
        "suggestions": suggest_words(query, word_language(query, known, learn)),
    })
