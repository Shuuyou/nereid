"""修订队友答辩 PPT：过时口径→实测、截图占位→实景图、____→真实数字。
用法: backend/.venv/bin/python scripts/fix_teammate_pptx.py
"""
from pptx import Presentation
from pptx.util import Emu, Pt
from pptx.oxml.ns import qn
from pathlib import Path
import copy

ROOT = Path(__file__).resolve().parent.parent
P = str(ROOT / "中国电子杯ICT产教融合大赛-智能体驱动AI安全知识情报系统.pptx")

prs = Presentation(P)


def _runs_text(para):
    return "".join(r.text for r in para.runs)


def set_para_text(para, new):
    """保留首 run 格式写回新文本"""
    if not para.runs:
        r = para.add_run()
        r.text = new
        return
    para.runs[0].text = new
    for r in para.runs[1:]:
        r.text = ""


def walk(shapes):
    for sh in shapes:
        if sh.shape_type == 6:
            yield from walk(sh.shapes)
        else:
            yield sh


def abs_pos(sh):
    """组内 shape → 幻灯片绝对坐标（处理 group chOff/缩放）"""
    x, y, w, h = sh.left, sh.top, sh.width, sh.height
    el = sh._element
    # 向上找父 group
    while el.getparent() is not None and el.getparent().tag.endswith("}grpSpPr") is False:
        el = el.getparent()
        if el.tag.endswith("}grpSp"):
            gp = el.find(qn("p:grpSpPr"))
            if gp is None:
                continue
            off = gp.find(qn("a:off"))
            ext = gp.find(qn("a:ext"))
            coff = gp.find(qn("a:chOff"))
            cext = gp.find(qn("a:chExt"))
            if None in (off, ext, coff, cext):
                continue
            sx = int(ext.get("cx")) / max(1, int(cext.get("cx")))
            sy = int(ext.get("cy")) / max(1, int(cext.get("cy")))
            x = int(off.get("x")) + (x - int(coff.get("x"))) * sx
            y = int(off.get("y")) + (y - int(coff.get("y"))) * sy
            w, h = int(w * sx), int(h * sy)
    return int(x), int(y), int(w), int(h)


def replace_text(slide_idx, old_sub, new_text, first_only=True):
    s = prs.slides[slide_idx]
    done = 0
    for sh in walk(s.shapes):
        if not sh.has_text_frame:
            continue
        for para in sh.text_frame.paragraphs:
            if old_sub in _runs_text(para):
                set_para_text(para, _runs_text(para).replace(old_sub, new_text))
                done += 1
                if first_only:
                    return done
    return done


def replace_blanks(slide_idx, mapping):
    """按段落整体文本匹配替换"""
    s = prs.slides[slide_idx]
    for sh in walk(s.shapes):
        if not sh.has_text_frame:
            continue
        for para in sh.text_frame.paragraphs:
            t = _runs_text(para).strip()
            for key, val in mapping.items():
                if key in t:
                    set_para_text(para, t.replace(key, val))


def fill_placeholder_with_image(slide_idx, placeholder_text, img_path, occurrence=1):
    """找到含占位文字的形状 → 同位置同尺寸插图（留 4% 边距），并清空占位文字"""
    s = prs.slides[slide_idx]
    n = 0
    for sh in walk(s.shapes):
        if not sh.has_text_frame:
            continue
        if placeholder_text in sh.text_frame.text:
            n += 1
            if n == occurrence:
                x, y, w, h = abs_pos(sh)
                # 占位形状往往只是文字，父级边框才是真正图框——尝试找同组最近的大矩形
                pad_x, pad_y = int(w * 0.02), int(h * 0.04)
                px, py = x + pad_x, y + pad_y + Emu(120000)
                pw, ph = int(w * 0.96), int(h * 0.96 - 120000)
                if ph <= 0:
                    ph = int(pw * 9 / 16)
                s.shapes.add_picture(str(img_path), px, py, width=pw, height=ph)
                set_para_text(sh.text_frame.paragraphs[0], "")
                for para in sh.text_frame.paragraphs[1:]:
                    set_para_text(para, "")
                return (x, y, w, h)
    return None


