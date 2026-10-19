"""PPT/报告用界面截图：Playwright 无头 Chromium 遍历关键页面。
用法: backend/.venv/bin/python scripts/take_screenshots.py [base_url]
输出: docs/screenshots/*.png (1920x1080)"""
import asyncio
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "docs" / "screenshots"
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3200"


async def main():
    from playwright.async_api import async_playwright
    OUT.mkdir(exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1920, "height": 1080},
                              device_scale_factor=1.5)

        async def shot(path_url: str, name: str, wait=2500, scroll=None):
            try:
                await pg.goto(f"{BASE}{path_url}", wait_until="networkidle",
                              timeout=30000)
            except Exception:
                await pg.wait_for_timeout(3000)
            if scroll:
                await pg.evaluate(f"window.scrollTo(0, {scroll})")
            await pg.wait_for_timeout(wait)
            await pg.screenshot(path=str(OUT / name), full_page=False)
            print("shot:", name)

        await shot("/", "01-duty.png", 3500)
        await shot("/items", "02-items.png", 3000)

        # 情报卡详情：取一条 KEV 高优条目
        import urllib.request, json as _j
        items = _j.load(urllib.request.urlopen(
            f"{BASE}/api/items?limit=1&sort=priority&severity=critical", timeout=10))
        iid = items["items"][0]["id"] if items.get("items") else None
        if iid:
            await shot(f"/items/{iid}", "03-item-detail.png", 3500)

        await shot("/review", "04-review.png", 3000)
        await shot("/sources", "05-sources.png", 3000)
        await shot("/graph", "06-graph.png", 4000)
        await shot("/for-you", "07-foryou.png", 3500)
        await shot("/reports", "08-reports.png", 3000)
        await shot("/pipeline", "09-pipeline.png", 3500)

        # QA：提交真实问题，等 done 再截
        await pg.goto(f"{BASE}/qa", wait_until="networkidle", timeout=30000)
        ta = pg.locator("textarea").first
        await ta.fill("我们内网部署了 Ollama 和 Milvus 2.4，有什么相关风险？")
        await pg.locator("button[type=submit], button:has(svg)").last.click()
        await pg.wait_for_timeout(1500)
        # 等答案流式完成（done → 状态行消失/置信条出现），最长 90s
        try:
            await pg.wait_for_selector("text=置信", timeout=90000)
        except Exception:
            pass
        await pg.wait_for_timeout(2000)
        await pg.screenshot(path=str(OUT / "10-qa-answer.png"), full_page=False)
        print("shot: 10-qa-answer.png")

        await b.close()


if __name__ == "__main__":
    asyncio.run(main())
