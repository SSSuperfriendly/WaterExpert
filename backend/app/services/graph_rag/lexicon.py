"""Curated term lists for entity linking.

``DOMAIN_TERMS`` / ``ALIASES`` / ``extract_keywords`` are moved here verbatim
from ``kg_service`` (which re-exports them, so existing imports keep working).
They back the *legacy* scorer, which ``tests/knowledge_graph/test_kg_service.py``
still exercises and which the eval harness uses as its baseline. Do not edit
them.

Everything below them is new and belongs to the GraphRAG linker. The important
one is :data:`RELATED_GROUPS`: the legacy ``ALIASES`` table treats ``浊度`` /
``TSS`` / ``SSC`` as synonyms of ``透明度``, which is a semantic error — those
quantities are *inversely* related to clarity, not interchangeable. Propagating
that into the new scorer would actively hurt retrieval precision, so the linker
uses two separate weight tiers instead:

* :data:`SYNONYM_GROUPS` (0.90) — same quantity, different surface form.
* :data:`RELATED_GROUPS` (0.55) — genuinely associated, but a distinct concept.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Moved verbatim from kg_service — the legacy scorer's term lists.
# ---------------------------------------------------------------------------
DOMAIN_TERMS = [
    "透明度", "清澈度", "水体透明度", "浊度", "悬浮物", "悬浮颗粒物",
    "悬浮物浓度", "总悬浮物", "总悬浮物浓度", "TSS", "SSC",
    "监测", "测量", "测定", "检测", "观测", "采样", "方法", "仪器",
    "传感器", "浊度计", "光学后向散射", "光学后向散射传感器",
    "OBS", "OBS-3A", "膜过滤法", "实验室分析", "透明度盘", "塞氏盘",
    "风速", "水深", "水动力", "波浪", "总氮", "总磷", "有机质",
]

ALIASES = {
    "透明度": [
        "透明度", "水体透明度", "清澈度", "浊度", "悬浮物",
        "悬浮物浓度", "总悬浮物浓度", "TSS", "SSC",
        "光学后向散射", "OBS", "OBS-3A", "浊度计",
        "透明度盘", "塞氏盘",
    ],
    "清澈度": [
        "清澈度", "透明度", "水体透明度", "浊度", "悬浮物",
        "悬浮物浓度", "TSS", "SSC",
    ],
    "浊度": [
        "浊度", "浊度计", "光学后向散射", "OBS", "OBS-3A",
        "悬浮物", "悬浮物浓度", "TSS", "SSC",
    ],
    "悬浮物": [
        "悬浮物", "悬浮颗粒物", "悬浮物浓度", "总悬浮物",
        "总悬浮物浓度", "TSS", "SSC", "膜过滤法",
    ],
    "监测": [
        "监测", "测量", "测定", "检测", "观测", "采样",
        "方法", "仪器", "传感器", "浊度计",
        "光学后向散射传感器", "OBS", "OBS-3A", "膜过滤法",
        "实验室分析", "透明度盘", "塞氏盘",
    ],
    "方法": [
        "方法", "监测", "测量", "测定", "检测", "采样",
        "仪器", "传感器", "浊度计", "OBS", "OBS-3A",
        "膜过滤法", "实验室分析", "透明度盘", "塞氏盘",
    ],
}


def extract_keywords(question: str) -> list:
    keywords = set()
    question = question.strip()

    for term in DOMAIN_TERMS:
        if term.lower() in question.lower():
            keywords.add(term)

    for key, values in ALIASES.items():
        if key in question:
            keywords.update(values)

    english_terms = re.findall(r"[A-Za-z0-9\-]+", question)
    for term in english_terms:
        if len(term) >= 2:
            keywords.add(term)

    return list(keywords)


# ---------------------------------------------------------------------------
# GraphRAG linker lexicons
# ---------------------------------------------------------------------------
#: Same quantity, different surface form. Linked at weight 0.90.
SYNONYM_GROUPS: list[set[str]] = [
    {"透明度", "水体透明度", "清澈度", "塞氏盘深度", "Secchi深度", "SECCHI DEPTH", "TRANSPARENCY"},
    {"悬浮物", "悬浮颗粒物", "悬浮物浓度", "总悬浮物", "总悬浮物浓度", "TSS", "SSC", "SS", "SPM"},
    {"监测", "测量", "测定", "检测", "观测", "采样"},
    {"遥感反演", "反演", "卫星影像", "遥感", "无人机监测", "REMOTE SENSING", "SATELLITE IMAGERY"},
    {"清淤", "底泥疏浚", "疏浚", "DREDGING"},
    {"生态修复", "水生植物修复", "植被恢复"},
    {"沉积物再悬浮", "底泥再悬浮", "泥沙再悬浮", "SEDIMENT RESUSPENSION"},
    {"总磷", "TP", "TOTAL PHOSPHORUS", "TOTAL PHOSPHORUS (TP)"},
    {"总氮", "TN", "TOTAL NITROGEN", "TOTAL NITROGEN (TN)"},
    {"叶绿素a", "叶绿素", "CHL A", "CHLOROPHYLL"},
    {"降雨", "降水", "RAINFALL", "PRECIPITATION"},
    {"径流", "地表径流", "RUNOFF", "SURFACE RUNOFF"},
    {"流量", "水流", "FLOW", "DISCHARGE", "STREAMFLOW", "STREAM FLOW"},
    {"泥沙", "沉积物", "底泥", "SEDIMENT", "SUSPENDED SEDIMENT", "FINE SEDIMENT"},
    {"土壤侵蚀", "侵蚀", "SOIL EROSION", "EROSION"},
    {"流域", "集水区", "WATERSHED", "CATCHMENT"},
    {"风速", "WIND SPEED"},
    {"水深", "WATER DEPTH", "WATER LEVEL", "水位"},
    {"水温", "WATER TEMPERATURE"},
    {"溶解氧", "DO", "DISSOLVED OXYGEN", "DISSOLVED OXYGEN (DO)"},
    {"洪水", "FLOOD"},
]

#: Genuinely associated, but a *distinct* concept — never interchangeable.
#: Linked at weight 0.55. This is the corrected form of the legacy table's
#: ``浊度`` ≡ ``透明度`` equivalence.
RELATED_GROUPS: list[set[str]] = [
    {"透明度", "浊度", "水色", "TURBIDITY", "光衰减", "LIGHT ATTENUATION"},
    {"悬浮物", "沉积物再悬浮", "SEDIMENT RESUSPENSION", "侵蚀", "EROSION"},
    {"浊度计", "光学后向散射", "OBS", "OBS-3A", "浊度", "悬浮物", "TURBIDITY"},
    {"含沙量", "输沙量", "泥沙负荷", "SEDIMENT LOAD", "SEDIMENT CONCENTRATION", "SUSPENDED SEDIMENT CONCENTRATION"},
    {"富营养化", "藻华", "蓝藻", "EUTROPHICATION", "ALGAL BLOOM", "CYANOBACTERIA"},
    {"营养盐", "氮", "磷", "NUTRIENTS", "NITROGEN", "PHOSPHORUS"},
    {"土地利用", "农业", "植被", "LAND USE", "AGRICULTURE", "VEGETATION", "AGRICULTURAL LAND USE"},
    {"暴雨", "降雨强度", "STORM EVENT", "STORM EVENTS", "RAINFALL INTENSITY", "洪峰流量", "PEAK FLOW", "PEAK DISCHARGE"},
]

#: English entity name -> Chinese surface forms. The inherited graph's entity
#: names are UPPERCASE ENGLISH while its edge ``description`` values are
#: Chinese, so a Chinese question reaches the *description* lexically for free
#: (see ``local_search``). This table exists for the part lexical matching
#: cannot bridge: turning a Chinese question into graph *seeds* for traversal.
#:
#: Hand-curated, ~120 entries, covering the highest-degree entities of
#: ``create_final_relationships.parquet`` (measured 2026-09-13). Extending
#: coverage is a one-line edit — deliberately data-driven rather than clever.
BILINGUAL: dict[str, list[str]] = {
    "TURBIDITY": ["浊度"],
    "SSC": ["悬浮物浓度", "悬浮泥沙浓度", "含沙量"],
    "TSS": ["总悬浮物", "悬浮物浓度"],
    "SUSPENDED SEDIMENT": ["悬浮泥沙", "悬浮沉积物", "悬浮物"],
    "FLOW": ["流量", "水流"],
    "WATER QUALITY": ["水质"],
    "RUNOFF": ["径流"],
    "DISCHARGE": ["流量", "排放"],
    "SEDIMENT TRANSPORT": ["泥沙输移", "输沙"],
    "PRECIPITATION": ["降水", "降雨"],
    "SOIL EROSION": ["土壤侵蚀"],
    "RAINFALL": ["降雨"],
    "SUSPENDED SEDIMENT CONCENTRATION (SSC)": ["悬浮泥沙浓度"],
    "SS": ["悬浮物"],
    "STREAMFLOW": ["河流流量", "径流"],
    "TOTAL PHOSPHORUS (TP)": ["总磷"],
    "STORM EVENT": ["暴雨事件", "风暴事件"],
    "SUSPENDED SEDIMENT (SS)": ["悬浮泥沙"],
    "PH": ["pH", "酸碱度"],
    "LAND USE": ["土地利用"],
    "SEDIMENT LOAD": ["泥沙负荷", "输沙量"],
    "STORM EVENTS": ["暴雨事件"],
    "SUSPENDED SEDIMENT YIELD": ["泥沙产沙量"],
    "CLIMATE CHANGE": ["气候变化"],
    "RAINFALL INTENSITY": ["降雨强度"],
    "TP": ["总磷"],
    "WATERSHED": ["流域"],
    "SUSPENDED SOLIDS": ["悬浮固体"],
    "SPM": ["悬浮颗粒物"],
    "TEMPERATURE": ["温度", "水温"],
    "CATCHMENT": ["流域", "集水区"],
    "SALINITY": ["盐度"],
    "SEDIMENT RESUSPENSION": ["沉积物再悬浮", "底泥再悬浮"],
    "SURFACE RUNOFF": ["地表径流"],
    "SEDIMENT YIELD": ["产沙量"],
    "SUSPENDED SEDIMENT CONCENTRATION": ["悬浮泥沙浓度", "含沙量"],
    "PHOSPHORUS": ["磷"],
    "HYDROGRAPH": ["流量过程线"],
    "SEDIMENT": ["沉积物", "底泥", "泥沙"],
    "TOTAL NITROGEN (TN)": ["总氮"],
    "WATER QUALITY PARAMETERS": ["水质参数"],
    "TOTAL SUSPENDED SOLIDS (TSS)": ["总悬浮固体"],
    "SEDIMENT DYNAMICS": ["泥沙动力学"],
    "NITROGEN (N)": ["氮"],
    "TN": ["总氮"],
    "FLOOD": ["洪水"],
    "GROUNDWATER": ["地下水"],
    "NITRATE": ["硝酸盐"],
    "FLOW VELOCITY": ["流速"],
    "BOD": ["生化需氧量"],
    "DO": ["溶解氧"],
    "AGRICULTURAL LAND USE": ["农业土地利用"],
    "SEDIMENT CONCENTRATION": ["含沙量", "泥沙浓度"],
    "CONDUCTIVITY": ["电导率"],
    "BASE FLOW": ["基流"],
    "PEAK FLOW": ["洪峰流量"],
    "WATER QUALITY RISK": ["水质风险"],
    "STORM FLOW": ["暴雨径流"],
    "SEASONAL VARIATION": ["季节性变化"],
    "PEAK DISCHARGE": ["洪峰流量"],
    "COD": ["化学需氧量"],
    "AGRICULTURE": ["农业"],
    "PARTICULATE MATTER": ["颗粒物"],
    "WATER LEVEL": ["水位"],
    "WIND SPEED": ["风速"],
    "NITROGEN": ["氮"],
    "TOTAL NITROGEN": ["总氮"],
    "CHL A": ["叶绿素a"],
    "HEAVY METALS": ["重金属"],
    "SLOPE": ["坡度"],
    "EROSION": ["侵蚀"],
    "WATER TEMPERATURE": ["水温"],
    "TOTAL SUSPENDED SOLIDS": ["总悬浮固体"],
    "WIND DIRECTION": ["风向"],
    "DISSOLVED OXYGEN (DO)": ["溶解氧"],
    "FINE SEDIMENT": ["细颗粒泥沙"],
    "PARTICLE SIZE": ["粒径"],
    "VEGETATION": ["植被"],
    "WIND": ["风"],
    "CHLOROPHYLL": ["叶绿素"],
    "WATER DEPTH": ["水深"],
    "TIDE": ["潮汐"],
    "LAKE TAIHU": ["太湖"],
    "MEILIANG BAY": ["梅梁湾"],
    "AMMONIA": ["氨氮"],
    "EC": ["电导率"],
    "ALKALINITY": ["碱度"],
    "SHEAR STRESS": ["剪应力"],
    "WAVE SHEAR STRESS": ["波浪剪应力"],
    "HYSTERESIS": ["滞后现象"],
    "SUSPENDED PARTICULATE MATTER": ["悬浮颗粒物"],
    "SECCHI DEPTH": ["透明度", "塞氏盘深度"],
    "TRANSPARENCY": ["透明度", "清澈度"],
    "LIGHT ATTENUATION": ["光衰减"],
    "NUTRIENTS": ["营养盐"],
    "EUTROPHICATION": ["富营养化"],
    "ALGAL BLOOM": ["藻华", "水华"],
    "CYANOBACTERIA": ["蓝藻"],
    "DREDGING": ["清淤", "疏浚"],
    "AERATION": ["曝气"],
    "REMOTE SENSING": ["遥感"],
    "SATELLITE IMAGERY": ["卫星影像"],
    "MONITORING": ["监测"],
    "TOTAL PHOSPHORUS": ["总磷"],
    "PARTICULATE PHOSPHORUS": ["颗粒态磷"],
    "DISSOLVED OXYGEN": ["溶解氧"],
    "PARTICLE SIZE DISTRIBUTION": ["粒径分布"],
    "SUSPENDED SEDIMENT LOAD": ["悬浮泥沙负荷"],
    "SUSPENDED SEDIMENT TRANSPORT": ["悬浮泥沙输移"],
    "GULLY EROSION": ["沟蚀"],
    "CONSERVATION PRACTICES": ["水土保持措施"],
    "WATER QUALITY INDEX (WQI)": ["水质指数"],
    "SPECIFIC SEDIMENT YIELD": ["单位产沙量"],
    "RUNOFF COEFFICIENT": ["径流系数"],
    "C-Q RELATIONSHIP": ["流量-含沙量关系"],
}

#: Question intent -> entity type, used for the type-hit ranking term. Intent is
#: read off the *linked seed's* type rather than a word list matching against
#: relation text, so it generalises to phrasings nobody enumerated.
INTENT_TYPE_CUES: list[tuple[tuple[str, ...], str | None]] = [
    (("监测", "测量", "测定", "检测", "方法", "仪器", "传感器", "反演", "遥感"), "监测方法"),
    (("治理", "修复", "清淤", "疏浚", "曝气", "措施", "改善", "控制"), "治理措施"),
    (("原因", "驱动", "为什么", "导致", "成因", "机理"), None),
    (("多少", "浓度", "数值", "范围"), None),
]

#: Latin tokens too generic to be useful evidence aliases, and too generic to
#: seed a traversal from.
STOPWORDS: frozenset[str] = frozenset({
    "the", "and", "for", "with", "from", "that", "this", "were", "was", "are",
    "has", "have", "been", "which", "than", "then", "also", "such",
    "other", "into", "during", "between", "within", "using", "used", "use",
    "can", "may", "not", "but", "its", "their", "these", "those", "more",
    "most", "some", "any", "all", "both", "each", "only", "over", "under",
    "higher", "lower", "increase", "increased", "decrease", "decreased",
    "however", "therefore", "thus", "due", "study", "studies", "result",
    "results", "data", "model", "models", "site", "sites", "river", "figure",
    "table", "total", "mean", "average", "measured", "observed", "found",
})

#: GraphRAG's extractor emitted bibliographic and structural nodes alongside
#: real domain entities — a measured sample of the inherited parquet's
#: highest-degree nodes includes ``REFERENCE`` (38), ``PARAMETER`` (38),
#: ``MODEL`` (49), ``DATA`` (32), ``YEAR`` (22), ``STUDY`` (22). They are not
#: domain concepts, so they must never become a query seed or anchor a
#: community summary. They stay in the graph: edges through them are still
#: citable, and dropping nodes would silently change the index.
#:
#: Kept deliberately narrow. Water-quality acronyms that *look* like junk
#: (``TSS``/``SSC``/``DO``/``PH``/``TP``/``CSS``…) are real entities here and
#: excluding them would break exactly the questions this feature exists for.
JUNK_ENTITIES: frozenset[str] = frozenset({
    "REFERENCE", "REFERENCES", "DATA", "DATASET", "DATASETS", "MODEL", "MODELS",
    "YEAR", "YEARS", "STUDY", "STUDIES", "DATE", "PARAMETER", "PARAMETERS",
    "EXPLANATORY VARIABLES", "PREDICTORS", "CALIBRATION PERIOD", "STATION A",
    "LABORATORY", "RIVERS", "EVENT", "C", "Q", "WS 2",
    "POL. J. ENVIRON. STUD.", "HOWLEAKY2008", "CATCHMODS", "Z4LA",
})

#: Relation labels the platform extractor is prompted to emit (see
#: ``build_extraction_prompt``). Used to render citations and, in the router, to
#: recognise an explicitly relational question.
RELATION_LABELS: frozenset[str] = frozenset({
    "影响", "导致", "相关", "监测", "反演", "改善", "降低", "增加",
})

#: Detects English entity names — the inherited graph's ``source``/``target``.
_LATIN_ENTITY = re.compile(r"^[A-Za-z][A-Za-z0-9\-\s\.\(\)²/]*$")
_LATIN_TOKEN = re.compile(r"[A-Za-z][A-Za-z\-]{3,}")


def is_latin_entity(name: str) -> bool:
    """True when ``name`` looks like an inherited-graph English entity."""
    return bool(_LATIN_ENTITY.match(name.strip()))


def latin_tokens(text: str) -> list[str]:
    """Content-bearing Latin tokens of ``text``, lowercased and deduped."""
    seen: dict[str, None] = {}
    for token in _LATIN_TOKEN.findall(text):
        lowered = token.lower()
        if lowered not in STOPWORDS:
            seen.setdefault(lowered, None)
    return list(seen)


def is_junk_entity(name: str) -> bool:
    return name.strip().upper() in JUNK_ENTITIES
