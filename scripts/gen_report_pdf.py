#!/usr/bin/env python3
"""技术报告 markdown → PDF（fpdf2 + NotoSansCJK，无 libreoffice 依赖）。
用法: backend/.venv/bin/python scripts/gen_report_pdf.py docs/08-技术报告.md docs/报告.pdf
"""
import re
import sys

from fpdf import FPDF

def _cjk_font() -> str:
    """NotoSansCJK-Regular.ttc 是多面字体（fpdf 不认 .ttc），运行时抽 SC 面到缓存。"""
    import os
    cache = "/tmp/NotoSansSC-secagent.otf"
    if not os.path.exists(cache):
        from fontTools.ttLib import TTCollection
        for f in TTCollection("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc").fonts:
            if "SC" in (f["name"].getDebugName(4) or "") and "Mono" not in (f["name"].getDebugName(4) or ""):
                f.save(cache)
                break
    return cache


FONT_REG = FONT_BOLD = _cjk_font()


class R(FPDF):
    def __init__(self):
        super().__init__()
        self.add_font("cjk", "", FONT_REG)
        self.add_font("cjk", "B", FONT_BOLD)
        self.set_auto_page_break(True, 18)
        self.set_margins(20, 20, 20)

    def header(self):
        self.set_font("cjk", "", 8)
        self.set_text_color(120)
        self.cell(0, 8, "捞针 · Nereid — 智能体驱动的 AI 安全知识情报系统", align="C")
        self.ln(10)

    def footer(self):
        self.set_y(-14)
        self.set_font("cjk", "", 8)
        self.set_text_color(120)
        self.cell(0, 8, f"{self.page_no()}", align="C")


def _t(pdf, s, size=10, style="", h=6):
    pdf.set_font("cjk", style, size)
    pdf.set_text_color(0)
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"`(.+?)`", r"\1", s)
    pdf.multi_cell(0, h, s, new_x="LMARGIN", new_y="NEXT")


def build(src, dst):
    pdf = R()
    pdf.add_page()
    for ln in open(src, encoding="utf-8"):
        s = ln.rstrip("\n")
        st = s.strip()
        if st.startswith("```"):
            continue
        if not st:
            pdf.ln(2)
            continue
        m = re.match(r"^(#{1,4})\s+(.*)", st)
        if m:
            lvl = len(m.group(1))
            pdf.ln(3)
            _t(pdf, m.group(2), size={1: 18, 2: 14, 3: 12}.get(lvl, 11), style="B", h=8)
            continue
        if st.startswith("|"):
            pdf.set_font("cjk", "", 8)
            pdf.set_text_color(0)
            cells = [c.strip() for c in st.strip("|").split("|")]
            if not re.match(r"^[:\-\s|]+$", st):
                cells = cells[:8]
                w = max((pdf.w - 40) / len(cells), 18)
                for c in cells:
                    pdf.cell(min(w, 70), 7, c[:26], border=1)
                pdf.ln()
            continue
        if re.match(r"^[-*]\s+", st):
            _t(pdf, "  • " + re.sub(r"^[-*]\s+", "", st), h=5.5)
        elif re.match(r"^\d+[.)]\s+", st):
            _t(pdf, "  " + st, h=5.5)
        elif st.startswith(">"):
            pdf.set_text_color(80)
            _t(pdf, st.lstrip("> "), h=5.5)
        elif st == "---":
            pdf.ln(2)
        else:
            _t(pdf, st, h=5.5)
    pdf.output(dst)
    print("pdf:", dst)


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2])
