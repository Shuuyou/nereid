"""演示视频 v2：全页面分场景录制（每场景独立视频段），配合字幕烧录。
用法: backend/.venv/bin/python scripts/record_demo_v2.py [base_url]
产出: docs/demo-video/scenes/01_*.webm ... + scenes.json（段落时长清单，供字幕对齐）"""
import asyncio
import json
import sys
import time
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "docs" / "demo-video" / "scenes"
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3200"
W, H = 1600, 900

# (文件名, 中文字幕, 场景函数)
SCENES = []


def scene(name, caption):
    def deco(fn):
        SCENES.append((name, caption, fn))
        return fn
    return deco


async def settle(pg, ms):
    await pg.wait_for_timeout(ms)


async def slow_scroll(pg, times=3, step=350, dwell=1400):
    for i in range(times):
        await pg.evaluate(f"window.scrollTo(0, {(i + 1) * step})")
        await settle(pg, dwell)
    await pg.evaluate("window.scrollTo(0, 0)")
    await settle(pg, 1200)


@scene("01-duty", "今日值班台——待复核 / 高优 / 新KEV 三队列，情报实时流入")
async def s_duty(pg):
    await pg.goto(f"{BASE}/", wait_until="networkidle", timeout=30000)
    await settle(pg, 5000)
    await slow_scroll(pg, 4, 400, 1600)


@scene("02-items", "情报检索——KEV 在野利用一键过滤，行点击速览")
async def s_items(pg):
    await pg.goto(f"{BASE}/items?kev=1", wait_until="networkidle", timeout=30000)
    await settle(pg, 3500)
    try:
        await pg.locator("tbody tr").first.click()
        await settle(pg, 3500)  # 速览抽屉
        await pg.keyboard.press("Escape")
        await settle(pg, 800)
    except Exception:
        pass
    await slow_scroll(pg, 2, 500, 1500)


@scene("03-detail", "情报卡——评分依据逐项展开，来源确认、映射、富化维度")
async def s_detail(pg):
    await pg.goto(f"{BASE}/items?kev=1", wait_until="networkidle", timeout=30000)
    await settle(pg, 3000)
    try:
        await pg.locator("tbody tr td a").first.click()
        await settle(pg, 3500)
    except Exception:
        pass
    await slow_scroll(pg, 4, 450, 1800)


@scene("04-graph", "知识图谱——实体关系展开，多跳问答的底层证据网")
async def s_graph(pg):
    await pg.goto(f"{BASE}/graph", wait_until="networkidle", timeout=30000)
    await settle(pg, 2500)
    try:
        inp = pg.locator("input").first
        await inp.fill("CVE-2024-37032")
        await pg.keyboard.press("Enter")
        await settle(pg, 6000)
        await pg.mouse.move(900, 450)
        await settle(pg, 4000)
    except Exception:
        pass


@scene("05-qa", "深度问答——多跳问题：实时推理链、行内引用、置信度")
async def s_qa(pg):
    await pg.goto(f"{BASE}/qa", wait_until="networkidle", timeout=30000)
    await settle(pg, 2200)
    ta = pg.locator("textarea").first
    await ta.click()
    await ta.press_sequentially("最近一周有哪些 AI 基础设施高危漏洞？", delay=55)
    await settle(pg, 900)
    await ta.press("Enter")
    # 等置信条出现（完成标记），最多 130s；DeepSeek 拥塞时推理链画面也有信息量
    try:
        await pg.wait_for_selector("text=置信", timeout=130000)
        await settle(pg, 2000)
        # 展开推理链
        try:
            await pg.locator("text=推理链").first.click()
            await settle(pg, 3000)
        except Exception:
            pass
    except Exception:
        await settle(pg, 5000)


@scene("06-review", "HITL 复核——低置信条目确认 / 回炉，全程留痕可撤销")
async def s_review(pg):
    await pg.goto(f"{BASE}/review", wait_until="networkidle", timeout=30000)
    await settle(pg, 3000)
    try:
        await pg.locator("tbody tr").first.click()
        await settle(pg, 3000)
        await pg.keyboard.press("Escape")
        await settle(pg, 800)
    except Exception:
        pass


@scene("07-foryou", "为你推荐——画像驱动，命中条目给推荐理由")
async def s_foryou(pg):
    await pg.goto(f"{BASE}/for-you", wait_until="networkidle", timeout=30000)
    await settle(pg, 5000)
    await slow_scroll(pg, 2, 400, 1400)


@scene("08-reports", "专题报告——日报自动生成，STIX 2.1 标准化导出")
async def s_reports(pg):
    await pg.goto(f"{BASE}/reports", wait_until="networkidle", timeout=30000)
    await settle(pg, 4500)
    await slow_scroll(pg, 2, 400, 1400)


@scene("09-sources", "数据源监控——42 源注册、健康度、累计采集量")
async def s_sources(pg):
    await pg.goto(f"{BASE}/sources", wait_until="networkidle", timeout=30000)
    await settle(pg, 4500)
    await slow_scroll(pg, 2, 450, 1400)


@scene("10-pipeline", "流水线——LangGraph DAG 每次运行、节点耗时全可追溯")
async def s_pipeline(pg):
    await pg.goto(f"{BASE}/pipeline", wait_until="networkidle", timeout=30000)
    await settle(pg, 5500)
    await slow_scroll(pg, 2, 400, 1500)


async def main():
    from playwright.async_api import async_playwright
    OUT.mkdir(parents=True, exist_ok=True)
    timing = []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for name, caption, fn in SCENES:
            ctx = await b.new_context(
                viewport={"width": W, "height": H}, device_scale_factor=1.5,
                record_video_dir=str(OUT / name), record_video_size={"width": W, "height": H})
            pg = await ctx.new_page()
            t0 = time.time()
            try:
                await fn(pg)
            except Exception as e:
                print(f"[{name}] warn: {e}")
            finally:
                try:
                    await pg.close()
                except Exception:
                    pass
                await ctx.close()
            timing.append({"name": name, "caption": caption,
                           "dur": round(time.time() - t0, 1)})
            print(f"[{name}] {timing[-1]['dur']}s")
        await b.close()
    (OUT.parent / "scenes.json").write_text(json.dumps(timing, ensure_ascii=False, indent=2))
    print(json.dumps(timing, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
