"""Question text -> graph seeds.

The old scorer (:func:`kg_service.score_relation`) fused two different jobs into
one hand-tuned integer: deciding *what the question is about* and deciding
*which relation answers it*. That is why ``关系 == "相关"`` needed a −3 special
case. This module does only the first job, and it is the sole thing that decides
which nodes a traversal may start from.

Layers, in descending confidence:

====  ==========================================================  ======
0     normalisation (NFKC, casefold, bracket/whitespace folding)   —
1     curated lexicons — exact, synonym, bilingual, related        .90–1.00
2     evidence-derived aliases (``evidence_aliases``)              .50
3     fuzzy — ``difflib`` for Latin, jaccard/containment for CJK   .40–.80
====  ==========================================================  ======

Script handling is the crux. The inherited graph's entity names are UPPERCASE
ENGLISH while its edge descriptions are Chinese, so the *lexical* layer never
needs to cross scripts — a Chinese question matches a Chinese description
directly. Cross-script work is needed here and only here, to turn a Chinese
question into English graph *seeds*, and that is what :data:`BILINGUAL` is for.

Two surfaces are searched, not one:

``norm``
    Everything folded to one string with whitespace removed. CJK surfaces are
    matched by containment against this.
``spaced``
    The same folding but with whitespace collapsed to single spaces. ASCII
    surfaces are matched here on word boundaries, which is what stops
    ``DO`` (dissolved oxygen) from matching inside the English word "does".
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from backend.app.services.graph_rag.config import GraphRagConfig
from backend.app.services.graph_rag.index import IndexBundle
from backend.app.services.graph_rag.lexicon import (
    BILINGUAL,
    RELATED_GROUPS,
    SYNONYM_GROUPS,
    is_junk_entity,
    is_latin_entity,
    latin_tokens,
)

#: Seed scores, one per linking layer. Named rather than inlined so the ranking
#: question ("why did this node become a seed?") has one answer per constant.
SEED_EXACT = 1.00
SEED_SYNONYM = 0.90
SEED_BILINGUAL = 0.85
SEED_CONTAINED = 0.80
SEED_RELATED = 0.55
SEED_EVIDENCE_ALIAS = 0.50
SEED_JACCARD = 0.40
#: A one-character *Chinese* entity name — 风, 磷, 氮 — is a real domain concept,
#: unlike a one-character Latin token, which is noise. It is matchable, but at a
#: lower weight than a full name, because a single character also occurs inside
#: unrelated words (风 in 风格). ``matched_via`` reports it as
#: ``contained_short`` so the weaker provenance is visible in the UI.
SEED_SHORT_CJK = 0.65

#: A Latin surface shorter than this is matched, but only as a weaker
#: ``contained`` hit: ``AN``/``AG``/``BA`` are real inherited entity names, and
#: at full weight they would outrank genuine matches on unrelated text.
SHORT_LATIN_CHARS = 3

#: ``difflib`` acceptance and the score band a hit lands in.
FUZZY_CUTOFF = 0.82
CJK_RATIO_CUTOFF = 0.70
JACCARD_CUTOFF = 0.60
MIN_JACCARD_CHARS = 3

#: Evidence-alias derivation: how Latin a description must be before its words
#: are treated as aliases for its endpoints, and how many words are taken.
EVIDENCE_LATIN_RATIO = 0.6
MAX_EVIDENCE_ALIASES = 6

#: The fuzzy layer only runs when the cheap layers came back thin — it is the
#: one layer whose cost scales with the question rather than the index.
FUZZY_TRIGGER_SEEDS = 3
MAX_FUZZY_CANDIDATES = 300

_BRACKETS = re.compile(r"[（）()\[\]【】《》]")
_SPLIT = re.compile(r"[（）()\[\]【】《》/、,，;；]")
_WHITESPACE = re.compile(r"\s+")
_LATIN_RUN = re.compile(r"[A-Za-z][A-Za-z0-9\-]*")
#: CJK Unified Ideographs and its Extension A. Spelled as codepoint ranges
#: rather than as a literal character class because the class's upper endpoint
#: (U+9FFF) is a glyph the repository's encoding guard reads as mojibake — and
#: it is right to: no source file should carry a lone U+9FFF for the sake of a
#: regex boundary.
_CJK_RANGES = ((0x3400, 0x4DBF), (0x4E00, 0x9FFF))
_HAS_CJK = re.compile("[" + "".join(f"{chr(lo)}-{chr(hi)}" for lo, hi in _CJK_RANGES) + "]")


def normalize(text: str, *, keep_spaces: bool = False) -> str:
    """Fold a surface form for comparison.

    NFKC handles the full-width/Half-width and compatibility cases (``（`` vs
    ``(``, ``ＴＳＳ`` vs ``TSS``) that a hand-written translation table would
    miss. Brackets and internal whitespace are then removed so that
    ``总悬浮物浓度（TSS）`` and ``总悬浮物浓度(TSS)`` collapse to one form.
    """
    folded = unicodedata.normalize("NFKC", text or "").casefold()
    folded = _BRACKETS.sub("", folded)
    return _WHITESPACE.sub(" " if keep_spaces else "", folded).strip()


def variants(name: str) -> list[str]:
    """Every surface form of an entity name worth matching.

    A parenthesised alias is the important case: ``总悬浮物浓度(TSS)`` has to be
    reachable as both ``总悬浮物浓度`` and ``TSS``, because a question will use one
    or the other, never both.
    """
    found: dict[str, None] = {}
    whole = normalize(name)
    if whole:
        found.setdefault(whole, None)
    for part in _SPLIT.split(name or ""):
        piece = normalize(part)
        if len(piece) >= 2:
            found.setdefault(piece, None)
    return list(found)


def _group_index(groups: list[set[str]]) -> dict[str, set[int]]:
    """``normalised member -> group ids``, so membership is one dict lookup."""
    index: dict[str, set[int]] = {}
    for group_id, group in enumerate(groups):
        for member in group:
            index.setdefault(normalize(member), set()).add(group_id)
    return index


_SYNONYM_INDEX = _group_index(SYNONYM_GROUPS)
_RELATED_INDEX = _group_index(RELATED_GROUPS)
_BILINGUAL_INDEX: dict[str, list[str]] = {}
for _english, _chinese_forms in BILINGUAL.items():
    _BILINGUAL_INDEX.setdefault(normalize(_english), []).extend(
        normalize(form) for form in _chinese_forms
    )


@dataclass(frozen=True)
class SeedLink:
    """One entity the question appears to be about."""

    node_key: str
    source_id: str
    name: str
    entity_type: str
    score: float
    matched_via: str
    surface: str

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "score": round(self.score, 4),
            "matched_via": self.matched_via,
            "surface": self.surface,
            "entity_type": self.entity_type,
            "source_id": self.source_id,
        }


class EntityLexicon:
    """A searchable surface index over every entity in the bundle.

    Built once per bundle; the bundle itself is memoised, so this cost is paid
    on index load rather than per question.
    """

    def __init__(self, bundle: IndexBundle, config: GraphRagConfig | None = None) -> None:
        self._bundle = bundle
        self._config = config or GraphRagConfig()
        #: normalised surface -> (node_key, score, matched_via)
        self._surfaces: dict[str, list[tuple[str, float, str]]] = {}
        #: bucket key -> surfaces. See :meth:`_bucket_key`.
        self._buckets: dict[str, list[str]] = {}
        #: node_key -> (display name, entity type)
        self._entities: dict[str, tuple[str, str]] = {}
        #: node_key -> normalised name, for the fuzzy layer
        self._names: dict[str, str] = {}
        #: a single character -> node keys containing it (CJK fuzzy candidates)
        self._by_char: dict[str, list[str]] = {}

    def build(self) -> None:
        for source in self._bundle.sources.values():
            for node_key, entity_type in source.node_types.items():
                name = source.display_name(node_key)
                if not name.strip() or is_junk_entity(name):
                    continue
                self._add_entity(node_key, source.source_id, name, entity_type)
            if self._config.evidence_aliases:
                self._add_evidence_aliases(source)

    # ---- construction ------------------------------------------------------
    def _add_entity(self, node_key: str, source_id: str, name: str, entity_type: str) -> None:
        self._entities[node_key] = (name, entity_type)
        whole = normalize(name)
        self._names[node_key] = whole
        for char in set(whole):
            if _HAS_CJK.match(char):
                self._by_char.setdefault(char, []).append(node_key)

        for surface in variants(name):
            via = "exact" if surface == whole else "contained"
            self._record(surface, node_key, SEED_EXACT if via == "exact" else SEED_CONTAINED, via)

        surface_set = set(variants(name))
        for group_id in self._groups_for(surface_set, _SYNONYM_INDEX):
            for member in SYNONYM_GROUPS[group_id]:
                self._record(normalize(member), node_key, SEED_SYNONYM, "synonym")
        for group_id in self._groups_for(surface_set, _RELATED_INDEX):
            for member in RELATED_GROUPS[group_id]:
                self._record(normalize(member), node_key, SEED_RELATED, "related")
        for surface in surface_set:
            for chinese_form in _BILINGUAL_INDEX.get(surface, ()):
                self._record(chinese_form, node_key, SEED_BILINGUAL, "bilingual")

    @staticmethod
    def _groups_for(surfaces: set[str], index: dict[str, set[int]]) -> set[int]:
        groups: set[int] = set()
        for surface in surfaces:
            groups |= index.get(surface, set())
        return groups

    def _add_evidence_aliases(self, source) -> None:
        """Register Latin words from an edge's evidence as weak aliases.

        Corpus-adaptive: the baseline graph's evidence is English while its
        entities are Chinese, so ``Wind-induced disturbances to sediment
        resuspension`` has to reach ``风``/``沉积物再悬浮`` somehow. Weak weight
        guarantees it never outranks a real name hit.
        """
        for relation in source.relations:
            evidence = relation.evidence
            if not evidence:
                continue
            letters = sum(1 for char in evidence if char.isascii() and char.isalpha())
            if letters < EVIDENCE_LATIN_RATIO * max(len(evidence), 1):
                continue
            tokens = latin_tokens(evidence)[:MAX_EVIDENCE_ALIASES]
            for endpoint in (relation.source, relation.target):
                if endpoint not in self._entities:
                    continue
                for token in tokens:
                    if len(token) >= 4:
                        self._record(token, endpoint, SEED_EVIDENCE_ALIAS, "evidence_alias")

    def _record(self, surface: str, node_key: str, score: float, via: str) -> None:
        if len(surface) < 2:
            if not _HAS_CJK.search(surface):
                # A one-letter Latin token ("a", "b", "q") is not a name.
                return
            # A one-character Chinese name is a real entity, but a weak surface.
            score = min(score, SEED_SHORT_CJK)
            via = "contained_short"
        bucket = self._surfaces.get(surface)
        if bucket is None:
            self._surfaces[surface] = [(node_key, score, via)]
            self._buckets.setdefault(self._bucket_key(surface), []).append(surface)
            return
        for position, existing in enumerate(bucket):
            if existing[0] == node_key:
                # Same surface, same entity, different layers. Layers are
                # applied weakest-last only by accident of this function's
                # order, and dropping the later entry would mean a *related*
                # link (0.55) silently vetoes a *bilingual* one (0.85) for the
                # same pair — 浊度→TURBIDITY is a translation, and it was
                # being recorded as a mere association because RELATED_GROUPS
                # happens to be walked first. Keep the strongest provenance
                # instead; that is what the layers are ordered by.
                if score > existing[1]:
                    bucket[position] = (node_key, score, via)
                return
        bucket.append((node_key, score, via))

    # ---- lookup ------------------------------------------------------------
    @staticmethod
    def _bucket_key(surface: str) -> str:
        """The shortest prefix that is enough to find ``surface`` again.

        A surface is only ever looked up via the n-grams of the question that
        contain its own opening characters, so three characters is sufficient:
        if the surface occurs in the question, so does its first three
        characters. Surfaces shorter than that are their own key.

        This exists because scanning all 12k surfaces per question cost 180 ms.
        Bucketing makes it proportional to the question's length instead.
        """
        return surface if len(surface) < 3 else surface[:3]

    @staticmethod
    def _question_keys(norm_question: str) -> set[str]:
        keys: set[str] = set()
        length = len(norm_question)
        for size in (1, 2, 3):
            for start in range(length - size + 1):
                keys.add(norm_question[start : start + size])
        return keys

    def link(self, question: str, *, max_seeds: int, min_score: float) -> list[SeedLink]:
        hits: dict[str, tuple[float, str, str]] = {}

        norm_question = normalize(question)
        spaced_question = normalize(question, keep_spaces=True)
        if not norm_question:
            return []

        candidates: dict[str, None] = {}
        for key in self._question_keys(norm_question):
            for surface in self._buckets.get(key, ()):
                candidates.setdefault(surface, None)

        for surface in candidates:
            if not self._surface_occurs(surface, norm_question, spaced_question):
                continue
            for node_key, score, via in self._surfaces[surface]:
                self._keep_best(hits, node_key, score, via, surface)

        if len(hits) < FUZZY_TRIGGER_SEEDS:
            self._fuzzy(question, spaced_question, hits)

        seeds = [
            SeedLink(
                node_key=node_key,
                source_id=node_key.partition("::")[0],
                name=self._entities[node_key][0],
                entity_type=self._entities[node_key][1],
                score=score,
                matched_via=via,
                surface=surface,
            )
            for node_key, (score, via, surface) in hits.items()
            if score >= min_score
        ]
        return self._cap_per_source(seeds, max_seeds)

    def _cap_per_source(self, seeds: list[SeedLink], max_seeds: int) -> list[SeedLink]:
        """Apply ``max_seeds`` within each source rather than across all of them.

        A single global cap lets one graph's hub nodes starve the other: the
        inherited graph's ``TURBIDITY`` has degree 593, so on a degree tiebreak
        it and its neighbours filled every slot and the platform graph — the
        user's own literature, and the whole reason this feature exists —
        contributed two seeds out of twelve.
        """
        by_source: dict[str, list[SeedLink]] = {}
        for seed in seeds:
            by_source.setdefault(seed.source_id, []).append(seed)

        out: list[SeedLink] = []
        for group in by_source.values():
            # Ties break by node degree, then name, so the seed list is stable
            # across runs and the UI does not reshuffle between identical
            # queries.
            group.sort(key=lambda seed: (-seed.score, -self._degree(seed), seed.name))
            out.extend(group[:max_seeds])
        return out

    def _degree(self, seed: SeedLink) -> int:
        source = self._bundle.sources.get(seed.source_id)
        return source.degree(seed.node_key) if source is not None else 0

    def _keep_best(
        self,
        hits: dict[str, tuple[float, str, str]],
        node_key: str,
        score: float,
        via: str,
        surface: str,
    ) -> None:
        current = hits.get(node_key)
        if current is None or score > current[0]:
            hits[node_key] = (score, via, surface)

    @staticmethod
    def _surface_occurs(surface: str, norm_question: str, spaced_question: str) -> bool:
        if _HAS_CJK.search(surface):
            # CJK is written without spaces, so containment on the
            # whitespace-folded form is the match — there is no token to find.
            return surface in norm_question
        return re.search(
            rf"(?<![a-z0-9]){re.escape(surface)}(?![a-z0-9])", spaced_question
        ) is not None

    def _fuzzy(
        self,
        question: str,
        spaced_question: str,
        hits: dict[str, tuple[float, str, str]],
    ) -> None:
        """Last resort for phrasings the lexicons do not enumerate.

        ``difflib`` only helps within a script, so it runs for Latin tokens
        against Latin entity names and never across the Chinese/English divide —
        that gap is what :data:`BILINGUAL` exists to cover.
        """
        import difflib

        tokens = [token for token in latin_tokens(question) if len(token) >= 4]
        if tokens:
            latin_entities = {
                node_key: name
                for node_key, (name, _type) in self._entities.items()
                if is_latin_entity(name)
            }
            names = list(latin_entities.values())
            for token in tokens:
                for match in difflib.get_close_matches(token, names, n=3, cutoff=FUZZY_CUTOFF):
                    ratio = difflib.SequenceMatcher(None, token, match).ratio()
                    score = 0.60 + 0.20 * (ratio - FUZZY_CUTOFF) / (1 - FUZZY_CUTOFF)
                    for node_key, name in latin_entities.items():
                        if name == match:
                            self._keep_best(hits, node_key, score, "fuzzy", token)

        cjk_candidates = self._cjk_candidates(question)
        if not cjk_candidates:
            return
        question_chars = {char for char in question if _HAS_CJK.match(char)}
        for node_key in cjk_candidates:
            name = self._names.get(node_key, "")
            if len(name) < MIN_JACCARD_CHARS:
                continue
            name_chars = set(name)
            union = question_chars | name_chars
            jaccard = len(question_chars & name_chars) / len(union) if union else 0.0
            if jaccard >= JACCARD_CUTOFF:
                self._keep_best(hits, node_key, SEED_JACCARD, "jaccard", name)
                continue
            ratio = difflib.SequenceMatcher(None, name, normalize(question)).ratio()
            if ratio >= CJK_RATIO_CUTOFF:
                score = 0.60 + 0.20 * (ratio - CJK_RATIO_CUTOFF) / (1 - CJK_RATIO_CUTOFF)
                self._keep_best(hits, node_key, score, "fuzzy", name)

    def _cjk_candidates(self, question: str) -> list[str]:
        """Entities sharing at least one character with the question.

        Bucketing by character keeps the fuzzy layer proportional to the
        question rather than to the 10k-entity index.
        """
        found: dict[str, None] = {}
        for char in question:
            if not _HAS_CJK.match(char):
                continue
            for node_key in self._by_char.get(char, ()):
                found.setdefault(node_key, None)
                if len(found) >= MAX_FUZZY_CANDIDATES:
                    return list(found)
        return list(found)


class EntityLinker:
    """Public entry point: the bundle's lexicon plus the config's thresholds."""

    def __init__(self, bundle: IndexBundle, config: GraphRagConfig | None = None) -> None:
        self.config = config or GraphRagConfig()
        self.lexicon = EntityLexicon(bundle, self.config)
        self.lexicon.build()

    def link(self, question: str) -> list[SeedLink]:
        return self.lexicon.link(
            question,
            max_seeds=self.config.max_seeds,
            min_score=self.config.seed_min_score,
        )

    def seeds_by_source(self, seeds: list[SeedLink]) -> dict[str, list[SeedLink]]:
        grouped: dict[str, list[SeedLink]] = {}
        for seed in seeds:
            grouped.setdefault(seed.source_id, []).append(seed)
        return grouped
