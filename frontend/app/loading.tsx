export default function Loading() {
  return (
    <div className="space-y-4">
      <div className="skeleton h-8 w-48" />
      <div className="grid gap-3 md:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => <div key={i} className="skeleton h-28" />)}
      </div>
    </div>
  );
}
