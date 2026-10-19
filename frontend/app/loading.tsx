import { Skeleton } from "@/components/ui";

export default function Loading() {
  return (
    <div>
      {/* spec-row 骨架 */}
      <Skeleton className="h-3 w-64" />
      {/* 页头骨架 */}
      <div className="mb-5 mt-3 flex items-end justify-between">
        <div className="space-y-2">
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-3 w-72" />
        </div>
        <Skeleton className="h-[30px] w-24" />
      </div>
      {/* stat strip 骨架：hairline 栅格 */}
      <div
        className="grid overflow-hidden rounded-md border border-line"
        style={{ gridTemplateColumns: "repeat(4,1fr)", gap: 1, background: "rgba(255,255,255,0.07)" }}
      >
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="bg-bg px-4 py-3.5">
            <Skeleton className="h-2.5 w-16" />
            <Skeleton className="mt-2 h-6 w-24" />
          </div>
        ))}
      </div>
      {/* 表行骨架 */}
      <div className="mt-7 space-y-px border-t border-line pt-3">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="flex items-center gap-4 py-1.5">
            <Skeleton className="h-3.5 w-10" />
            <Skeleton className="h-3.5 flex-1" />
            <Skeleton className="h-3.5 w-20" />
            <Skeleton className="h-3.5 w-14" />
            <Skeleton className="h-3.5 w-24" />
          </div>
        ))}
      </div>
    </div>
  );
}
