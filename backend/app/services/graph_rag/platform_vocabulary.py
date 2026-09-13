"""The platform's field vocabulary, as a bridge into the knowledge graph.

Why this module exists
----------------------
The platform and the knowledge graph each keep their own words for the same
physical quantity, and nothing connected them.

* ``ingestion/schema_registry.py`` is the platform's *data contract*: every
  column the modelling chain accepts, with its canonical name, Chinese label,
  accepted aliases and unit (``air_temp`` / ``平均气温`` / ``气温`` / ``tem_avg``).
* ``lexicon.py``'s ``BILINGUAL`` table is the graph's *translation table*: a
  hand-written list that lets a Chinese question reach the inherited graph's
  UPPERCASE ENGLISH entity names (``气温`` → ``AIR TEMPERATURE``).

Two hand-maintained lists, no code path between them. The consequence is
measurable: the turbidity model's own diagnosis ranks ``气温`` as a driver, and
``AIR TEMPERATURE`` is a real node of the inherited graph, yet ``气温`` reached
*nothing* — because ``气温`` happens to be absent from both the platform's
labels (which say ``平均气温``) and the graph's table. Neither list was wrong on
its own; the seam between them was simply never built.

What this module does
---------------------
It derives the bridge from the registry instead of writing it out by hand:

``terms``
    Every :class:`~...schema_registry.FieldSpec` across all six
    ``DATASET_SPECS`` — one :class:`PlatformTerm` each, carrying the field's
    label, canonical name and *unambiguous* aliases.
``bridges_to``
    Which graph entities a term names, decided by token alignment between the
    term's Latin forms and the entity's own name. ``air_temp`` → ``AIR
    TEMPERATURE`` matches on ``air`` (equal) and ``temp`` (a prefix of
    ``temperature``); ``WIND SPEED`` also matches ``ANNUAL WIND SPEED``, because
    the term's tokens are a subsequence of the entity's.
``expand``
    The reverse direction, for a *model feature* rather than a column name:
    given ``气温`` it returns the surfaces of the registry field that names the
    same quantity (``平均气温``, ``air_temp``, ``tem_avg``), which the linker can
    then resolve. This is the half the turbidity diagnosis needs, because the
    model names its features in prose, not in column names.

Two deliberate refusals
-----------------------
**No guessing.** Alignment is token-wise and conservative, and an alias that
two different fields both claim is dropped rather than assigned to either. The
registry really does list ``temperature`` under both ``water_temp`` and
``air_temp``; resolving that by preference would put a fabricated edge in the
graph's provenance, which is the one thing this feature may not do.

**No obligation to match.** A model feature like ``自净指数`` or
``年周期正弦分量`` is an internal construct with no counterpart in the
literature graph. The honest answer there is "the graph does not cover this
factor", and the caller is expected to say so rather than to invent support.
The bridge therefore widens what *can* resolve without pretending everything
does.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache

from backend.app.services.ingestion import schema_registry as registry

# CJK Unified Ideographs and Extension A, spelled as codepoint ranges rather
# than as a literal character class: the class's upper endpoint (U+9FFF) is a
# glyph the repository's encoding guard reads as mojibake, and it is right to —
# no source file should carry a lone U+9FFF for the sake of a regex boundary.
_CJK_RANGES = ((0x3400, 0x4DBF), (0x4E00, 0x9FFF))
_HAS_CJK = re.compile("[" + "".join(f"{chr(lo)}-{chr(hi)}" for lo, hi in _CJK_RANGES) + "]")

_LATIN_RUN = re.compile(r"[a-z0-9]+")
_BRACKETS = re.compile(r"[（）()\[\]【】《》]")
_WHITESPACE = re.compile(r"\s+")

#: A Latin token this long or longer may be matched by prefix, so ``temp``
#: reaches ``temperature`` and ``wind`` reaches ``windspeed``. Shorter tokens
#: must match exactly: ``air`` must not become ``airport``, and ``do``
#: (dissolved oxygen) must not become ``domestic``.
MIN_PREFIX_TOKEN = 4

#: The shortest token a *whole-tuple* match may rest on. ``TP``/``PH``/``DO``
#: are genuine registry canonicals and genuine graph entities, so an exact
#: two-letter match is real evidence; a two-letter token matched by containment
#: would be noise.
MIN_ANCHOR_TOKEN = 3

#: How many entities one term may bridge to. ``flow`` legitimately reaches
#: ``FLOW``, ``PEAK FLOW``, ``BASE FLOW``, ``STORM FLOW``… and a handful of
#: variants is signal. An unbounded fan-out would mean the term is really a
#: common word, and past this point it stops being evidence for any of them.
MAX_ENTITIES_PER_TERM = 64

#: The shortest CJK span allowed to join a feature name to a field label.
#: ``气温`` inside ``平均气温`` is the case this exists for; a single character
#: would join unrelated words (风 in 风格).
MIN_CJK_OVERLAP = 2

#: Leading qualifiers the registry puts on a column name that prose drops.
#: The column is ``平均气温``; every person and every model that mentions it
#: writes ``气温``. Stripping the qualifier is a fact about *this* vocabulary —
#: the registry's labels are column headers, and a column header carries its
#: aggregation because two columns of one file must be distinguishable.
#:
#: Liberal on purpose: a stripped form only matters if the remainder is itself a
#: registered surface of some field, so a bad strip (站点名称 → 名称) resolves to
#: nothing and costs nothing.
_CN_MODIFIERS = (
    "平均", "日均", "当天", "当日", "相对", "实测", "有效", "最高", "最低",
    "上游", "下游", "站点", "断面", "瞬时", "累计",
)


def _fold(text: object) -> str:
    """NFKC + casefold — the same folding the registry applies to headers."""
    return unicodedata.normalize("NFKC", str(text or "")).casefold()


def _flatten(text: object) -> str:
    """Folded, with brackets and every internal space removed."""
    return _WHITESPACE.sub("", _BRACKETS.sub("", _fold(text))).strip()


def _tokens(text: object) -> tuple[str, ...]:
    """Lowercase alphanumeric runs. Chinese-only names yield ``()`` by design."""
    return tuple(_LATIN_RUN.findall(_fold(text)))


def _token_key(token: str) -> str:
    """The bucket a token is filed under.

    Two tokens can only be prefix-compatible if their keys collide, which is
    what makes the lookup an index rather than a scan: ``temperature`` and
    ``temp`` both key on ``temp``, while ``air`` and ``airport`` key on ``air``
    and ``airp`` — correctly, since neither may match the other.
    """
    return token if len(token) < MIN_PREFIX_TOKEN else token[:MIN_PREFIX_TOKEN]


def _compatible(left: str, right: str) -> bool:
    """One token standing for another: equal, or a long-enough prefix."""
    if left == right:
        return True
    if len(left) < MIN_PREFIX_TOKEN or len(right) < MIN_PREFIX_TOKEN:
        return False
    return left.startswith(right) or right.startswith(left)


def _covers(needle: tuple[str, ...], haystack: tuple[str, ...]) -> bool:
    """Every token of ``needle`` met, in order, by a token of ``haystack``.

    Subsequence rather than prefix, because the entity names carry qualifiers
    the registry does not: ``WIND SPEED`` has to reach ``ANNUAL WIND SPEED``,
    and ``WATER LEVEL`` has to reach ``HUANGDU WATER LEVEL``. A greedy walk is
    exact for subsequence matching, so no backtracking is needed.
    """
    if needle == haystack:
        return True
    if not needle or len(needle) > len(haystack):
        return False
    if min(len(token) for token in needle) < 2:
        return False
    if max(len(token) for token in needle) < MIN_ANCHOR_TOKEN:
        return False
    remaining = iter(haystack)
    return all(any(_compatible(token, candidate) for candidate in remaining) for token in needle)


@dataclass(frozen=True)
class BridgeMatch:
    """One graph entity a registry field names, and how completely."""

    term: PlatformTerm
    #: How much of the entity's name the field accounts for — the shorter token
    #: tuple over the longer. ``1.0`` when the field's own name is the entity's
    #: name (``air_temp`` → ``AIR TEMPERATURE``), ``0.5`` when a single-token
    #: field is only half of it (``air_temp`` → ``TEMPERATURE``). This is what
    #: lets the caller find a field's *primary* entity rather than treating
    #: every entity that mentions the quantity as equally intended.
    coverage: float


def _coverage(left: tuple[str, ...], right: tuple[str, ...]) -> float:
    if not left or not right:
        return 0.0
    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
    return len(shorter) / len(longer)


def _aligned(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    """Whether two token tuples name the same thing, shorter inside longer.

    Dominance is required as well as containment: the shorter side must account
    for at least half the longer side's tokens. Without it, the single token
    ``turbidity`` reaches ``TURBIDITY HISTESIS PATTERNS`` and every other
    research construct that happens to mention turbidity — nine extra entities
    competing for a seed budget that ``TURBIDITY`` itself should have. A name is
    *about* the quantity when the quantity is most of what it says.
    """
    if not left or not right:
        return False
    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
    if len(shorter) * 2 < len(longer):
        return False
    return _covers(shorter, longer)


@dataclass(frozen=True)
class PlatformTerm:
    """One registry field, as the linker sees it."""

    data_type: str
    canonical: str
    label: str
    unit: str | None
    #: The surfaces worth matching a question or a feature name against: the
    #: Chinese label, the canonical column name, and every alias no other field
    #: also claims.
    surfaces: tuple[str, ...]
    #: Latin token forms drawn from those surfaces, for the graph-side bridge.
    token_forms: tuple[tuple[str, ...], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "data_type": self.data_type,
            "canonical": self.canonical,
            "label": self.label,
            "unit": self.unit,
            "surfaces": list(self.surfaces),
        }


@lru_cache(maxsize=1)
def platform_terms() -> tuple[PlatformTerm, ...]:
    """Every field the platform accepts, in ``DATASET_SPECS`` order.

    Cached because the registry is a module constant: the answer cannot change
    within a process, and the bridge is rebuilt per index load.
    """
    fields: list[tuple[str, registry.FieldSpec]] = []
    for data_type, spec in registry.DATASET_SPECS.items():
        for field_spec in spec.all_fields:
            fields.append((data_type, field_spec))

    # Which canonicals claim each folded surface. An alias claimed twice is
    # ambiguous and gets dropped below.
    claimants: dict[str, set[str]] = {}
    for _data_type, field_spec in fields:
        for alias in (field_spec.canonical, *field_spec.aliases):
            claimants.setdefault(_flatten(alias), set()).add(field_spec.canonical)

    terms: list[PlatformTerm] = []
    for data_type, field_spec in fields:
        surfaces: dict[str, None] = {}
        for surface in (field_spec.label, field_spec.canonical, *field_spec.aliases):
            text = str(surface or "").strip()
            if not text:
                continue
            named_by_field = surface in (field_spec.label, field_spec.canonical)
            if not named_by_field and len(claimants.get(_flatten(text), ())) > 1:
                continue
            surfaces.setdefault(text, None)
        token_forms = tuple(form for form in (_tokens(text) for text in surfaces) if form)
        terms.append(
            PlatformTerm(
                data_type=data_type,
                canonical=field_spec.canonical,
                label=field_spec.label,
                unit=field_spec.unit,
                surfaces=tuple(surfaces),
                token_forms=token_forms,
            )
        )
    return tuple(terms)


class PlatformVocabulary:
    """The bridge itself: registry terms in, graph surfaces out (and back).

    Built once per :class:`~...entity_link.EntityLexicon`; the registry side is
    cached, so this constructor only pays for the token index.
    """

    def __init__(self, terms: Iterable[PlatformTerm] | None = None) -> None:
        self.terms: tuple[PlatformTerm, ...] = tuple(terms if terms is not None else platform_terms())
        #: token bucket -> term positions. See :func:`_token_key`.
        self._by_token: dict[str, list[int]] = {}
        #: folded label -> term positions, for the CJK containment direction.
        self._by_label: dict[str, list[int]] = {}
        for position, term in enumerate(self.terms):
            for form in term.token_forms:
                for token in form:
                    bucket = self._by_token.setdefault(_token_key(token), [])
                    if position not in bucket:
                        bucket.append(position)
            self._by_label.setdefault(_flatten(term.label), []).append(position)

    # ---- graph side --------------------------------------------------------
    def candidates(self, text: object) -> list[int]:
        """Term positions whose tokens share a bucket with ``text``'s tokens."""
        found: dict[int, None] = {}
        for token in _tokens(text):
            for position in self._by_token.get(_token_key(token), ()):
                found.setdefault(position, None)
        return list(found)

    def matches(self, text: object) -> list[PlatformTerm]:
        """The registry fields that name the same quantity as ``text``."""
        tokens = _tokens(text)
        found: dict[int, None] = {}
        for position in self.candidates(text):
            term = self.terms[position]
            if any(_aligned(tokens, form) for form in term.token_forms):
                found.setdefault(position, None)
        flattened = _flatten(text)
        if len(flattened) >= MIN_CJK_OVERLAP and _HAS_CJK.search(flattened):
            for position, term in enumerate(self.terms):
                label = _flatten(term.label)
                if len(label) < MIN_CJK_OVERLAP:
                    continue
                # Either direction: 气温 sits inside 平均气温, and a feature
                # named 松浦流量水位 would contain the label 松浦流量.
                if flattened in label or label in flattened:
                    found.setdefault(position, None)
        return [self.terms[position] for position in sorted(found)]

    def expand(self, text: object) -> list[str]:
        """Surfaces of every field ``text`` names, for widening a query.

        The order is the registry's, so the caller's output is deterministic.
        """
        surfaces: dict[str, None] = {}
        for term in self.matches(text):
            for surface in term.surfaces:
                surfaces.setdefault(surface, None)
        return list(surfaces)

    def triggered_by(self, text: object) -> list[tuple[str, tuple[str, ...]]]:
        """Chinese spans of ``text`` that name a field, and what to also try.

        The question-side counterpart of :meth:`bridges_to`. ``matches`` asks
        "does this *whole* string name a field", which is the right question for
        a model feature name (``气温``) and the wrong one for a sentence: the
        sentence is longer than the label, so the containment test never fires.

        So this scans the other way — for each field, does any of its Chinese
        surfaces, or its label with the leading qualifier dropped, occur inside
        the text. The Latin direction is deliberately absent: a question naming
        ``air_temp`` outright is already served by the lexicon's own exact
        layer, and matching Latin tokens inside a sentence is how ``air`` in
        "air quality" becomes a temperature reading.

        The returned span is what the text actually said (``气温``), never the
        label that was reached through it, so ``matched_via`` stays honest about
        where a seed came from.
        """
        flattened = _flatten(text)
        if not flattened or not _HAS_CJK.search(flattened):
            return []
        found: list[tuple[str, tuple[str, ...]]] = []
        for term in self.terms:
            for trigger in self._triggers(term):
                flattened_trigger = _flatten(trigger)
                if len(flattened_trigger) < MIN_CJK_OVERLAP:
                    continue
                if flattened_trigger in flattened:
                    found.append((trigger, term.surfaces))
                    break
        return found

    @staticmethod
    def _triggers(term: PlatformTerm) -> list[str]:
        """Chinese surfaces of ``term``, plus its label minus a qualifier."""
        triggers: list[str] = []
        for surface in term.surfaces:
            if _HAS_CJK.search(_fold(surface)):
                triggers.append(surface)
        for modifier in _CN_MODIFIERS:
            if term.label.startswith(modifier) and len(term.label) > len(modifier):
                triggers.append(term.label[len(modifier) :])
        return triggers

    def bridges_to(self, entity_names: Iterable[str]) -> dict[str, list[BridgeMatch]]:
        """Graph entity name -> the fields that name it, with their coverage.

        Term-aware rather than flattened to a surface list because the caller
        has to be able to *decline* a bridge per field: see
        :meth:`~...entity_link.EntityLexicon._add_platform_vocabulary`.

        Bulk rather than per-entity so the per-term fan-out cap is applied
        across the whole graph instead of being rediscovered for every name —
        and so a field that turns out to be a common word is capped once rather
        than once per entity.
        """
        counts = [0] * len(self.terms)
        bridged: dict[str, list[BridgeMatch]] = {}
        for name in entity_names:
            tokens = _tokens(name)
            if not tokens:
                continue
            hits = [
                position
                for position in self.candidates(name)
                if counts[position] < MAX_ENTITIES_PER_TERM
                and any(_aligned(tokens, form) for form in self.terms[position].token_forms)
            ]
            if not hits:
                continue
            for position in hits:
                counts[position] += 1
            bridged[name] = [
                BridgeMatch(
                    term=self.terms[position],
                    coverage=max(
                        _coverage(tokens, form) for form in self.terms[position].token_forms
                    ),
                )
                for position in hits
            ]
        return bridged


@lru_cache(maxsize=1)
def vocabulary() -> PlatformVocabulary:
    """The process-wide bridge. The registry is static, so this is safe."""
    return PlatformVocabulary()
