"""Knowledge-graph pipeline orchestration.

Ported from the ``qcd`` Streamlit project, split by category per the merge
plan:

* ``Pages/3_BuildKG.py`` extraction logic (``split_text`` / ``build_prompt`` /
  ``parse_json`` / ``extract_triples`` / ``save_kg``) lives here as module-level
  functions so both the API service and the background ``kg_job_runner``
  subprocess can reuse them.
* ``Pages/4_QA.py`` retrieval logic (domain terms / aliases / scoring /
  context building / ``answer_question``) lives here too.

Runtime artifacts are written under ``var/knowledge_graph/`` (gitignored). When
no runtime graph has been built yet, ``graph()`` / ``qa()`` fall back to the
committed baseline under ``outputs/knowledge_graph/`` so the feature is usable
immediately after checkout.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
from fastapi import UploadFile

from backend.app.config import Settings
from backend.app.services.kg_llm import call_llm, is_llm_configured
from backend.app.services.kg_pdf_processor import (
    ExtractionResult,
    extract_structured_text,
    write_log,
    write_outputs,
)

RUNNING_STATUS = "running"
COMPLETED_STATUS = "completed"
FAILED_STATUS = "failed"
ORPHANED_STATUS = "orphaned"
TERMINAL_STATUSES = {COMPLETED_STATUS, FAILED_STATUS, ORPHANED_STATUS}

DOWNLOADABLE_FILES = {"entities.csv", "relations.csv", "graph.json"}

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


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# KG construction (ported from Pages/3_BuildKG.py)
# ---------------------------------------------------------------------------
def split_text(text: str, max_chars: int = 1200) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]

    chunks = []
    current = ""

    for paragraph in paragraphs:
        if len(current) + len(paragraph) > max_chars:
            if current:
                chunks.append(current)
            current = paragraph
        else:
            current = current + "\n" + paragraph

    if current:
        chunks.append(current)

    return chunks


def build_extraction_prompt(text: str) -> str:
    return f"""
请从下面的水体清澈度相关文本中抽取知识图谱三元组。

抽取对象包括但不限于：
1. 水体对象：湖泊、水库、河流、太湖、巢湖等；
2. 清澈度指标：透明度、Secchi深度、浊度、水色等；
3. 水质因子：悬浮物、叶绿素a、CDOM、总磷、总氮等；
4. 环境因子：风速、降雨、水深、水温、光照、流速等；
5. 监测方法：现场监测、遥感反演、无人机监测、卫星影像等；
6. 治理措施：控源截污、生态修复、清淤、蓝藻治理等。

关系类型尽量使用：
影响、导致、相关、监测、反演、改善、降低、增加。

要求：
1. 只输出 JSON，不要输出解释文字；
2. 不要编造文本中没有的信息；
3. evidence 必须来自原文或尽量贴近原文。

JSON 格式如下：

{{
  "triples": [
    {{
      "source": "悬浮颗粒物",
      "source_type": "水质因子",
      "relation": "影响",
      "target": "透明度",
      "target_type": "清澈度指标",
      "evidence": "悬浮颗粒物浓度升高会降低水体透明度"
    }}
  ]
}}

