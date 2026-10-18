#!/usr/bin/env python3
"""答辩 PPT 生成：按 docs/07 大纲产出 14 页深色风 PPTX（含讲稿 notes）。
匿名约束：无学校/队名/人名（赛题硬性要求）。
用法: backend/.venv/bin/python scripts/gen_pptx.py docs/nereid-defense.pptx
"""
import sys

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Pt

BG = RGBColor(0x0B, 0x14, 0x26)
PANEL = RGBColor(0x12, 0x1E, 0x33)
ACC = RGBColor(0x38, 0xBD, 0xF8)
ACC2 = RGBColor(0x34, 0xD3, 0x99)
TXT = RGBColor(0xE6, 0xEE, 0xF7)
DIM = RGBColor(0x9A, 0xB0, 0xC8)
WARN = RGBColor(0xFB, 0xB4, 0x24)

W, H = Emu(12192000), Emu(6858000)  # 16:9


def _slide(prs):
    s = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = BG
    return s


def _box(s, x, y, w, h):
    tb = s.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    return tf


def _add(tf, text, size=14, bold=False, color=TXT, first=False, align=None, space_after=4):
    p = tf.paragraphs[0] if first and not tf.paragraphs[0].runs else tf.add_paragraph()
    r = p.add_run()
    r.text = text
    f = r.font
    f.size = Pt(size)
    f.bold = bold
    f.color.rgb = color
    f.name = "Noto Sans CJK SC"
    if align:
        p.alignment = align
    p.space_after = Pt(space_after)
    return p


def _head(s, title, kicker=None):
    tf = _box(s, Emu(500000), Emu(280000), Emu(11200000), Emu(700000))
    if kicker:
        _add(tf, kicker, 12, True, ACC, first=True)
        _add(tf, title, 28, True, TXT)
    else:
        _add(tf, title, 30, True, TXT, first=True)


def _notes(s, text):
    s.notes_slide.notes_text_frame.text = text


def _card(s, x, y, w, h, title, lines, title_color=ACC):
    from pptx.enum.shapes import MSO_SHAPE
    sh = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
    sh.fill.solid()
    sh.fill.fore_color.rgb = PANEL
    sh.line.color.rgb = RGBColor(0x24, 0x3B, 0x5C)
    sh.line.width = Pt(0.75)
    tf = sh.text_frame
    tf.word_wrap = True
    tf.margin_left = Emu(120000)
    tf.margin_top = Emu(80000)
    _add(tf, title, 14, True, title_color, first=True)
    for ln in lines:
        _add(tf, ln, 11, False, TXT, space_after=2)
    return sh


def _tbl(s, x, y, w, h, rows, col_w=None, header=True, font=12):
    g = s.shapes.add_table(len(rows), len(rows[0]), x, y, w, h)
    t = g.table
    if col_w:
        for i, cw in enumerate(col_w):
            t.columns[i].width = cw
    for ri, row in enumerate(rows):
        for ci, cell in enumerate(row):
            c = t.cell(ri, ci)
            c.text = str(cell)
            for p in c.text_frame.paragraphs:
                for r in p.runs:
                    r.font.size = Pt(font)
                    r.font.name = "Noto Sans CJK SC"
                    r.font.color.rgb = TXT if not (header and ri == 0) else ACC
                    if header and ri == 0:
                        r.font.bold = True
            c.fill.solid()
            c.fill.fore_color.rgb = PANEL if ri % 2 else RGBColor(0x0F, 0x1A, 0x2E)
    return t