# ============ S3：术语更新 ============
replace_text(2, "实时大屏|", "值班台|", first_only=False)

# ============ S5：源规模 41→42（注册口径）============
replace_text(4, "41 个", "42 个", first_only=True)

# ============ S13/S14/S15：大屏→值班台 + 截图占位→实景 ============
replace_text(12, "实时安全情报大屏", "今日值班台（实时监测工作台）", first_only=False)
fill_placeholder_with_image(12, "截图占位", ROOT / "docs/screenshots/01-duty.png", occurrence=1)
fill_placeholder_with_image(12, "截图占位", ROOT / "docs/screenshots/02-items.png", occurrence=2)

# S14：富化复核→item-detail；图谱→graph；资产看板→duty 底栏(用 for-you? 用 duty 资产表)
fill_placeholder_with_image(13, "局部截图占位", ROOT / "docs/screenshots/03-item-detail.png", occurrence=1)
fill_placeholder_with_image(13, "截图占位", ROOT / "docs/screenshots/06-graph.png", occurrence=1)
fill_placeholder_with_image(13, "截图占位", ROOT / "docs/screenshots/01-duty.png", occurrence=2)

# S15：问答 → qa-answer；报告 → reports
fill_placeholder_with_image(14, "问题、回答、来源引用与工具调用截图", ROOT / "docs/screenshots/10-qa-answer.png")
fill_placeholder_with_image(14, "报告内容与导出入口截图", ROOT / "docs/screenshots/08-reports.png")

# ============ S17：测试环境填空 ============
replace_blanks(16, {
    "CPU / GPU：________    内存：________":
        "CPU 32 核 / GPU 驱动不匹配（全链路 CPU ONNX）    内存 94 GB",
    "OS / 容器 / 模型及依赖版本：________________":
        "Ubuntu 24.04 / Docker 29+Compose / DeepSeek API + Qwen3-Embedding-0.6B + bge-reranker-v2-m3（ONNX）",
})

# ============ S18：实测数字填空 ============
replace_blanks(17, {
    "— / —": "35 / 42",
    "有效入库 ____ 条   成功率 ____%": "有效入库 50,277 条   成功率 84%（24h 任务 1006/1197）",
    "更新时效 P95  ____ s": "更新时效 P95  cvelistV5 增量 p50≈30min",
    "采集至可检索 P95  ____ s": "采集至可检索 P95  43.7 s（金丝雀端到端实测）",
    "P ____%   R ____%   F1 ____%": "P —%   R —%   F1 —%（确定性规则去重为主，未独立评测）",
    "单跳 100%   多跳 100%   跨文档 未测": "单跳 100%   多跳 95.8%   整体 97.9%（12 题）",
    "吞吐 ____ QPS   持续运行 ____ h   失败率 ____%": "吞吐 单机部署未压测   持续运行 >72h（systemd 自愈）   失败率 0%",
    "失败案例：________    原因：________    局限 / 改进：________":
        "失败案例：个别答案 [n] 编号超出引用集    原因：生成侧引用噪声    改进：前端口径校验+未引用候选折叠（已上线）",
})
# 基线表：完整系统行
s18 = prs.slides[17]
for sh in walk(s18.shapes):
    if sh.has_table:
        tbl = sh.table
        for row in tbl.rows:
            cells = [c.text.strip() for c in row.cells]
            if cells and cells[0] == "完整系统":
                row.cells[1].text_frame.paragraphs[0].runs[0].text = "97.9%"
                row.cells[2].text_frame.paragraphs[0].runs[0].text = "95.8%"

prs.save(P)
print("done — slides:", len(prs.slides.__iter__.__self__._sldIdLst))