待抽取文本：
{text}
"""


def parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"\{[\s\S]*\}", text)

    if match:
        try:
            return json.loads(match.group())
        except Exception:
            return {"triples": []}

    return {"triples": []}


def extract_triples(chunk: str) -> list[dict]:
    prompt = build_extraction_prompt(chunk)
    result = call_llm(prompt)
    data = parse_json(result)

    triples = data.get("triples", [])

    if not isinstance(triples, list):
        return []

    clean_triples = []

    for item in triples:
        source = str(item.get("source", "")).strip()
        target = str(item.get("target", "")).strip()
        relation = str(item.get("relation", "")).strip()

        if not source or not target or not relation:
            continue

        clean_triples.append({
            "source": source,
            "source_type": str(item.get("source_type", "未知类型")).strip(),
            "relation": relation,
            "target": target,
            "target_type": str(item.get("target_type", "未知类型")).strip(),
            "evidence": str(item.get("evidence", "")).strip(),
        })

    return clean_triples


def save_kg(triples: list[dict], kg_dir: str | Path) -> int:
    if not triples:
        return 0

    kg_dir = Path(kg_dir)
    kg_dir.mkdir(parents=True, exist_ok=True)

    relations_df = pd.DataFrame(triples)

    relations_df = relations_df.drop_duplicates(
        subset=["source", "relation", "target"]
    )

    entity_map = {}

    for _, row in relations_df.iterrows():
        entity_map[row["source"]] = row["source_type"]
        entity_map[row["target"]] = row["target_type"]

    entities = []

    for i, (name, entity_type) in enumerate(entity_map.items(), start=1):
        entities.append({
            "entity_id": f"E{i:04d}",
            "entity_name": name,
            "entity_type": entity_type,
        })

    entities_df = pd.DataFrame(entities)

    entities_path = kg_dir / "entities.csv"
    relations_path = kg_dir / "relations.csv"
    graph_path = kg_dir / "graph.json"

    entities_df.to_csv(entities_path, index=False, encoding="utf-8-sig")
    relations_df.to_csv(relations_path, index=False, encoding="utf-8-sig")

    graph_data = {
        "nodes": [
            {
                "id": row["entity_name"],
                "label": row["entity_name"],
                "type": row["entity_type"],
            }
            for _, row in entities_df.iterrows()
        ],
        "edges": [
            {
                "source": row["source"],
                "target": row["target"],
                "relation": row["relation"],
                "evidence": row.get("evidence", ""),
            }
            for _, row in relations_df.iterrows()
        ],
    }

    graph_path.write_text(
        json.dumps(graph_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return len(relations_df)


# ---------------------------------------------------------------------------
# KG QA (ported from Pages/4_QA.py)
# ---------------------------------------------------------------------------
def load_relations(relations_path: str | Path | None) -> list[dict]:
    if not relations_path:
        return []

    path = Path(relations_path)

    if not path.exists():
        return []

    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
    except UnicodeDecodeError:
        df = pd.read_csv(path, encoding="utf-8")

    for col in ["source", "target", "relation", "evidence"]:
        if col not in df.columns:
            df[col] = ""

    df = df.fillna("")
    return df.to_dict("records")


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


def score_relation(row: dict, question: str, keywords: list) -> int:
    source = str(row.get("source", ""))
    target = str(row.get("target", ""))
    relation = str(row.get("relation", ""))
    evidence = str(row.get("evidence", ""))

    row_text = f"{source} {target} {relation} {evidence}"

    score = 0

    if source and source in question:
        score += 10
    if target and target in question:
        score += 10
    if relation and relation in question:
        score += 8

    for kw in keywords:
        if not kw:
            continue

        if kw in source or kw in target:
            score += 6
        elif kw in relation:
            score += 5
        elif kw in evidence:
            score += 2

    method_intent_words = ["方法", "监测", "测量", "测定", "检测", "仪器", "传感器"]
    has_method_intent = any(word in question for word in method_intent_words)

    method_evidence_words = [
        "监测", "测量", "测定", "检测", "采样", "传感器",
        "浊度计", "OBS", "OBS-3A", "膜过滤法", "实验室分析",
        "透明度盘", "塞氏盘", "optical backscatter", "turbidity meter",
        "measured", "sensor", "filtration",
    ]

    if has_method_intent:
        if any(word.lower() in row_text.lower() for word in method_evidence_words):
            score += 8

        if relation == "相关":
            score -= 3

    return score


def retrieve_graph_context(
    question: str,
    relations_path: str | Path | None,
    top_k: int = 8,
) -> list[dict]:
    rows = load_relations(relations_path)

    if not rows:
        return []

    keywords = extract_keywords(question)
    scored_rows = []

    for row in rows:
        score = score_relation(row, question, keywords)

        if score > 0:
            item = dict(row)
            item["_score"] = score
            scored_rows.append(item)

    if not scored_rows:
        return []

    scored_rows.sort(key=lambda item: item["_score"], reverse=True)

    seen = set()
    deduped = []

    for item in scored_rows:
        key = (item.get("source"), item.get("relation"), item.get("target"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    return deduped[:top_k]


def build_context_text(matched: list[dict]) -> str:
    context_lines = []

    for row in matched:
        source = str(row.get("source", ""))
        relation = str(row.get("relation", ""))
        target = str(row.get("target", ""))
        evidence = str(row.get("evidence", ""))

        context_lines.append(
            f"关系：{source} ——[{relation}]→ {target}\n"
            f"证据：{evidence}"
        )

    return "\n\n".join(context_lines)


def build_qa_prompt(question: str, context_text: str) -> str:
    return f"""
