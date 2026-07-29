export default function PageHeader({ title, subtitle, right }) {
  return (
    <div className="px-8 pt-10 pb-6 border-b border-white/10 flex items-end justify-between gap-6 flex-wrap">
      <div>
        <div className="text-[10px] tracking-[0.3em] uppercase text-[#00FF66] font-mono mb-2 flex items-center gap-2">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-[#00FF66] animate-pulse" />
          LIVE
        </div>
        <h1 className="font-heading text-4xl tracking-tight leading-none">{title}</h1>
        {subtitle && <p className="mt-3 text-sm text-white/50 font-mono">{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}
