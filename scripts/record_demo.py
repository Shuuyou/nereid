"""演示视频自动录制：Playwright 逐场景走查真实产品，输出分段 webm → ffmpeg 合成 mp4。
用法: backend/.venv/bin/python scripts/record_demo.py [base_url]
产出: docs/demo-video/*.mp4 + demo_full.mp4"""
import asyncio
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "docs" / "demo-video"
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3200"
W, H = 1600, 900


async def scene(ctx, name, fn):
    page = await ctx.new_page()
    try:
        await fn(page)
    except Exception as e:
        print(f"[{name}] warn: {e}")
    await page.close()
    print(f"[{name}] done")


async def main():
    from playwright.async_api import async_playwright
    OUT.mkdir(exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={"width": W, "height": H},
                                  device_scale_factor=1.5,
                                  record_video_dir=str(OUT / "raw"),
                                  record_video_size={"width": W, "height": H})
        page = await ctx.new_page()

        # ---- S2.1 值班台（25s）----
        await page.goto(f"{BASE}/", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(6000)
        await page.mouse.move(960, 450)
        # 缓慢扫过队列区
        for i in range(4):
            await page.mouse.move(700 + i * 60, 350 + i * 120)
            await page.wait_for_timeout(1400)
        await page.evaluate("window.scrollTo(0, 320)")
        await page.wait_for_timeout(3500)
        await page.evaluate("window.scrollTo(0, 900)")
        await page.wait_for_timeout(4000)
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(2500)

        # ---- S2.2 情报检索→情报卡（40s）----
        await page.goto(f"{BASE}/items?kev=1", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(4000)
        # 点开第一行的速览抽屉
        row = page.locator("tbody tr").first
        await row.click()
        await page.wait_for_timeout(3000)
        # 关闭抽屉进详情
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(800)
        await page.locator("tbody tr td a").first.click()
        await page.wait_for_timeout(4000)
        await page.evaluate("window.scrollTo(0, 500)")
        await page.wait_for_timeout(3000)
        await page.evaluate("window.scrollTo(0, 1100)")
        await page.wait_for_timeout(3500)
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(2000)

        # ---- S2.4 知识图谱（20s）----
        await page.goto(f"{BASE}/graph", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2500)
        inp = page.locator("input").first
        await inp.fill("CVE-2024-37032")
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(6000)
        await page.mouse.move(900, 450)
        await page.wait_for_timeout(5000)

        # ---- S2.3 深度问答（流式全录，约 60-90s）----
        await page.goto(f"{BASE}/qa", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2500)
        ta = page.locator("textarea").first
        await ta.click()
        await ta.press_sequentially("我们内网部署了 Ollama 和 Milvus 2.4，有什么相关风险？", delay=60)
        await page.wait_for_timeout(1000)
        await page.locator("textarea").first.press("Enter")
        # 等到完成标记出现（推理链 receipt/置信条），最长 120s
        try:
            await page.wait_for_selector("text=置信", timeout=120000)
        except Exception:
            pass
        await page.wait_for_timeout(2500)
        # 展开推理链给评委看
        try:
            rc = page.locator("text=推理链").first
            await rc.click()
            await page.wait_for_timeout(3000)
        except Exception:
            pass
        # 滚一下右栏证据
        await page.mouse.move(1450, 400)
        await page.wait_for_timeout(3000)

        # ---- S2.5 复核队列（20s）----
        await page.goto(f"{BASE}/review", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)
        row = page.locator("tbody tr").first
        try:
            await row.click()
            await page.wait_for_timeout(3500)  # peek 抽屉
        except Exception:
            pass
        # 确认一条演示复核动作
        try:
            btn = page.locator("button:has-text('确认')").last
            await btn.click()
            await page.wait_for_timeout(3000)
        except Exception:
            pass

        # ---- 个性化/报告/数据源/流水线（40s）----
        for path, dwell in [("/for-you", 5000), ("/reports", 4000),
                            ("/sources", 4000), ("/pipeline", 6000)]:
            await page.goto(f"{BASE}{path}", wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(dwell)

        await page.close()
        await ctx.close()
        await b.close()
        print("all scenes done")


if __name__ == "__main__":
    asyncio.run(main())
