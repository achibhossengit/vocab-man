from django.db import IntegrityError, transaction
from django.db.models import Q
from django.db.models.functions import Lower

from .llm import LANGUAGE_NAMES, LookupFailed, _prompt, generate_graph
from .models import WordProfile, WordRelation

STORE_LIMIT = 5


def split_pair(pair):
    parts = str(pair or "").split("-", 1)
    if len(parts) == 2 and parts[0] in LANGUAGE_NAMES and parts[1] in LANGUAGE_NAMES and parts[0] != parts[1]:
        return parts[0], parts[1]
    return WordProfile.Lan.EN, WordProfile.Lan.BN


def _script(lan, char):
    if lan == WordProfile.Lan.BN:
        return "\u0980" <= char <= "\u09ff"
    if lan == WordProfile.Lan.AR:
        return "\u0600" <= char <= "\u06ff" or "\u0750" <= char <= "\u077f"
    if lan == WordProfile.Lan.EN:
        return "A" <= char <= "Z" or "a" <= char <= "z"
    return False


def word_language(word, known, learn):
    scores = {known: 0, learn: 0}
    for char in word:
        if _script(known, char):
            scores[known] += 1
        if _script(learn, char):
            scores[learn] += 1
    if scores[learn] > scores[known]:
        return learn
    if scores[known]:
        return known
    if scores[learn]:
        return learn
    return known


def _clean(value):
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def _items(value):
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)][:STORE_LIMIT]


def suggest_words(term, lan="en"):
    term = _clean(term)
    if not term or lan not in LANGUAGE_NAMES:
        return []
    exact = (
        WordProfile.objects.filter(lan=lan, word__iexact=term)
        .values_list("word", flat=True)
        .first()
    )
    rows = (
        WordProfile.objects.filter(lan=lan, word__istartswith=term)
        .exclude(word__iexact=term)
        .annotate(word_key=Lower("word"))
        .order_by("word_key")
        .values_list("word", "word_key")
    )
    words = [exact] if exact else []
    seen = {term.casefold()} if exact else set()
    for word, key in rows:
        if key in seen:
            continue
        seen.add(key)
        words.append(word)
        if len(words) == 5:
            break
    return [{"word": word, "bn": lan == WordProfile.Lan.BN} for word in words]


def find_profiles(lan, word):
    word = _clean(word)
    if not word:
        return []
    return list(WordProfile.objects.filter(lan=lan, word__iexact=word).order_by("id"))


def _links(profile):
    return WordRelation.objects.filter(Q(source=profile) | Q(target=profile)).select_related(
        "source", "target"
    ).order_by("id")


def _other(profile, relation):
    if relation.source_id == profile.id:
        return relation.target
    return relation.source


def _lexical(profile, kind):
    found = []
    seen = set()
    for relation in _links(profile):
        if relation.relation != kind:
            continue
        other = _other(profile, relation)
        if other.lan != profile.lan or other.id in seen:
            continue
        seen.add(other.id)
        found.append(other)
    return found


def _unique(words):
    found = []
    seen = set()
    for word in words:
        key = word.casefold()
        if key in seen:
            continue
        seen.add(key)
        found.append(word)
    return found


def _antonym_hubs(profile):
    hubs = []
    for hub in _lexical(profile, WordRelation.Kind.ANTONYM):
        siblings = _lexical(hub, WordRelation.Kind.ANTONYM)
        if len(siblings) > 1 and any(item.id == profile.id for item in siblings):
            hubs.append(hub)
    return hubs


def _grouped(profile, synonym_limit, antonym_limit):
    direct = _lexical(profile, WordRelation.Kind.SYNONYM)
    hubs = _antonym_hubs(profile) if not direct else []
    if hubs:
        synonyms = []
        antonyms = []
        for hub in hubs:
            shown_antonyms = _lexical(hub, WordRelation.Kind.ANTONYM)[:antonym_limit]
            if any(item.id == profile.id for item in shown_antonyms):
                synonyms.extend(item.word for item in shown_antonyms if item.id != profile.id)
            else:
                synonyms.extend(
                    item.word for item in _lexical(hub, WordRelation.Kind.ANTONYM) if item.id != profile.id
                )
            antonyms.extend(item.word for item in _lexical(hub, WordRelation.Kind.SYNONYM)[:synonym_limit])
            antonyms.append(hub.word)
        return _unique(synonyms), _unique(antonyms), synonym_limit + len(hubs)

    if len(direct) == 1:
        hub = direct[0]
        synonyms = [
            hub.word if item.id == profile.id else item.word
            for item in _lexical(hub, WordRelation.Kind.SYNONYM)
        ]
    else:
        synonyms = [item.word for item in direct]
    antonyms = _lexical(profile, WordRelation.Kind.ANTONYM)
    if not antonyms and len(direct) == 1:
        antonyms = _lexical(direct[0], WordRelation.Kind.ANTONYM)
    return _unique(synonyms), [item.word for item in antonyms], antonym_limit


def _translation(profile, other_lan):
    for relation in _links(profile):
        other = _other(profile, relation)
        if relation.relation == WordRelation.Kind.SYNONYM and other.lan == other_lan:
            return other
    return None


def _side(source_profile, target_profile, lan):
    if lan == target_profile.lan:
        return target_profile
    return source_profile


