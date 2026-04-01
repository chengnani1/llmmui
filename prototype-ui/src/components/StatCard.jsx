export default function StatCard({ label, value, unit, accent }) {
  return (
    <div className="panel p-5">
      <div className="muted">{label}</div>
      <div className={`mt-4 flex items-end gap-2 text-3xl font-bold ${accent}`}>
        <span>{value}</span>
        <span className="pb-1 text-sm font-medium text-slate-500">{unit}</span>
      </div>
    </div>
  );
}
