"""
naics_classifier.py
-------------------
Maps a free-text product or component name ("aluminum housing", "LED module")
to a 6-digit NAICS industry so the emissions model can look up the matching
USEEIO intensity.

Two deterministic stages, no network calls:
  1. Curated phrases for common procurement terms (checked first, longest
     phrase wins).
  2. Lexical match against all USEEIO industry titles, weighted by how rare
     each word is (IDF) and biased toward manufacturing sectors.

If nothing matches, it returns the generic manufacturing prefix "33", which
the model resolves to the sector-median intensity.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from functools import lru_cache

from . import ml_bridge  # noqa: F401  (side-effect: configures sys.path for ml.*)


GENERIC_NAICS_CODE = "33"
GENERIC_NAICS_TITLE = "Manufacturing (generic, sector median)"


@dataclass(frozen=True)
class NaicsMatch:
    code: str
    title: str
    method: str       # "curated" | "lexical" | "fallback"
    confidence: str   # "high" | "medium" | "low"

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


# Phrase -> (code, USEEIO 2017 title). Phrases are matched on stemmed tokens.
_CURATED: dict[str, tuple[str, str]] = {
    # apparel & textiles
    "t shirt": ("315220", "Men's and Boys' Cut and Sew Apparel Manufacturing"),
    "tshirt": ("315220", "Men's and Boys' Cut and Sew Apparel Manufacturing"),
    "cotton t shirt": ("315220", "Men's and Boys' Cut and Sew Apparel Manufacturing"),
    "apparel": ("315280", "Other Cut and Sew Apparel Manufacturing"),
    "garment": ("315280", "Other Cut and Sew Apparel Manufacturing"),
    "clothing": ("315280", "Other Cut and Sew Apparel Manufacturing"),
    "fabric": ("313210", "Broadwoven Fabric Mills"),
    "cotton fabric": ("313210", "Broadwoven Fabric Mills"),
    "yarn": ("313110", "Fiber, Yarn, and Thread Mills"),
    "thread": ("313110", "Fiber, Yarn, and Thread Mills"),
    # electronics
    "circuit board": ("334412", "Bare Printed Circuit Board Manufacturing"),
    "printed circuit board": ("334412", "Bare Printed Circuit Board Manufacturing"),
    "pcb": ("334412", "Bare Printed Circuit Board Manufacturing"),
    "pcba": ("334418", "Printed Circuit Assembly (Electronic Assembly) Manufacturing"),
    "printed circuit assembly": ("334418", "Printed Circuit Assembly (Electronic Assembly) Manufacturing"),
    "semiconductor": ("334413", "Semiconductor and Related Device Manufacturing"),
    "chip": ("334413", "Semiconductor and Related Device Manufacturing"),
    "microchip": ("334413", "Semiconductor and Related Device Manufacturing"),
    "integrated circuit": ("334413", "Semiconductor and Related Device Manufacturing"),
    "led": ("334413", "Semiconductor and Related Device Manufacturing"),
    "led module": ("334413", "Semiconductor and Related Device Manufacturing"),
    "solar cell": ("334413", "Semiconductor and Related Device Manufacturing"),
    "solar panel": ("334413", "Semiconductor and Related Device Manufacturing"),
    "solar module": ("334413", "Semiconductor and Related Device Manufacturing"),
    "photovoltaic": ("334413", "Semiconductor and Related Device Manufacturing"),
    "display": ("334419", "Other Electronic Component Manufacturing"),
    "lcd": ("334419", "Other Electronic Component Manufacturing"),
    "touchscreen": ("334419", "Other Electronic Component Manufacturing"),
    "power adapter": ("335999", "All Other Miscellaneous Electrical Equipment and Component Manufacturing"),
    "power supply": ("335999", "All Other Miscellaneous Electrical Equipment and Component Manufacturing"),
    "ac adapter": ("335999", "All Other Miscellaneous Electrical Equipment and Component Manufacturing"),
    "charger": ("335999", "All Other Miscellaneous Electrical Equipment and Component Manufacturing"),
    "battery": ("335911", "Storage Battery Manufacturing"),
    "battery pack": ("335911", "Storage Battery Manufacturing"),
    "lithium ion": ("335911", "Storage Battery Manufacturing"),
    "electric motor": ("335312", "Motor and Generator Manufacturing"),
    "lamp": ("335110", "Electric Lamp Bulb and Part Manufacturing"),
    "light bulb": ("335110", "Electric Lamp Bulb and Part Manufacturing"),
    "desk lamp": ("335121", "Residential Electric Lighting Fixture Manufacturing"),
    "table lamp": ("335121", "Residential Electric Lighting Fixture Manufacturing"),
    "floor lamp": ("335121", "Residential Electric Lighting Fixture Manufacturing"),
    # metals
    "aluminum": ("331318", "Other Aluminum Rolling, Drawing, and Extruding"),
    "aluminum housing": ("331318", "Other Aluminum Rolling, Drawing, and Extruding"),
    "aluminum extrusion": ("331318", "Other Aluminum Rolling, Drawing, and Extruding"),
    "aluminum sheet": ("331315", "Aluminum Sheet, Plate, and Foil Manufacturing"),
    "aluminum foil": ("331315", "Aluminum Sheet, Plate, and Foil Manufacturing"),
    "steel": ("331110", "Iron and Steel Mills and Ferroalloy Manufacturing"),
    "steel pipe": ("331210", "Iron and Steel Pipe and Tube Manufacturing from Purchased Steel"),
    "steel tube": ("331210", "Iron and Steel Pipe and Tube Manufacturing from Purchased Steel"),
    "copper": ("331420", "Copper Rolling, Drawing, Extruding, and Alloying"),
    "fastener": ("332722", "Bolt, Nut, Screw, Rivet, and Washer Manufacturing"),
    "screw": ("332722", "Bolt, Nut, Screw, Rivet, and Washer Manufacturing"),
    "bolt": ("332722", "Bolt, Nut, Screw, Rivet, and Washer Manufacturing"),
    "metal stamping": ("332119", "Metal Crown, Closure, and Other Metal Stamping (except Automotive)"),
    # automotive
    "automotive component": ("336390", "Other Motor Vehicle Parts Manufacturing"),
    "automotive part": ("336390", "Other Motor Vehicle Parts Manufacturing"),
    "auto part": ("336390", "Other Motor Vehicle Parts Manufacturing"),
    "car part": ("336390", "Other Motor Vehicle Parts Manufacturing"),
    "vehicle part": ("336390", "Other Motor Vehicle Parts Manufacturing"),
    "wire harness": ("336320", "Motor Vehicle Electrical and Electronic Equipment Manufacturing"),
    "wiring harness": ("336320", "Motor Vehicle Electrical and Electronic Equipment Manufacturing"),
    "tire": ("326211", "Tire Manufacturing (except Retreading)"),
    # plastics, rubber, chemicals
    "plastic": ("326199", "All Other Plastics Product Manufacturing"),
    "plastic part": ("326199", "All Other Plastics Product Manufacturing"),
    "plastic housing": ("326199", "All Other Plastics Product Manufacturing"),
    "injection molded": ("326199", "All Other Plastics Product Manufacturing"),
    "plastic resin": ("325211", "Plastics Material and Resin Manufacturing"),
    "resin": ("325211", "Plastics Material and Resin Manufacturing"),
    "polymer": ("325211", "Plastics Material and Resin Manufacturing"),
    "plastic bottle": ("326160", "Plastics Bottle Manufacturing"),
    "pet bottle": ("326160", "Plastics Bottle Manufacturing"),
    "packaging film": ("326112", "Plastics Packaging Film and Sheet (including Laminated) Manufacturing"),
    "shrink wrap": ("326112", "Plastics Packaging Film and Sheet (including Laminated) Manufacturing"),
    "foam": ("326150", "Urethane and Other Foam Product (except Polystyrene) Manufacturing"),
    "polystyrene foam": ("326140", "Polystyrene Foam Product Manufacturing"),
    "rubber": ("326299", "All Other Rubber Product Manufacturing"),
    "adhesive": ("325520", "Adhesive Manufacturing"),
    "glue": ("325520", "Adhesive Manufacturing"),
    "sealant": ("325520", "Adhesive Manufacturing"),
    "paint": ("325510", "Paint and Coating Manufacturing"),
    "coating": ("325510", "Paint and Coating Manufacturing"),
    "ink": ("325910", "Printing Ink Manufacturing"),
    # paper, glass, packaging
    "cardboard": ("322211", "Corrugated and Solid Fiber Box Manufacturing"),
    "corrugated box": ("322211", "Corrugated and Solid Fiber Box Manufacturing"),
    "shipping box": ("322211", "Corrugated and Solid Fiber Box Manufacturing"),
    "carton": ("322211", "Corrugated and Solid Fiber Box Manufacturing"),
    "paper packaging": ("322219", "Other Paperboard Container Manufacturing"),
    "paper bag": ("322220", "Paper Bag and Coated and Treated Paper Manufacturing"),
    "paper cup": ("322219", "Other Paperboard Container Manufacturing"),
    "label": ("323111", "Commercial Printing (except Screen and Books)"),
    "glass bottle": ("327213", "Glass Container Manufacturing"),
    "glass jar": ("327213", "Glass Container Manufacturing"),
    # consumer goods
    "cosmetic": ("325620", "Toilet Preparation Manufacturing"),
    "toothpaste": ("325620", "Toilet Preparation Manufacturing"),
    "shampoo": ("325620", "Toilet Preparation Manufacturing"),
    "soap": ("325611", "Soap and Other Detergent Manufacturing"),
    "detergent": ("325611", "Soap and Other Detergent Manufacturing"),
    "toy": ("339930", "Doll, Toy, and Game Manufacturing"),
}

_STOPWORDS = frozenset({
    "a", "an", "and", "or", "the", "of", "for", "in", "on", "with", "to", "by",
    "except", "other", "all", "manufacturing", "manufacture", "manufacturer",
    "mill", "product", "including", "made", "purchased", "related", "type",
    "misc", "miscellaneous", "nec", "supplier", "custom",
})

# British -> US spellings used by NAICS titles (applied to stemmed tokens).
_SPELLING = {
    "aluminium": "aluminum",
    "tyre": "tire",
    "fibre": "fiber",
    "colour": "color",
    "mould": "mold",
    "moulded": "molded",
    "moulding": "molding",
}

# Query-side synonyms: token -> extra tokens that appear in USEEIO titles.
_SYNONYMS: dict[str, tuple[str, ...]] = {
    "box": ("paperboard",),
    "glue": ("adhesive",),
    "garment": ("apparel",),
    "clothing": ("apparel",),
    "shirt": ("apparel",),
    "cotton": ("fabric",),
    "chip": ("semiconductor",),
    "led": ("semiconductor",),
    "pellet": ("resin", "plastic"),
    "polymer": ("resin", "plastic"),
    "bulb": ("lamp",),
    "light": ("lighting",),
    "sofa": ("upholstered", "furniture"),
    "chair": ("furniture",),
    "desk": ("furniture",),
    "shoe": ("footwear",),
    "sneaker": ("footwear",),
    "boot": ("footwear",),
}

# Tokens that mark capital equipment. A title about machinery is only a good
# match when the query also mentions machinery.
_MACHINERY_TOKENS = frozenset({"machinery", "machine", "equipment"})


def _stem(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if token.endswith(("sses", "xes", "zes", "ches", "shes")):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us")):
        return token[:-1]
    return token


def _tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower().replace("-", " "))
    stems = (_stem(word) for word in words)
    return [_SPELLING.get(stem, stem) for stem in stems]


def _content_tokens(text: str) -> list[str]:
    return [token for token in _tokens(text) if token not in _STOPWORDS]


def _curated_phrases() -> list[tuple[tuple[str, ...], tuple[str, str]]]:
    phrases = [(tuple(_tokens(phrase)), target) for phrase, target in _CURATED.items()]
    # Longest phrase first so "desk lamp" beats "lamp".
    return sorted(phrases, key=lambda item: len(item[0]), reverse=True)


_CURATED_PHRASES = _curated_phrases()


def _contains_phrase(tokens: list[str], phrase: tuple[str, ...]) -> bool:
    width = len(phrase)
    return any(tuple(tokens[i:i + width]) == phrase for i in range(len(tokens) - width + 1))


@lru_cache(maxsize=1)
def _title_index() -> tuple[list[tuple[str, str, frozenset[str]]], dict[str, float]]:
    """(code, title, token set) per USEEIO industry, plus IDF weights."""
    from ml.reference_data import NAICS_DETAIL  # type: ignore

    entries = [
        (code, title, frozenset(_content_tokens(title)))
        for code, (_n2, title, _val) in NAICS_DETAIL.items()
        if len(code) == 6
    ]
    document_count = max(len(entries), 1)
    frequency: dict[str, int] = {}
    for _code, _title, tokens in entries:
        for token in tokens:
            frequency[token] = frequency.get(token, 0) + 1
    idf = {
        token: math.log((document_count + 1) / (count + 0.5))
        for token, count in frequency.items()
    }
    return entries, idf


def _sector_weight(code: str) -> float:
    """Prefer industries that make things over those that sell or service them."""
    sector = code[:2]
    if sector in ("31", "32", "33"):
        return 1.0
    if sector in ("11", "21"):
        return 0.85
    if sector in ("22", "23"):
        return 0.6
    return 0.35


def _lexical_match(product: str) -> NaicsMatch | None:
    base_tokens = list(dict.fromkeys(_content_tokens(product)))
    if not base_tokens:
        return None

    query = set(base_tokens)
    for token in base_tokens:
        query.update(_SYNONYMS.get(token, ()))

    entries, idf = _title_index()
    if not entries:
        return None

    wants_machinery = bool(query & _MACHINERY_TOKENS)
    best: tuple[float, str, str, frozenset[str]] | None = None
    for code, title, title_tokens in entries:
        overlap = query & title_tokens
        if not overlap:
            continue
        score = sum(idf.get(token, 0.0) for token in overlap)
        score /= math.sqrt(len(title_tokens))
        score *= _sector_weight(code)
        if not wants_machinery and title_tokens & _MACHINERY_TOKENS:
            score *= 0.6
        if best is None or score > best[0]:
            best = (score, code, title, title_tokens)

    if best is None:
        return None

    _score, code, title, title_tokens = best
    matched_base = [
        token
        for token in base_tokens
        if token in title_tokens
        or any(synonym in title_tokens for synonym in _SYNONYMS.get(token, ()))
    ]
    coverage = len(matched_base) / len(base_tokens)
    confidence = "high" if coverage >= 0.99 else "medium" if coverage >= 0.5 else "low"
    return NaicsMatch(code=code, title=title, method="lexical", confidence=confidence)


def lookup_naics(code: str) -> NaicsMatch | None:
    """Describe an exact 6-digit USEEIO code (e.g. one proposed by the agent)."""
    from ml.reference_data import NAICS_DETAIL  # type: ignore

    normalized = str(code or "").strip()
    entry = NAICS_DETAIL.get(normalized) if len(normalized) == 6 else None
    if entry is None:
        return None
    return NaicsMatch(code=normalized, title=entry[1], method="agent", confidence="medium")


@lru_cache(maxsize=512)
def classify_naics(product: str) -> NaicsMatch:
    """Best-effort product/component name -> NAICS industry match."""
    tokens = _tokens(product)
    for phrase, (code, title) in _CURATED_PHRASES:
        if phrase and _contains_phrase(tokens, phrase):
            return NaicsMatch(code=code, title=title, method="curated", confidence="high")

    lexical = _lexical_match(product)
    if lexical is not None:
        return lexical

    return NaicsMatch(
        code=GENERIC_NAICS_CODE,
        title=GENERIC_NAICS_TITLE,
        method="fallback",
        confidence="low",
    )
