import { useMemo, useState } from "react";
import InfoCard from "../components/InfoCard";
import StatusBadge from "../components/StatusBadge";
import { historyRows } from "../mock/data";

export default function HistoryPage() {
  const [filters, setFilters] = useState({
    appName: "",
    permission: "",
    level: "",
  });

  const filteredRows = useMemo(() => {
    return historyRows.filter((row) => {
      const matchesName = !filters.appName || row.appName.includes(filters.appName);
      const matchesPermission = !filters.permission || row.permission === filters.permission;
      const matchesLevel = !filters.level || row.level === filters.level;
      return matchesName && matchesPermission && matchesLevel;
    });
  }, [filters]);

  return (
    <div className="space-y-6">
      <InfoCard title="历史分析记录筛选">
        <div className="grid grid-cols-[1.1fr_0.9fr_0.9fr_0.7fr] gap-4">
          <input
            className="input"
            placeholder="按应用名称筛选"
            value={filters.appName}
            onChange={(event) => setFilters((prev) => ({ ...prev, appName: event.target.value }))}
          />
          <select
            className="input"
            value={filters.permission}
            onChange={(event) => setFilters((prev) => ({ ...prev, permission: event.target.value }))}
          >
            <option value="">全部权限类型</option>
            <option value="ACCESS_FINE_LOCATION">ACCESS_FINE_LOCATION</option>
            <option value="READ_CONTACTS">READ_CONTACTS</option>
            <option value="CAMERA">CAMERA</option>
            <option value="READ_EXTERNAL_STORAGE">READ_EXTERNAL_STORAGE</option>
            <option value="RECORD_AUDIO">RECORD_AUDIO</option>
          </select>
          <select
            className="input"
            value={filters.level}
            onChange={(event) => setFilters((prev) => ({ ...prev, level: event.target.value }))}
          >
            <option value="">全部风险等级</option>
            <option value="高风险">高风险</option>
            <option value="中风险">中风险</option>
            <option value="低风险">低风险</option>
          </select>
          <button
            className="btn-secondary"
            onClick={() => setFilters({ appName: "", permission: "", level: "" })}
          >
            重置筛选
          </button>
        </div>
      </InfoCard>

      <InfoCard title="历史分析记录">
        <div className="overflow-hidden rounded-2xl border border-slate-200">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50 text-left text-slate-500">
              <tr>
                <th className="px-4 py-3 font-medium">应用名称</th>
                <th className="px-4 py-3 font-medium">权限类型</th>
                <th className="px-4 py-3 font-medium">风险等级</th>
                <th className="px-4 py-3 font-medium">分析日期</th>
                <th className="px-4 py-3 font-medium">操作人</th>
                <th className="px-4 py-3 font-medium">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white">
              {filteredRows.map((row) => (
                <tr key={row.id}>
                  <td className="px-4 py-4 font-medium text-slate-800">{row.appName}</td>
                  <td className="px-4 py-4 text-slate-600">{row.permission}</td>
                  <td className="px-4 py-4">
                    <StatusBadge text={row.level} />
                  </td>
                  <td className="px-4 py-4 text-slate-600">{row.date}</td>
                  <td className="px-4 py-4 text-slate-600">{row.operator}</td>
                  <td className="px-4 py-4">
                    <div className="flex gap-2">
                      <button className="btn-secondary">查看详情</button>
                      <button className="btn-primary px-4 py-2.5">导出报告</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </InfoCard>
    </div>
  );
}