你是“清澈度领域知识图谱构建及问答系统”的智能问答助手。

请严格根据下面的知识图谱检索结果回答用户问题。
如果图谱中没有直接答案，可以基于已有关系进行合理归纳，但不要编造图谱中完全没有的信息。

用户问题：
{question}

知识图谱检索结果：
{context_text}

回答要求：
1. 使用中文回答。
2. 先给出直接答案。
3. 不要简单罗列三元组，要把图谱关系组织成自然语言。
4. 如果问题涉及“方法、监测、测量、仪器”，请区分：
   - 直接监测方法
   - 间接监测指标
   - 辅助校准或实验室分析方法
5. 回答最后用“依据图谱关系”简要列出支撑答案的核心关系。
"""


def fallback_answer(question: str, matched: list[dict]) -> str:
    answer = "根据当前知识图谱，检索到以下相关关系：\n\n"

    for i, row in enumerate(matched, start=1):
        source = str(row.get("source", ""))
        relation = str(row.get("relation", ""))
        target = str(row.get("target", ""))
        evidence = str(row.get("evidence", ""))

        answer += (
            f"{i}. {source} ——[{relation}]→ {target}\n\n"
            f"   证据：{evidence}\n\n"
        )

    return answer


def answer_question(question: str, relations_path: str | Path | None) -> str:
    if not relations_path or not Path(relations_path).exists():
        return "当前还没有构建知识图谱，请先完成图谱构建。"

    rows = load_relations(relations_path)

    if not rows:
        return "当前知识图谱中没有关系数据。"

    question = question.strip()
    matched = retrieve_graph_context(question, relations_path, top_k=8)

    if not matched:
        return "当前知识图谱中没有检索到与该问题直接相关的关系。"

    context_text = build_context_text(matched)
    prompt = build_qa_prompt(question, context_text)

    system_prompt = (
        "你是清澈度领域知识图谱问答助手。"
        "你的任务是根据知识图谱中的实体、关系和证据，"
        "为用户生成准确、简洁、专业的中文答案。"
    )

    try:
        return call_llm(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.2,
        )
    except Exception as exc:
        return (
            "大模型调用失败，以下为知识图谱检索结果：\n\n"
            + fallback_answer(question, matched)
            + f"\n\n错误信息：{exc}"
        )


# ---------------------------------------------------------------------------
# Service orchestration
# ---------------------------------------------------------------------------
class KnowledgeGraphService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.kg_root = settings.var_root / "knowledge_graph"
        self.uploads_dir = self.kg_root / "uploads"
        self.texts_dir = self.kg_root / "texts"
        self.kg_dir = self.kg_root / "kg"
        self.jobs_dir = self.kg_root / "jobs"

        for directory in (self.uploads_dir, self.texts_dir, self.kg_dir, self.jobs_dir):
            directory.mkdir(parents=True, exist_ok=True)

        self._jobs_lock = threading.Lock()

    @property
    def baseline_root(self) -> Path:
        return self.settings.outputs_root / "knowledge_graph"

    # ---- helpers -----------------------------------------------------------
    def _resolve_kg_file(self, name: str) -> tuple[Path | None, str]:
        runtime = self.kg_dir / name
        if runtime.exists():
            return runtime, "runtime"
        baseline = self.baseline_root / name
        if baseline.exists():
            return baseline, "baseline"
        return None, "none"

    def _read_json(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None

    def _write_status_file(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(path)

    def _load_jobs(self) -> list[dict]:
        path = self.jobs_dir / "jobs.json"
        if not path.exists():
            return []
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return []
        return loaded if isinstance(loaded, list) else []

    def _save_jobs(self, jobs: list[dict]) -> None:
        path = self.jobs_dir / "jobs.json"
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(jobs, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(path)

    def _append_job(self, record: dict[str, Any]) -> None:
        with self._jobs_lock:
            jobs = [j for j in self._load_jobs() if j.get("job_id") != record.get("job_id")]
            jobs.append(record)
            self._save_jobs(jobs)

    def _job_view(self, record: dict[str, Any]) -> dict[str, Any]:
        status = self._read_json(Path(str(record.get("status_file", "")))) or {}
        terminal = status.get("status") in TERMINAL_STATUSES
        pid = record.get("pid")
        if not terminal and isinstance(pid, int) and not self._pid_exists(pid):
            status = {**status, "status": ORPHANED_STATUS, "message": "任务进程已退出且无完成标记。"}
        return {**record, **status}

    @staticmethod
    def _pid_exists(pid: int) -> bool:
        if not isinstance(pid, int) or pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    # ---- sync operations ---------------------------------------------------
    def summary(self) -> dict[str, Any]:
        graph = self.graph()
        return {
            "uploads": len(list(self.uploads_dir.glob("*.pdf"))),
            "texts": len(list(self.texts_dir.glob("*.txt"))),
            "node_count": graph["node_count"],
            "edge_count": graph["edge_count"],
            "source": graph["source"],
            "llm_configured": is_llm_configured(),
        }

    def list_uploads(self) -> list[dict]:
        return sorted(
            [
                {"name": path.name, "size_bytes": path.stat().st_size}
                for path in self.uploads_dir.glob("*.pdf")
            ],
            key=lambda item: item["name"],
        )

    def upload_pdfs(self, files: list[UploadFile]) -> dict[str, Any]:
        if not files:
            raise ValueError("未选择任何 PDF 文件。")

        saved = []
        skipped = []

        for upload in files:
            filename = Path(upload.filename or "uploaded.pdf").name
            if Path(filename).suffix.lower() != ".pdf":
                skipped.append({"name": filename, "reason": "仅支持 PDF 文件。"})
                continue
            target = self.uploads_dir / filename
            with target.open("wb") as handle:
                while chunk := upload.file.read(1024 * 1024):
                    handle.write(chunk)
            upload.file.close()
            saved.append({"name": filename, "size_bytes": target.stat().st_size})

        return {"saved": saved, "skipped": skipped}

    def clear_uploads(self) -> int:
        count = 0
        for path in self.uploads_dir.glob("*.pdf"):
            path.unlink()
            count += 1
        return count

    def list_texts(self) -> dict[str, list[dict]]:
        txt = sorted(
            [
                {"name": path.name, "size_bytes": path.stat().st_size}
                for path in self.texts_dir.glob("*.txt")
            ],
            key=lambda item: item["name"],
        )
        json_files = sorted(
            [
                {"name": path.name, "size_bytes": path.stat().st_size}
                for path in self.texts_dir.glob("*.json")
            ],
            key=lambda item: item["name"],
        )
        return {"txt": txt, "json": json_files}

    def preprocess(
        self,
        files: list[str],
        write_json: bool = False,
        keep_captions: bool = False,
    ) -> dict[str, Any]:
        selected = [Path(f).name for f in files if f]
        if not selected:
            raise ValueError("请至少选择一个 PDF 文件。")

        results: list[ExtractionResult] = []
        processed = []
        errors = []

        for name in selected:
            pdf_path = self.uploads_dir / name
            if not pdf_path.exists():
                errors.append({"name": name, "error": "文件不存在。"})
                continue
            try:
                result = extract_structured_text(pdf_path, keep_captions=keep_captions)
                result = write_outputs(result, self.texts_dir, write_json=write_json)
                results.append(result)
                processed.append({
                    "name": name,
                    "title_len": len(result.title),
                    "abstract_len": len(result.abstract),
                    "keywords_len": len(result.keywords),
                    "body_len": len(result.body),
                    "notes": result.notes,
                })
            except Exception as exc:  # pragma: no cover - depends on PDF content
                errors.append({"name": name, "error": str(exc)})

        if results:
            write_log(results, self.texts_dir / "process_log.csv")

        return {"processed": processed, "errors": errors, "processed_count": len(processed)}

    def clear_texts(self) -> int:
        count = 0
        for pattern in ("*.txt", "*.json", "process_log.csv"):
            for path in self.texts_dir.glob(pattern):
                path.unlink()
                count += 1
        return count

    def clear_kg(self) -> int:
        count = 0
        for name in DOWNLOADABLE_FILES:
            path = self.kg_dir / name
            if path.exists():
                path.unlink()
                count += 1
        return count

    def graph(self) -> dict[str, Any]:
        path, source = self._resolve_kg_file("graph.json")
        if path is None:
            return {"nodes": [], "edges": [], "node_count": 0, "edge_count": 0, "source": "none"}

        data = self._read_json(path) or {}
        nodes = data.get("nodes", [])
        edges = data.get("edges", [])
        return {
            "nodes": nodes,
            "edges": edges,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "source": source,
        }

    def qa(self, question: str) -> dict[str, Any]:
        question = (question or "").strip()
        if not question:
            raise ValueError("请输入问题。")

        path, source = self._resolve_kg_file("relations.csv")
        answer = answer_question(question, path)
        matched = retrieve_graph_context(question, path, top_k=8)

        return {
            "question": question,
            "answer": answer,
            "matched_relations": matched,
            "source": source,
        }

    def file_download_path(self, name: str) -> Path:
        if name not in DOWNLOADABLE_FILES:
            raise FileNotFoundError(f"未知的图谱文件: {name}")
        path, _source = self._resolve_kg_file(name)
        if path is None:
            raise FileNotFoundError(f"图谱文件不存在: {name}")
        return path

    # ---- background build ---------------------------------------------------
    def start_build(self, files: list[str], max_chars: int = 1200) -> dict[str, Any]:
        selected = [Path(f).name for f in files if f]
        if not selected:
            raise ValueError("请至少选择一个文本文件。")

        missing = [name for name in selected if not (self.texts_dir / name).exists()]
        if missing:
            raise FileNotFoundError("文本文件不存在: " + ", ".join(missing))

        job_id = uuid4().hex[:12]
        run_root = self.jobs_dir / job_id
        run_root.mkdir(parents=True, exist_ok=False)

        status_file = run_root / "run_status.json"
        stdout_log = run_root / "logs" / "stdout.log"
        stderr_log = run_root / "logs" / "stderr.log"
        stdout_log.parent.mkdir(parents=True, exist_ok=True)

        started_at = utc_now()
        record = {
            "job_id": job_id,
            "created_at": started_at,
            "started_at": started_at,
            "files": selected,
            "max_chars": max_chars,
            "status": RUNNING_STATUS,
            "status_file": str(status_file),
            "stdout_log": str(stdout_log),
            "stderr_log": str(stderr_log),
        }

        command = [
            sys.executable,
            "-m",
            "backend.app.tasks.kg_job_runner",
            "--kg-dir",
            str(self.kg_dir),
            "--text-dir",
            str(self.texts_dir),
            "--status-file",
            str(status_file),
            "--selected-files",
            json.dumps(selected, ensure_ascii=False),
            "--max-chars",
            str(max_chars),
        ]

        stdout_handle = stdout_log.open("w", encoding="utf-8")
        stderr_handle = stderr_log.open("w", encoding="utf-8")
        try:
            process = subprocess.Popen(
                command,
                cwd=str(self.settings.project_root),
                stdout=stdout_handle,
                stderr=stderr_handle,
            )
        finally:
            stdout_handle.close()
            stderr_handle.close()

        record["pid"] = process.pid
        record["command"] = command

        self._write_status_file(
            status_file,
            {
                "status": RUNNING_STATUS,
                "started_at": started_at,
                "progress": 0,
                "message": "构建任务已启动。",
            },
        )
        self._append_job(record)
        return self._job_view(record)

    def list_build_jobs(self) -> list[dict]:
        views = [self._job_view(record) for record in self._load_jobs()]
        return sorted(views, key=lambda item: item.get("created_at", ""), reverse=True)

    def refresh_build_job(self, job_id: str) -> dict[str, Any]:
        record = next(
            (item for item in self._load_jobs() if item.get("job_id") == job_id),
            None,
        )
        if record is None:
            raise KeyError(job_id)
        return self._job_view(record)
