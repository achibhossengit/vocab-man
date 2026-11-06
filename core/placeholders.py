ENGLISH_SUGGESTIONS = ["ancestors", "ancestor", "ancestor worship"]
BANGLA_SUGGESTIONS = ["পূর্ব", "পূর্বপুরুষ", "পূর্বসূরি"]

WORD_DETAILS = {
    "ancestor": {
        "meaning": "পূর্বপুরুষ",
        "meaning_bn": True,
        "pos": ["Noun", "Verb"],
        "synonyms": ["father", "predecessor", "forefather", "sire", "progenitor"],
        "antonyms": ["descendant", "offspring", "successor", "heir"],
        "examples": [
            "My ancestor Admiral Anson circumnavigated the globe 250 years ago.",
            "His descendant still keeps the family name.",
        ],
    },
    "পূর্বপুরুষ": {
        "meaning": "ancestor",
        "meaning_bn": False,
        "pos": ["Noun", "Verb"],
        "synonyms": ["father", "predecessor", "forefather", "sire", "progenitor"],
        "antonyms": ["descendant", "offspring", "successor", "heir"],
        "examples": [
            "My ancestor Admiral Anson circumnavigated the globe 250 years ago.",
            "His descendant still keeps the family name.",
        ],
    },
}

RECENT = [
    {"word": "light", "meaning": "আলো", "saved": True},
    {"word": "book", "meaning": "বই", "saved": True},
    {"word": "give up", "meaning": "হাল ছেড়ে দেওয়া", "saved": False},
    {"word": "ancestor", "meaning": "পূর্বপুরুষ", "saved": True},
]

WORDPACKS = [
    {"name": "cedar lantern", "count": "1 word", "range": "ancestor–descendant"},
    {"name": "wordpack-6", "count": "8 words", "range": "father–heir"},
    {"name": "wordpack-4", "count": "14 words", "range": "light–book"},
    {"name": "quiet harbor", "count": "6 words", "range": "water–friend"},
    {"name": "wordpack-5", "count": "20 words", "range": "give up–understand"},
]

PACK_CHOICES = [
    {"name": "wordpack-6", "count": "8", "selected": True},
    {"name": "wordpack-4", "count": "14", "selected": False},
]