def card_from_profiles(source_profile, target_profile, options):
    learned = _side(source_profile, target_profile, options["learn"])
    example = _clean(learned.example)
    synonyms, antonyms, antonym_limit = _grouped(learned, options["synonyms"], options["antonyms"])
    return {
        "meaning": target_profile.word,
        "meaning_bn": target_profile.lan == WordProfile.Lan.BN,
        "pos": [source_profile.pos] if source_profile.pos else [],
        "pos_bn": source_profile.lan == WordProfile.Lan.BN,
        "definition": learned.definition,
        "definition_bn": learned.lan == WordProfile.Lan.BN,
        "synonyms": synonyms[: options["synonyms"]],
        "synonyms_bn": learned.lan == WordProfile.Lan.BN,
        "antonyms": antonyms[:antonym_limit],
        "antonyms_bn": learned.lan == WordProfile.Lan.BN,
        "examples": [example][: options["examples"]] if example else [],
        "examples_bn": learned.lan == WordProfile.Lan.BN,
    }


def known_cluster(profile):
    synonyms, antonyms, antonym_limit = _grouped(profile, STORE_LIMIT, STORE_LIMIT)
    return {
        "word": profile.word,
        "pos": profile.pos,
        "synonyms": synonyms[:STORE_LIMIT],
        "antonyms": antonyms[:antonym_limit],
    }


def upsert_profile(lan, word, pos, definition, example):
    word = _clean(word)
    pos = _clean(pos)
    definition = _clean(definition)
    example = _clean(example)
    if lan not in LANGUAGE_NAMES or not word or not pos:
        return None
    with transaction.atomic():
        found = WordProfile.objects.filter(lan=lan, word__iexact=word, pos__iexact=pos).first()
        if found:
            changed = False
            if not found.definition and definition:
                found.definition = definition
                changed = True
            if not found.example and example:
                found.example = example
                changed = True
            if changed:
                found.save()
            return found
        try:
            return WordProfile.objects.create(
                lan=lan,
                word=word,
                pos=pos,
                definition=definition,
                example=example,
            )
        except IntegrityError:
            return WordProfile.objects.filter(lan=lan, word__iexact=word, pos__iexact=pos).first()


def link(left, right, kind):
    if left is None or right is None or left.id == right.id:
        return
    source, target = (left, right) if left.id < right.id else (right, left)
    with transaction.atomic():
        WordRelation.objects.get_or_create(source=source, target=target, relation=kind)


def _remember(bucket, profile):
    if profile is not None:
        bucket.setdefault(profile.word.casefold(), profile)


def _save_source(data, lan):
    head = upsert_profile(lan, data.get("word"), data.get("pos"), data.get("definition"), data.get("example"))
    bucket = {}
    _remember(bucket, head)
    synonyms = []
    antonyms = []
    for item in _items(data.get("synonyms")):
        profile = upsert_profile(lan, item.get("word"), item.get("pos"), item.get("definition"), item.get("example"))
        link(head, profile, WordRelation.Kind.SYNONYM)
        _remember(bucket, profile)
        if profile is not None:
            synonyms.append(profile)
    for item in _items(data.get("antonyms")):
        profile = upsert_profile(lan, item.get("word"), item.get("pos"), item.get("definition"), item.get("example"))
        link(head, profile, WordRelation.Kind.ANTONYM)
        _remember(bucket, profile)
        if profile is not None:
            antonyms.append(profile)
    return head, bucket


def _save_target(data, lan, source_head, bucket):
    head = upsert_profile(lan, data.get("word"), data.get("pos"), data.get("definition"), data.get("example"))
    link(source_head, head, WordRelation.Kind.SYNONYM)
    for item in _items(data.get("synonyms")):
        matched = bucket.get(_clean(item.get("of")).casefold())
        if matched is None:
            continue
        profile = upsert_profile(lan, item.get("word"), item.get("pos"), item.get("definition"), item.get("example"))
        link(head, profile, WordRelation.Kind.SYNONYM)
        link(matched, profile, WordRelation.Kind.SYNONYM)
    for item in _items(data.get("antonyms")):
        matched = bucket.get(_clean(item.get("of")).casefold())
        if matched is None:
            continue
        profile = upsert_profile(lan, item.get("word"), item.get("pos"), item.get("definition"), item.get("example"))
        link(head, profile, WordRelation.Kind.ANTONYM)
        link(matched, profile, WordRelation.Kind.SYNONYM)
    return head


def save_payload(payload, source_lan, target_lan):
    source = payload.get("source") if isinstance(payload, dict) else None
    target = payload.get("target") if isinstance(payload, dict) else None
    if not isinstance(source, dict) or not isinstance(target, dict):
        return
    if source.get("lan") != source_lan or target.get("lan") != target_lan:
        return
    with transaction.atomic():
        head, bucket = _save_source(source, source_lan)
        _save_target(target, target_lan, head, bucket)


def lookup_word(word, options, generate=None):
    word = _clean(word)
    if not word:
        return None
    known, learn = split_pair(options.get("pair"))
    source_lan = word_language(word, known, learn)
    target_lan = learn if source_lan == known else known
    profiles = find_profiles(source_lan, word)
    for profile in profiles:
        target_profile = _translation(profile, target_lan)
        if target_profile is not None:
            return card_from_profiles(profile, target_profile, options)
    known = known_cluster(profiles[0]) if profiles else None
    prompt = _prompt(word, source_lan, target_lan, known)
    payload = (generate or generate_graph)(prompt)
    if not isinstance(payload, dict):
        return None
    source = payload.get("source")
    target = payload.get("target")
    if not isinstance(source, dict) or not isinstance(target, dict):
        return None
    if source.get("lan") != source_lan or target.get("lan") != target_lan:
        raise LookupFailed("Could not load this card.")
    source["word"] = known["word"] if known else word
    if known:
        source["pos"] = known["pos"]
    save_payload(payload, source_lan, target_lan)
    for profile in find_profiles(source_lan, word):
        target_profile = _translation(profile, target_lan)
        if target_profile is not None:
            return card_from_profiles(profile, target_profile, options)
    return None
