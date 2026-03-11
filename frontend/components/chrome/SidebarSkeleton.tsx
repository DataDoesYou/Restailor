export default function SidebarSkeleton() {
  return (
  <aside className="sticky top-0 h-[calc(100vh-2rem)] md:h-[calc(100vh-3rem)] border-r border-slate-800 text-slate-200 text-sm md:text-base w-[240px] min-w-[240px] max-w-[240px] shrink-0 box-border overflow-hidden">
      <div className="space-y-3 pr-5 animate-pulse">
        <div className="h-6 w-24 bg-slate-700/60 rounded" />
        <div className="h-4 w-40 bg-slate-700/50 rounded" />
        <div className="h-4 w-28 bg-slate-700/40 rounded" />
        <div className="h-4 w-32 bg-slate-700/40 rounded" />
        <div className="h-4 w-20 bg-slate-700/40 rounded" />
      </div>
    </aside>
  );
}
