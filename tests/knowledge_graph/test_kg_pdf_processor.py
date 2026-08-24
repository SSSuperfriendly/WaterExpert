from __future__ import annotations

import unittest

from backend.app.services.kg_pdf_processor import (
    clean_inline,
    clean_line,
    extract_sections_from_lines,
    format_txt,
    is_page_number,
    looks_like_caption,
    looks_like_reference_start,
    normalize_for_repeat,
    ExtractionResult,
)


class CleanLineTest(unittest.TestCase):
    def test_none_becomes_empty_string(self) -> None:
        self.assertEqual(clean_line(None), "")

    def test_collapses_whitespace_and_strips(self) -> None:
        self.assertEqual(clean_line("  水体  清澈度\t度  "), "水体 清澈度 度")

    def test_replaces_non_breaking_space(self) -> None:
        self.assertEqual(clean_line("透明度 监测"), "透明度 监测")

    def test_clean_inline_collapses_all_whitespace(self) -> None:
        self.assertEqual(clean_inline("透明度\n监测\n方法"), "透明度 监测 方法")


class PageNumberTest(unittest.TestCase):
    def test_plain_number(self) -> None:
        self.assertTrue(is_page_number("123"))

    def test_chinese_page_number(self) -> None:
        self.assertTrue(is_page_number("第 12 页"))

    def test_english_page_number(self) -> None:
        self.assertTrue(is_page_number("Page 3 of 10"))

    def test_slash_form(self) -> None:
        self.assertTrue(is_page_number("3 / 5"))

    def test_regular_text_is_not_page_number(self) -> None:
        self.assertFalse(is_page_number("水体透明度监测方法"))


class CaptionTest(unittest.TestCase):
    def test_chinese_figure(self) -> None:
        self.assertTrue(looks_like_caption("图1 透明度监测示意图"))

    def test_english_table(self) -> None:
        self.assertTrue(looks_like_caption("Table 2. Sampling stations"))

    def test_regular_text_is_not_caption(self) -> None:
        self.assertFalse(looks_like_caption("水体透明度受悬浮物影响"))


class ReferenceStartTest(unittest.TestCase):
    def test_chinese_references(self) -> None:
        self.assertTrue(looks_like_reference_start("参考文献"))

    def test_english_references(self) -> None:
        self.assertTrue(looks_like_reference_start("References"))

    def test_regular_text_is_not_reference(self) -> None:
        self.assertFalse(looks_like_reference_start("结论与展望"))


class NormalizeForRepeatTest(unittest.TestCase):
    def test_digits_replaced_and_lowercased(self) -> None:
        self.assertEqual(normalize_for_repeat("Page 12 of 30"), "page # of #")


class ExtractSectionsTest(unittest.TestCase):
    def test_extracts_abstract_keywords_and_body(self) -> None:
        lines = [
            "摘要：本文研究了水体透明度的监测方法。",
            "关键词：透明度；监测；悬浮物",
            "引言",
            "水体透明度受悬浮物浓度影响。",
            "参考文献",
            "[1] 作者. 论文标题. 2020.",
        ]

        abstract, keywords, body = extract_sections_from_lines(lines)

        self.assertEqual(abstract, "本文研究了水体透明度的监测方法。")
        self.assertEqual(keywords, "透明度；监测；悬浮物")
        self.assertIn("水体透明度受悬浮物浓度影响。", body)
        # References are excluded from the body.
        self.assertNotIn("参考文献", body)
        self.assertNotIn("[1]", body)


class FormatTxtTest(unittest.TestCase):
    def test_includes_present_sections_only(self) -> None:
        result = ExtractionResult(
            source_pdf="paper.pdf",
            title="透明度监测",
            abstract="摘要内容",
            keywords="关键词内容",
            body="正文内容",
            notes=[],
        )

        text = format_txt(result)

        self.assertIn("标题：", text)
        self.assertIn("摘要：", text)
        self.assertIn("关键词：", text)
        self.assertIn("正文：", text)

    def test_omits_missing_sections(self) -> None:
        result = ExtractionResult(
            source_pdf="paper.pdf",
            title="",
            abstract="",
            keywords="",
            body="正文内容",
            notes=[],
        )

        text = format_txt(result)

        self.assertNotIn("标题：", text)
        self.assertNotIn("摘要：", text)
        self.assertIn("正文：", text)


if __name__ == "__main__":
    unittest.main()
