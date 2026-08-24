"""Structured text extraction for the knowledge-graph literature pipeline.

Ported from the ``qcd`` Streamlit project (``core/pdf_processor.py``) with the
Streamlit layer removed. The functions here are pure logic that turn a PDF
literature file into a structured text block (title / abstract / keywords /
body), stripping page numbers, repeated headers/footers, and figure captions.

The original module had no Streamlit dependency and depends only on
``fitz`` (PyMuPDF), so the port is faithful.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Tuple

import fitz


@dataclass
class TextBlock:
    text: str
    page_num: int
    x0: float
    y0: float
    x1: float
    y1: float
    avg_font: float
    page_width: float
    page_height: float


@dataclass
class ExtractionResult:
    source_pdf: str
    title: str
    abstract: str
    keywords: str
    body: str
    output_txt: str = ""
    output_json: str = ""
    notes: List[str] = field(default_factory=list)


def clean_line(text: str) -> str:
    if text is None:
        return ""

    text = text.replace(" ", " ")
    text = text.replace("　", " ")
    text = text.replace("﻿", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def clean_inline(text: str) -> str:
    text = clean_line(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_for_repeat(text: str) -> str:
    text = clean_inline(text)
    text = re.sub(r"\d+", "#", text)
    return text.lower()


def is_page_number(text: str) -> bool:
    text = clean_inline(text)

    patterns = [
        r"^\d+$",
        r"^第\s*\d+\s*页$",
        r"^page\s*\d+$",
        r"^page\s*\d+\s*of\s*\d+$",
        r"^-\s*\d+\s*-$",
        r"^\d+\s*/\s*\d+$",
    ]

    return any(re.match(p, text, re.I) for p in patterns)


def looks_like_caption(text: str) -> bool:
    text = clean_inline(text)

    patterns = [
        r"^(图|表)\s*\d+",
        r"^(figure|fig\.?|table)\s*\d+",
    ]

    return any(re.match(p, text, re.I) for p in patterns)


def looks_like_reference_start(text: str) -> bool:
    text = clean_inline(text)
    return bool(re.match(r"^(参考文献|参考资料|references|bibliography)$", text, re.I))


def looks_like_ack_start(text: str) -> bool:
    text = clean_inline(text)
    return bool(re.match(r"^(致谢|acknowledg?ments?|附录|appendix)$", text, re.I))


def looks_like_affiliation_or_contact(text: str) -> bool:
    text = clean_inline(text)

    patterns = [
        r"@",
        r"\bemail\b",
        r"\be-mail\b",
        r"(大学|学院|研究所|Institute|University|College|Laboratory|School|Department)",
        r"(基金|资助项目|Grant|Funding)",
        r"doi[:：]",
        r"received[:：]|accepted[:：]|published[:：]",
    ]

    return any(re.search(p, text, re.I) for p in patterns)


def extract_page_blocks(page, page_num: int) -> List[TextBlock]:
    page_dict = page.get_text("dict")
    page_width = page.rect.width
    page_height = page.rect.height

    blocks: List[TextBlock] = []

    for block in page_dict.get("blocks", []):
        if "lines" not in block:
            continue

        block_lines = []
        font_sizes = []

        for line in block["lines"]:
            spans_text = []

            for span in line.get("spans", []):
                text = clean_inline(span.get("text", ""))

                if text:
                    spans_text.append(text)
                    font_sizes.append(float(span.get("size", 0.0)))

            if spans_text:
                block_lines.append(" ".join(spans_text))

        block_text = clean_inline(" ".join(block_lines))

        if not block_text:
            continue

        x0, y0, x1, y1 = block["bbox"]
        avg_font = sum(font_sizes) / len(font_sizes) if font_sizes else 0.0

        blocks.append(
            TextBlock(
                text=block_text,
                page_num=page_num,
                x0=float(x0),
                y0=float(y0),
                x1=float(x1),
                y1=float(y1),
                avg_font=avg_font,
                page_width=float(page_width),
                page_height=float(page_height),
            )
        )

    return blocks


def sort_blocks_reading_order(blocks: List[TextBlock]) -> List[TextBlock]:
    if not blocks:
        return blocks

    page_width = blocks[0].page_width
    mid_x = page_width / 2

    left_blocks = [b for b in blocks if (b.x0 + b.x1) / 2 < mid_x * 0.98]
    right_blocks = [b for b in blocks if (b.x0 + b.x1) / 2 >= mid_x * 0.98]

    narrow_count = sum((b.x1 - b.x0) < page_width * 0.7 for b in blocks)

    if (
        len(left_blocks) >= 3
        and len(right_blocks) >= 3
        and narrow_count / max(len(blocks), 1) > 0.6
    ):
        return (
            sorted(left_blocks, key=lambda b: (round(b.y0, 1), b.x0))
            + sorted(right_blocks, key=lambda b: (round(b.y0, 1), b.x0))
        )

    return sorted(blocks, key=lambda b: (round(b.y0, 1), b.x0))


def extract_pdf_blocks(pdf_path: str | Path) -> Tuple[List[List[TextBlock]], List[str]]:
    doc = fitz.open(pdf_path)

    pages: List[List[TextBlock]] = []
    notes: List[str] = []
    total_chars = 0

    for page_num, page in enumerate(doc):
        blocks = extract_page_blocks(page, page_num)
        blocks = sort_blocks_reading_order(blocks)

        total_chars += sum(len(b.text) for b in blocks)
        pages.append(blocks)

    doc.close()

    if total_chars < 200:
        notes.append("文本总字符数较少，PDF 可能是扫描版或图片版。")

    return pages, notes


def detect_repeated_headers_footers(
    pages: List[List[TextBlock]],
    top_ratio: float = 0.15,
    bottom_ratio: float = 0.12,
    min_repeat_ratio: float = 0.45,
) -> Tuple[set, set]:
    top_counter = Counter()
    bottom_counter = Counter()
    total_pages = len(pages)

    for page_blocks in pages:
        if not page_blocks:
            continue

        page_height = page_blocks[0].page_height

        for block in page_blocks:
            norm = normalize_for_repeat(block.text)

            if not norm or is_page_number(block.text):
                continue

            if block.y0 <= page_height * top_ratio:
                top_counter[norm] += 1

            if block.y1 >= page_height * (1 - bottom_ratio):
                bottom_counter[norm] += 1

    min_repeat = max(2, int(total_pages * min_repeat_ratio))

    repeated_top = {k for k, v in top_counter.items() if v >= min_repeat}
    repeated_bottom = {k for k, v in bottom_counter.items() if v >= min_repeat}

    return repeated_top, repeated_bottom


def filter_blocks(
    pages: List[List[TextBlock]],
    keep_captions: bool = False
) -> List[List[TextBlock]]:
    repeated_top, repeated_bottom = detect_repeated_headers_footers(pages)

    filtered_pages: List[List[TextBlock]] = []

    for page_blocks in pages:
        page_result: List[TextBlock] = []

        for block in page_blocks:
            text = clean_inline(block.text)

            if not text:
                continue

            if is_page_number(text):
                continue

            norm = normalize_for_repeat(text)

            if block.y0 <= block.page_height * 0.15 and norm in repeated_top:
                continue

            if block.y1 >= block.page_height * 0.88 and norm in repeated_bottom:
                continue

            if not keep_captions and looks_like_caption(text):
                continue

            page_result.append(block)

        filtered_pages.append(page_result)

    return filtered_pages


def looks_like_title_candidate(text: str) -> bool:
    text = clean_inline(text)

    if not text:
        return False

    if len(text) < 8 or len(text) > 220:
        return False

    if re.search(r"\b(abstract|keywords?)\b", text, re.I):
        return False

    if looks_like_affiliation_or_contact(text):
        return False

    if is_page_number(text):
        return False

    return True


def extract_title(first_page_blocks: List[TextBlock]) -> str:
    if not first_page_blocks:
        return ""

    abstract_y = None

    for block in first_page_blocks:
        text = clean_inline(block.text)

        if re.match(r"^(摘要|abstract)\b", text, re.I):
            abstract_y = block.y0
            break

    candidates = []

    for block in first_page_blocks:
        text = clean_inline(block.text)

        if block.y0 > block.page_height * 0.55:
            continue

        if abstract_y is not None and block.y0 >= abstract_y:
            continue

        if not looks_like_title_candidate(text):
            continue

        candidates.append(block)

    if not candidates:
        return ""

    def score(block: TextBlock):
        text = clean_inline(block.text)
        length_score = 3 if 20 <= len(text) <= 160 else 1
        center_x = (block.x0 + block.x1) / 2
        center_penalty = abs(center_x - block.page_width / 2)

        return (
            length_score,
            block.avg_font * 2,
            -center_penalty,
            -block.y0,
        )

    best = max(candidates, key=score)
    return clean_inline(best.text)


def pages_to_lines(pages: List[List[TextBlock]]) -> List[str]:
    lines = []

    for page_blocks in pages:
        for block in page_blocks:
            text = clean_inline(block.text)

            if text:
                lines.append(text)

    return lines


def join_body_lines(lines: List[str]) -> str:
    if not lines:
        return ""

    merged = []

    for line in lines:
        line = clean_inline(line)

        if not line:
            continue

        if not merged:
            merged.append(line)
            continue

        prev = merged[-1]

        if re.search(r"[。！？.!?:：]$", prev):
            merged.append(line)
        elif re.match(
            r"^(\d+(\.\d+)*\s*|[一二三四五六七八九十]+[、.]|引言|结论|讨论|结果|方法|材料与方法|研究区概况|研究方法)",
            line,
            re.I,
        ):
            merged.append("\n" + line)
        else:
            merged[-1] = prev + " " + line

    text = "\n".join(merged)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def find_section_positions(full_text: str):
    result = {
        "abstract_match": None,
        "keywords_match": None,
        "body_start": 0,
        "body_end": len(full_text),
    }

    abstract_patterns = [
        r"(摘要)\s*[:：]?\s*(.*?)(?=\n\s*(关键词|关键字|Keywords?)\s*[:：])",
        r"(abstract)\s*[:：]?\s*(.*?)(?=\n\s*(keywords?)\s*[:：])",
        r"(摘要)\s*[:：]?\s*(.*?)(?=\n\s*[1１]\s*[、.\s])",
        r"(abstract)\s*[:：]?\s*(.*?)(?=\n\s*[1１]\s*[、.\s])",
    ]

    for pattern in abstract_patterns:
        match = re.search(pattern, full_text, re.I | re.S)

        if match:
            result["abstract_match"] = match
            break

    keyword_patterns = [
        r"(关键词|关键字|keywords?)\s*[:：]?\s*(.*?)(?=\n)"
    ]

    for pattern in keyword_patterns:
        match = re.search(pattern, full_text, re.I | re.S)

        if match:
            result["keywords_match"] = match
            break

    if result["keywords_match"]:
        result["body_start"] = result["keywords_match"].end()
    elif result["abstract_match"]:
        result["body_start"] = result["abstract_match"].end()
    else:
        match = re.search(
            r"\n\s*(引言|INTRODUCTION|[1１]\s*[、.\s]|一[、.\s])",
            full_text,
            re.I,
        )

        if match:
            result["body_start"] = match.start()

    stop_patterns = [
        r"\n\s*(参考文献|参考资料)\s*$",
        r"\n\s*(references|bibliography)\s*$",
        r"\n\s*(致谢|acknowledg?ments?)\s*$",
        r"\n\s*(附录|appendix)\s*$",
    ]

    for pattern in stop_patterns:
        match = re.search(
            pattern,
            full_text[result["body_start"] :],
            re.I | re.M,
        )

        if match:
            result["body_end"] = result["body_start"] + match.start()
            break

    return result


def extract_sections_from_lines(lines: List[str]) -> Tuple[str, str, str]:
    full_text = "\n".join(lines)
    pos = find_section_positions(full_text)

    abstract = ""
    keywords = ""

    abstract_match = pos["abstract_match"]
    keywords_match = pos["keywords_match"]

    if abstract_match:
        abstract = clean_inline(abstract_match.group(2))

    if keywords_match:
        keywords = clean_inline(keywords_match.group(2))

    body_text = full_text[pos["body_start"] : pos["body_end"]].strip()

    body_lines = [
        clean_inline(x)
        for x in body_text.splitlines()
        if clean_inline(x)
    ]

    body_lines = [
        line
        for line in body_lines
        if not is_page_number(line)
        and not looks_like_reference_start(line)
        and not looks_like_ack_start(line)
        and not looks_like_caption(line)
    ]

    body = join_body_lines(body_lines)

    return abstract, keywords, body


def extract_structured_text(
    pdf_path: str | Path,
    keep_captions: bool = False
) -> ExtractionResult:
    pages, notes = extract_pdf_blocks(pdf_path)
    filtered_pages = filter_blocks(pages, keep_captions=keep_captions)

    first_page = filtered_pages[0] if filtered_pages else []
    title = extract_title(first_page)

    lines = pages_to_lines(filtered_pages)

    abstract, keywords, body = extract_sections_from_lines(lines)

    if not title:
        notes.append("未稳定识别到标题。")

    if not abstract:
        notes.append("未识别到摘要。")

    if not keywords:
        notes.append("未识别到关键词。")

    if len(body) < 200:
        notes.append("正文提取长度较短，请人工抽查。")

    return ExtractionResult(
        source_pdf=str(pdf_path),
        title=title,
        abstract=abstract,
        keywords=keywords,
        body=body,
        notes=notes,
    )


def format_txt(result: ExtractionResult) -> str:
    parts = []

    if result.title:
        parts.append("标题：\n" + result.title)

    if result.abstract:
        parts.append("摘要：\n" + result.abstract)

    if result.keywords:
        parts.append("关键词：\n" + result.keywords)

    if result.body:
        parts.append("正文：\n" + result.body)

    return "\n\n".join(parts).strip()


def write_outputs(
    result: ExtractionResult,
    output_dir: str | Path,
    write_json: bool = False
) -> ExtractionResult:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    stem = Path(result.source_pdf).stem

    txt_path = output_dir / f"clean_{stem}.txt"
    txt_path.write_text(format_txt(result), encoding="utf-8")

    result.output_txt = str(txt_path)

    if write_json:
        json_path = output_dir / f"clean_{stem}.json"
        json_path.write_text(
            json.dumps(asdict(result), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        result.output_json = str(json_path)

    return result


def write_log(results: List[ExtractionResult], log_path: str | Path) -> None:
    log_path = Path(log_path)

    with log_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)

        writer.writerow([
            "source_pdf",
            "title_len",
            "abstract_len",
            "keywords_len",
            "body_len",
            "output_txt",
            "output_json",
            "notes",
        ])

        for result in results:
            writer.writerow([
                result.source_pdf,
                len(result.title),
                len(result.abstract),
                len(result.keywords),
                len(result.body),
                result.output_txt,
                result.output_json,
                " | ".join(result.notes),
            ])
