import json
from urllib.parse import urlencode

from django.shortcuts import redirect, render
from django.urls import reverse

from .llm import LookupFailed, card_options, lookup_card
from .placeholders import PACK_CHOICES, RECENT, WORDPACKS
from .wiktionary import is_bangla, suggest_words


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
    show_pack = request.GET.get("pack") == "1" and bool(word)
    detail = None
    card_error = ""
    card_params = {
        "word": word,
        "tone": options["tone"],
        "synonyms": options["synonyms"],
        "antonyms": options["antonyms"],
        "examples": options["examples"],
    }
    selected_url = search_url(**card_params) if word else ""
    query_string = urlencode(card_params) if word else ""
    fresh = request.GET.get("new") == "1"
    if word:
        cache_key = json.dumps([word, options], ensure_ascii=False, sort_keys=True)
        cached = request.session.get("card_cache") or {}
        if not fresh and cached.get("key") == cache_key:
            detail = cached.get("card")
        else:
            try:
                detail = lookup_card(word, options)
            except LookupFailed as exc:
                card_error = str(exc)
            if detail:
                request.session["card_cache"] = {"key": cache_key, "card": detail}
            elif not card_error:
                card_error = "Could not load this card. Try Refresh."

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
        "show_pack": show_pack and bool(detail),
        "selected_url": selected_url,
        "pack_url": search_url(**card_params, pack="1"),
        "added_url": search_url(**card_params, added="1"),
        "pack_get": f"{reverse('pack')}?{query_string}" if query_string else "",
        "added_get": f"{reverse('card')}?{urlencode({**card_params, 'added': '1'})}" if word else "",
        "redirect_fresh": bool(detail and fresh and request.headers.get("HX-Request") != "true"),
    }


def home(request):
    state = card_state(request)
    if state["redirect_fresh"]:
        return redirect(state["selected_url"])
    field_value = state["word"] or state["query"]
    options = state["options"]
    return render(request, "core/home.html", {
        "nav": "home",
        "query": state["query"],
        "word": state["word"],
        "stage": state["stage"],
        "field_value": field_value,
        "field_bn": is_bangla(field_value),
        "suggestions": suggest_words(state["query"]) if state["query"] and not state["word"] else [],
        "detail": state["detail"],
        "card_error": state["card_error"],
        "card_tone": options["tone"],
        "max_synonyms": options["synonyms"],
        "max_antonyms": options["antonyms"],
        "max_examples": options["examples"],
        "show_pack": state["show_pack"],
        "pack_choices": PACK_CHOICES,
        "recent": RECENT,
        "wordpacks": WORDPACKS,
        "clear_url": reverse("home"),
        "pack_url": state["pack_url"],
        "added_url": state["added_url"],
        "pack_get": state["pack_get"],
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
        "pack_url": state["pack_url"],
        "pack_get": state["pack_get"],
        "added_url": state["added_url"],
        "selected_url": state["selected_url"],
    })
    push = state["added_url"] if added else state["selected_url"]
    if push:
        response["HX-Push-Url"] = push
    return response


def pack(request):
    state = card_state(request)
    response = render(request, "core/partials/add_pack.html", {
        "word": state["word"],
        "detail": state["detail"],
        "pack_choices": PACK_CHOICES,
        "selected_url": state["selected_url"],
        "added_url": state["added_url"],
        "added_get": state["added_get"],
    })
    if state["pack_url"] and state["detail"]:
        response["HX-Push-Url"] = state["pack_url"]
    return response


def suggest(request):
    query = (request.GET.get("q") or request.GET.get("word") or "").strip()
    return render(request, "core/partials/word_preview.html", {
        "query": query,
        "suggestions": suggest_words(query),
    })
