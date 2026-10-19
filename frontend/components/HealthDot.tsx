"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

/** 侧栏底健康状态——真探测 /api/health（30s 轮询），不再是恒绿假指示 */
export function HealthDot() {
  const [ok, setOk] = useState<boolean | null>(null);
  useEffect(() => {
    let t: any;
    const ping = () =>
      api.health().then((h) => setOk(h?.status === "ok")).catch(() => setOk(false))
        .finally(() => { t = setTimeout(ping, 30_000); });
    ping();
    return () => clearTimeout(t);
  }, []);
  if (ok === null) return null;
  return (
    <div className="flex items-center gap-1.5 text-[11px] text-faint" title={ok ? "后端健康" : "后端不可达"}>
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: ok ? "var(--ok)" : "var(--err)" }} />
      {ok ? "在线" : "离线"}
    </div>
  );
}
