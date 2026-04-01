const colorMap = {
  已连接: "bg-emerald-100 text-emerald-700",
  已完成: "bg-slate-200 text-slate-700",
  分析中: "bg-blue-100 text-blue-700",
  高风险: "bg-rose-100 text-rose-700",
  中风险: "bg-amber-100 text-amber-700",
  低风险: "bg-emerald-100 text-emerald-700",
  待判定: "bg-slate-100 text-slate-600",
  高: "bg-rose-100 text-rose-700",
  中: "bg-amber-100 text-amber-700",
  低: "bg-emerald-100 text-emerald-700",
};

export default function StatusBadge({ text }) {
  return <span className={`tag ${colorMap[text] || "bg-slate-100 text-slate-700"}`}>{text}</span>;
}
