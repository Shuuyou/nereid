// 浏览器端跟随页面来源主机（localhost:3200→localhost:8000，Tailscale IP→同 IP:8000）；
// SSR/构建期回落 localhost；可用 NEXT_PUBLIC_API_URL 显式覆盖。
export const API = process.env.NEXT_PUBLIC_API_URL
  || (typeof window !== "undefined"
    ? `${window.location.protocol}//${window.location.hostname}:8000`
    : "http://localhost:8000");

async function j(path: string, init?: RequestInit) {
  const r = await fetch(`${API}${path}`, { ...init, cache: "no-store" });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

export const api = {
  health: () => j("/api/health"),
  stats: () => j("/api/stats/overview"),
  items: (p: Record<string, string | number | boolean>) => {
    const q = new URLSearchParams(Object.entries(p).filter(([, v]) => v !== "" && v !== undefined).map(([k, v]) => [k, String(v)]));
    return j(`/api/items?${q}`);
  },
  item: (id: string) => j(`/api/items/${id}`),
  related: (id: string) => j(`/api/items/${id}/related`),
  sources: () => j("/api/sources"),
  runSource: (id: number) => j(`/api/sources/${id}/run`, { method: "POST" }),
  runAll: () => j("/api/collect/run-all", { method: "POST" }),
  enrich: (id: string) => j(`/api/items/${id}/enrich`, { method: "POST" }),
  kgStats: () => j("/api/kg/stats"),
  freshness: () => j("/api/stats/freshness"),
  assetExposure: () => j("/api/stats/asset_exposure"),
  kgSubgraph: (entity: string, depth = 2) => j(`/api/kg/subgraph?entity=${encodeURIComponent(entity)}&depth=${depth}`),
  reports: () => j("/api/reports"),
  report: (id: string) => j(`/api/reports/${id}`),
  dailyReport: () => j("/api/reports/daily", { method: "POST" }),
  qaHistory: (id: string) => j(`/api/qa/sessions/${id}`),
};

export interface QaEvent {
  type: "status" | "token" | "trace" | "citations" | "done" | "error";
  data: any;
}

export async function* streamChat(question: string, sessionId: string | null, deep = true): AsyncGenerator<QaEvent> {
  const r = await fetch(`${API}/api/qa/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, session_id: sessionId, deep }),
  });
  const sid = r.headers.get("X-Session-Id");
  if (!r.ok || !r.body) throw new Error(`chat ${r.status}`);
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  let evType = "message";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const lines = buf.split("\n");
    buf = lines.pop() || "";
    for (const line of lines) {
      if (line.startsWith("event:")) evType = line.slice(6).trim();
      else if (line.startsWith("data:")) {
        try {
          yield { type: evType as QaEvent["type"], data: JSON.parse(line.slice(5)) };
        } catch { /* ignore */ }
      }
    }
  }
  if (sid) yield { type: "status", data: { session_id: sid } };
}

/** 订阅实时情报流（SSE /api/feed/stream），返回取消函数 */
export function subscribeFeed(onItem: (item: any) => void): () => void {
  if (typeof window === "undefined") return () => {};
  const es = new EventSource(`${API}/api/feed/stream`);
  es.addEventListener("new_item", (e) => {
    try { onItem(JSON.parse((e as MessageEvent).data)); } catch { /* ignore */ }
  });
  return () => es.close();
}