def build(dst):
    prs = Presentation()
    prs.slide_width = W
    prs.slide_height = H

    # ---------- P1 封面 ----------
    s = _slide(prs)
    tf = _box(s, Emu(900000), Emu(2100000), Emu(10400000), Emu(2400000))
    _add(tf, "捞针 · Nereid", 54, True, TXT, first=True)
    _add(tf, "智能体驱动的 AI 安全知识情报系统", 22, False, ACC)
    _add(tf, "大海捞针，我们捞给你看", 15, False, DIM, space_after=16)
    _add(tf, '第三届"中国电子杯"高校 ICT 产教融合创新大赛 · 赛题九', 13, False, DIM)
    _notes(s, "各位评委好。我们带来的作品叫'捞针'——大海捞针的捞针；英文代号 Nereid，希腊神话里在深海潜游的五十位海之宁芙——也就是我们的智能体群。安全情报的本质就是从信息的海洋里捞出那根针，我们用一群 AI 智能体把这件事做成了自动化的系统。")

    # ---------- P2 痛点 ----------
    s = _slide(prs)
    _head(s, "AI 安全情报的三个断层", "痛点 · 为什么")
    _card(s, Emu(600000), Emu(1300000), Emu(3500000), Emu(2600000), "散 · 源碎片化",
          ["CVE/NVD/GHSA/KEV 官方", "20+ 社区 RSS/邮件列表", "厂商 CSAF 公告", "论文 / 政策文件", "信息散在十几处,人工拼凑"])
    _card(s, Emu(4300000), Emu(1300000), Emu(3500000), Emu(2600000), "浅 · 只有 CVE",
          ["提示注入 / 投毒 / Agent 滥用", "大多没有 CVE 编号", "现有平台不覆盖", "AI 安全 ≠ 漏洞库"])
    _card(s, Emu(8000000), Emu(1300000), Emu(3500000), Emu(2600000), "断 · 决策链条长",
          ["影响面→利用情况→修复", "应急响应以小时/天计", "问答能力缺失", "情报≠可追问的知识"])
    tf = _box(s, Emu(600000), Emu(4400000), Emu(11000000), Emu(900000))
    _add(tf, "赛题要的不是又一个漏洞库，而是能回答问题的情报系统。", 20, True, ACC2, first=True)
    _add(tf, "用 AI 原生架构，做 AI 安全的情报。", 15, False, DIM)
    _notes(s, "传统情报平台解决'有没有'，我们解决'懂不懂'——这是整份方案的出发点。30 秒。")

    # ---------- P3 总览 ----------
    s = _slide(prs)
    _head(s, "一张图看懂捞针 · Nereid", "系统总览 · 架构")
    rows = [
        ("表现层", "Next.js 大屏 / 情报卡 / 图谱探索 / 深度问答 / 为你推荐 / 报告", ACC),
        ("智能体编排", "LangGraph 三层：Pipeline DAG · QueryAgent(Supervisor-as-Tools) · Analyst(P-E-C)", ACC2),
        ("能力层", "监测 11类41源 · 富化 8worker · Qdrant 混合检索 · Neo4j 图谱", TXT),
        ("底座", "PostgreSQL / Qdrant / Neo4j / Redis · docker-compose · systemd 自愈", DIM),
    ]
    y = 1300000
    for name, desc, c in rows:
        _card(s, Emu(600000), Emu(y), Emu(10900000), Emu(1050000), name, [desc], c)
        y += 1150000
    tf = _box(s, Emu(600000), Emu(6000000), Emu(11000000), Emu(500000))
    _add(tf, "45,034 条情报 · 29,134 图谱节点 · 58,471 边 · 全流程无人值守", 14, True, WARN, first=True)
    _notes(s, "四层结构：表现层六个界面，编排层三种图拓扑，能力层四大模块，底座四存储。数字全部是 2026-10-18 实测快照。")

    # ---------- P4 监测 ----------
    s = _slide(prs)
    _head(s, "11 类 41 源 · 四层去重 · 核心链路 ≤1 小时", "情报监测")
    _tbl(s, Emu(500000), Emu(1250000), Emu(6000000), Emu(2600000), [
        ("源类别", "代表"),
        ("CVE 官方", "cvelistV5 git 增量 (15min) · NVD · GHSA · OSV"),
        ("威胁情报", "CISA KEV · ExploitDB · 厂商 CSAF"),
        ("社区", "20+ 中英 RSS · HN · 邮件列表"),
        ("AI 专用", "攻击/事件/政策源 · 网信办 · TC260 · GB"),
    ], font=11)
    _card(s, Emu(6800000), Emu(1250000), Emu(4800000), Emu(2600000), "四层去重漏斗",
          ["① URL 哈希", "② 编号集合并集 (CVE/GHSA 多号)", "③ SimHash 近重复", "④ MinHash-LSH 合并"],
          ACC2)
    _card(s, Emu(500000), Emu(4100000), Emu(11100000), Emu(1400000), "实测时效",
          ["cvelistV5 准实时通道 p50 ≈ 30.1 min · nvidia_psirt 0.5 min · 金丝雀注入→可检索 43.7s",
           "满分线 ≥7 类 ≤6h → 实测 11 类 ≤1h（约 12 倍超出）"], WARN)
    _notes(s, "强调自动化程度分：APScheduler 全程无人值守 + 断点续采 + 失败降级不阻塞（cisa.gov 不可达自动切 GitHub KEV 镜像）。")

    # ---------- P5 富化 ----------
    s = _slide(prs)
    _head(s, "10+ 维度自动富化 · 置信度合并 · 宁可缺不可错", "情报富化")
    _card(s, Emu(500000), Emu(1250000), Emu(5600000), Emu(2800000), "富化维度（8 worker 并发）",
          ["CVSS/EPSS/KEV/SSVC 评分", "PoC + 四级可信度(含恶意检测)", "资产测绘 · 论文关联", "CWE→CAPEC→ATT&CK/ATLAS",
           "版本解析 · 修复建议 · 中文摘要", "相似情报 · 攻击链 · AI 分类"], ACC)
    _card(s, Emu(6300000), Emu(1250000), Emu(5300000), Emu(2800000), "准确率机制",
          ["官方字段锁死：CVSS/EPSS/KEV 只信确定性源", "LLM 只做抽取，evidence+schema 校验", "校验器闸门 + 低置信 abstain 入复核",
           "来源权重 官方1.0 > 厂商0.95 > 聚合0.75 > LLM0.6", "层级真值：CNA+ADP(Vulnrichment) → NVD Primary"], ACC2)
    _card(s, Emu(500000), Emu(4300000), Emu(11100000), Emu(1300000), "实测",
          ["字段级准确率 99.2% · 召回 100%（n=30 分层随机，三源真值逐条比对）· vuln 富化覆盖 100%",
           "EPSS 每日官方 CSV 全量 31,457 条 · extra.cvss_source/epss_as_of 溯源"], WARN)
    _notes(s, "富化准确率 5 分看这里：官方字段直接锁死，LLM 产出必须带证据过校验器，置信度不够宁可标存疑——准确率是设计出来的，不是口号。45 秒。")

    # ---------- P6 问答 ----------
    s = _slide(prs)
    _head(s, "Agentic RAG + 知识图谱多跳桥接", "情报问答")
    _card(s, Emu(500000), Emu(1250000), Emu(11100000), Emu(1500000), "证据管线（并发扇出）",
          ["extract → 路由∥原句混合检索∥KG 种子扩展∥KEV 意图直查 (4路 gather) → Agent 单轮决策(parallel_tool_calls)",
           "→ 候选合并 → RRF 预排 → 交叉编码重排(真实 top 段) → KG ≤3 跳桥接 → 行内引用生成 → 置信度校准 → SSE 真流式"], ACC)
    _tbl(s, Emu(500000), Emu(3100000), Emu(5600000), Emu(2300000), [
        ("指标", "实测"),
        ("整体命中率", "100%（12 题自建集 live）"),
        ("多跳命中率", "100%"),
        ("推理链完备率(≥3步)", "100%（每步带 ms 耗时）"),
        ("引用精确率", "83.3%"),
        ("延迟", "快路径 3.2s · 深度 p50 8.9s"),
    ], font=11)
    _card(s, Emu(6300000), Emu(3100000), Emu(5300000), Emu(2300000), "凭什么可信",
          ["每句答案带 [n] 引用，可点回情报卡原文", "trace.steps 完整暴露推理路径（异常不丢）",
           "置信度校准 + <0.25 自动 abstain", "KG 桥接靠图路径，不是向量碰运气"], ACC2)
    _notes(s, "两个评委最关心的点：跨文档靠 KG 最短路径桥接；每句话带引用编号可回查——幻觉在工程上被结构性压住。40 秒。")

    # ---------- P7 智能体 ----------
    s = _slide(prs)
    _head(s, "LangGraph 三层混合编排 —— 按任务选模式", "智能体架构 · 15分")
    _card(s, Emu(500000), Emu(1250000), Emu(3600000), Emu(2900000), "周期链路 · 确定性 DAG",
          ["collect→enrich→index→kg→notify", "节点幂等可重放", "部分失败可续跑", "TaskRun+Redis 实时态"], ACC)
    _card(s, Emu(4300000), Emu(1250000), Emu(3600000), Emu(2900000), "交互链路 · Supervisor-as-Tools",
          ["4 工具：检索/KG/详情/KEV", "单轮决策+parallel_tool_calls", "证据不足自动回退", "轮次预算防失控"], ACC2)
    _card(s, Emu(8100000), Emu(1250000), Emu(3600000), Emu(2900000), "分析链路 · P-E-C",
          ["聚合统计→提纲→逐节→校验", "LLM 不可用时模板兜底", "日报自动产出"], WARN)
    _card(s, Emu(500000), Emu(4400000), Emu(11100000), Emu(1400000), "生产级能力",
          ["PostgreSQL checkpointer durable execution（7 checkpoint/run，崩溃后同 thread_id 断点续跑）",
           "HITL 复核队列 confirm/reject 闭环 · handoff 弹跳预算 · worker 只回结论防上下文膨胀"], ACC)
    _notes(s, "评委如果只看一页请看这页：三套模式对应三类任务，共享 TaskRun+Redis 态——'架构精良且可扩展'的具体含义：加一条新链路=加一张子图。45 秒，本页放慢。")

    # ---------- P8 知识底座 ----------
    s = _slide(prs)
    _head(s, "L1–L6 资产分层 × OWASP × ATLAS × 中文政策", "AI 安全知识底座")
    _card(s, Emu(500000), Emu(1250000), Emu(5600000), Emu(2900000), "三维情报立方体",
          ["L1 基础设施/推理 · L2 模型/数据 · L3 应用/智能体", "L4 供应链 · L5 政策治理 · L6 滥用威胁",
           "OWASP LLM Top10 + ASI Agentic Top10 双标签", "MITRE ATLAS 成熟度三级标注"], ACC)
    _card(s, Emu(6300000), Emu(1250000), Emu(5300000), Emu(2900000), "别人没有的那一层",
          ["CVE+非CVE 双轨：incident/article/policy 同库同问答", "中文政策源（网信办/TC260/GB）国际平台零覆盖",
           "影子漏洞标注（disputed-but-exploited）", "KG：Item-CVE-CWE-Technique-Product-Vendor"], ACC2)
    _card(s, Emu(500000), Emu(4400000), Emu(11100000), Emu(1100000), "实测",
          ["AI 相关条目 2,330 条（L1 2078/L2 138/L3 2196/L4 103/L5 25/L6 13）· KG 29,134 节点 58,471 边"], WARN)
    _notes(s, "回答'为什么是 AI 安全情报系统而不是漏洞库'：EchoLeak 零点击注入、MCP 投毒、GB/T 45654——它们没有 CVSS，但都是安全团队的早报头条。35 秒。")

    # ---------- P9 演示 ----------
    s = _slide(prs)
    _head(s, "一个 SOC 的早晨：从告警到日报，无人值守", "场景演示")
    steps = ["① 大屏态势：41 源实时流入", "② 新 CVE 入库：15min 增量",
             "③ 富化情报卡：8 worker 并发全景", "④ 内网风险问答：多跳推理+引用",
             "⑤ 为你推荐+自动日报：画像驱动"]
    y = 1500000
    for st in steps:
        _card(s, Emu(800000), Emu(y), Emu(10600000), Emu(800000), st, [], ACC)
        y += 950000
    _notes(s, "重点看第三四帧：富化是 8 个 worker 并发跑出来的；'内网跑了 Ollama 和 Milvus 2.4 有什么风险'要跨文档推理，是深度问答的真实考题。若放视频让位给视频。40 秒。")

    # ---------- P10 实测 ----------
    s = _slide(prs)
    _head(s, "满分线 vs 实测", "性能数字收口")
    _tbl(s, Emu(700000), Emu(1300000), Emu(10800000), Emu(3400000), [
        ("评分项", "满分线", "实测"),
        ("数据源覆盖", "≥7 类", "11 类 / 41 源"),
        ("监测时效", "≤6h", "≤1h（cvelistV5 增量 p50≈30min）"),
        ("富化维度/准确率", "≥5 维 / ≥95%", "8 worker 10+ 维 / 准确率 99.2%·召回 100%"),
        ("问答质量", "多跳≥85%、≤5s", "多跳 100%·整体 100%·快路径 3.2s·深度 p50 8.9s"),
        ("数据规模", "—", "45,034 情报 / 29,134 KG 节点 / 58,471 边"),
        ("运维自愈", "—", "systemd 三服务+compose 重启策略，断电自愈"),
    ], font=12)
    tf = _box(s, Emu(700000), Emu(5000000), Emu(10800000), Emu(800000))
    _add(tf, "评测集 12 题 · 方法=关键词命中+引用存在性校验 · reports/eval_qa.json 可现场重跑", 12, False, DIM, first=True)
    _notes(s, "只念表。所有满分线我们都是达到或超出，且每个数字都能现场复现——评测脚本就在代码仓库里。30 秒。")

    # ---------- P11 工程化 ----------
    s = _slide(prs)
    _head(s, "全流程无人值守 · 五条降级线 · 一键部署", "工程化 · 10分")
    _card(s, Emu(500000), Emu(1250000), Emu(5600000), Emu(2900000), "部署与自愈",
          ["docker-compose 全栈一键起（PG/Qdrant/Neo4j/Redis）", "user systemd 三服务 + linger 开机拉起",
           "Prometheus + Grafana 监控告警", "幂等重放 + SAVEPOINT 事务隔离"], ACC)
    _card(s, Emu(6300000), Emu(1250000), Emu(5300000), Emu(2900000), "降级矩阵（真实踩出来的）",
          ["cisa.gov 不可达 → GitHub KEV 官方镜像", "GitHub API 403/限流 → 降级不阻塞",
           "Hunter 无 API 权限 → is_simulated 模拟标注", "GPU 驱动异常 → CPU ONNX 全链路",
           "LLM key 缺失 → 确定性模板兜底"], ACC2)
    _notes(s, "自动化 10 分看'自愈'：五条降级线全部真实踩出来——比如 cisa.gov 国内不可达，系统自动切 GitHub 官方 KEV 镜像。30 秒。")

    # ---------- P12 对比 ----------
    s = _slide(prs)
    _head(s, "为什么是捞针 · Nereid", "与现有方案对比")
    _tbl(s, Emu(600000), Emu(1300000), Emu(11000000), Emu(3600000), [
        ("维度", "通用漏洞库", "商用 TI 平台", "捞针·Nereid"),
        ("AI 资产视角立方体", "无", "无", "L1–L6×OWASP×ATLAS"),
        ("非 CVE 情报(事件/政策)", "无", "部分", "双轨全覆盖"),
        ("攻击链自动生成", "无", "手工", "自动+可视化"),
        ("PoC 可信度分级", "无", "少", "四级含恶意检测"),
        ("中文政策源", "无", "无", "网信办/TC260/GB"),
        ("多跳问答", "无", "弱", "KG 桥接+引用+推理链"),
        ("个性化推荐", "无", "订阅", "画像驱动+理由回显+反馈闭环"),
    ], font=12)
    _notes(s, "通用平台告诉你'有这个洞'，捞针告诉你'这个洞在 AI 资产栈的哪一层、谁在用它、会不会轮到你'。35 秒。")

    # ---------- P13 创新 ----------
    s = _slide(prs)
    _head(s, "差异化创新", "创新点总结")
    inns = [
        ("① AI 资产视角情报立方体", "L1–L6×OWASP×ATLAS×政策 三维投影"),
        ("② CVE+非CVE 双轨", "incident/policy 同库同问答"),
        ("③ 攻击链自动生成", "确定性模板+LLM 润色+可视化"),
        ("④ PoC 四级可信度", "含 7 类恶意特征静态检测"),
        ("⑤ 层级真值源富化", "CNA+ADP→NVD Primary，cvss_source 溯源"),
        ("⑥ Durable execution", "PG checkpointer 断点续跑，生产级编排"),
    ]
    x0, y0 = 600000, 1300000
    for i, (t, d) in enumerate(inns):
        _card(s, Emu(x0 + (i % 3) * 3700000), Emu(y0 + (i // 3) * 1900000),
              Emu(3500000), Emu(1700000), t, [d], ACC if i % 3 == 0 else (ACC2 if i % 3 == 1 else WARN))
    _notes(s, "只点三张卡：立方体/双轨/durable execution。用 AI 原生架构做 AI 安全情报——我们用自己的题目，答自己的题。30 秒。")

    # ---------- P14 结尾 ----------
    s = _slide(prs)
    tf = _box(s, Emu(900000), Emu(2200000), Emu(10400000), Emu(2600000))
    _add(tf, "让每一条漏洞，自己走完从发现到决策的路", 30, True, TXT, first=True, align=PP_ALIGN.CENTER, space_after=20)
    _add(tf, "监测更全更快 · 富化更深更准 · 问答能推理可解释", 16, False, ACC, align=PP_ALIGN.CENTER, space_after=24)
    _add(tf, "捞针 · Nereid", 22, True, TXT, align=PP_ALIGN.CENTER, space_after=6)
    _add(tf, "感谢奇安信命题与组委会", 12, False, DIM, align=PP_ALIGN.CENTER)
    _notes(s, "以上是捞针 Nereid 的全部汇报。它不是又一个漏洞列表，而是一群替安全团队值夜班、在大海里捞针的智能体。谢谢各位评委，请批评指正。15 秒。")

    prs.save(dst)
    print("pptx:", dst, "slides:", len(prs.slides.__iter__.__self__._sldIdLst))


if __name__ == "__main__":
    build(sys.argv[1])
