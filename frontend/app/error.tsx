"use client";
import { TriangleAlert, RotateCcw } from "lucide-react";

export default function Error({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <div className="panel w-full max-w-md">
        <div className="panel-h">
          <span className="t">RUNTIME ERROR</span>
          <span className="st st-err"><span className="dot" />FAULT</span>
        </div>
        <div className="panel-b flex flex-col items-center gap-3 py-6 text-center">
          <TriangleAlert size={26} strokeWidth={1.5} className="text-err" />
          <div className="text-[14px] font-medium text-fg">页面渲染出错</div>
          <div className="mono max-w-full truncate px-4 text-[12px] text-faint" title={error.message}>
            {error.message}
          </div>
          <button className="btn btn-acc mt-2" onClick={reset}>
            <RotateCcw size={12} strokeWidth={1.75} />重试
          </button>
        </div>
      </div>
    </div>
  );
}
