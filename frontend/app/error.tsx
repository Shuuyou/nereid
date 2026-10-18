"use client";
import { TriangleAlert, RotateCcw } from "lucide-react";

export default function Error({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="card mx-auto mt-16 flex max-w-md flex-col items-center gap-3 py-10 text-center">
      <TriangleAlert size={28} strokeWidth={1.5} className="text-critical" />
      <div className="text-[14px] font-medium text-fg">页面渲染出错</div>
      <div className="mono max-w-full truncate px-4 text-[11px] text-faint">{error.message}</div>
      <button className="btn-soft mt-2 !text-[12px]" onClick={reset}>
        <RotateCcw size={12} />重试
      </button>
    </div>
  );
}
