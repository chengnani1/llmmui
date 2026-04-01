import { Fragment, useState } from "react";
import InfoCard from "../components/InfoCard";
import StatusBadge from "../components/StatusBadge";
import { resultRows } from "../mock/data";

export default function ResultsPage() {
  const [expandedId, setExpandedId] = useState(resultRows[0].id);

  return (
    <InfoCard title="分析结果表">
      <div className="overflow-hidden rounded-2xl border border-slate-200">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-slate-500">
            <tr>
              <th className="px-4 py-3 font-medium">任务编号</th>
              <th className="px-4 py-3 font-medium">应用名称</th>
              <th className="px-4 py-3 font-medium">权限类型</th>
              <th className="px-4 py-3 font-medium">风险等级</th>
              <th className="px-4 py-3 font-medium">是否过度请求</th>
              <th className="px-4 py-3 font-medium">是否重复请求</th>
              <th className="px-4 py-3 font-medium">解释说明</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 bg-white">
            {resultRows.map((row) => (
              <Fragment key={row.id}>
                <tr
                  className="cursor-pointer transition hover:bg-slate-50"
                  onClick={() => setExpandedId((prev) => (prev === row.id ? "" : row.id))}
                >
                  <td className="px-4 py-4 font-medium text-slate-800">{row.taskId}</td>
                  <td className="px-4 py-4 text-slate-600">{row.appName}</td>
                  <td className="px-4 py-4 text-slate-600">{row.permission}</td>
                  <td className="px-4 py-4">
                    <StatusBadge text={row.level} />
                  </td>
                  <td className="px-4 py-4 text-slate-600">{row.excessive}</td>
                  <td className="px-4 py-4 text-slate-600">{row.duplicated}</td>
                  <td className="px-4 py-4 text-slate-600">{row.summary}</td>
                </tr>
                {expandedId === row.id && (
                  <tr className="bg-slate-50">
                    <td colSpan="7" className="p-5">
                      <div className="grid grid-cols-[0.65fr_1.35fr] gap-5">
                        <div className="flex h-64 items-center justify-center rounded-2xl border border-dashed border-slate-300 bg-white text-center text-sm leading-7 text-slate-500">
                          界面截图占位图
                          <br />
                          1080 × 1920
                        </div>
                        <div className="space-y-4">
                          <div className="rounded-2xl border border-slate-200 bg-white p-4">
                            <div className="text-sm font-semibold text-slate-900">交互链摘要</div>
                            <div className="mt-3 text-sm leading-7 text-slate-600">{row.chain}</div>
                          </div>
                          <div className="rounded-2xl border border-slate-200 bg-white p-4">
                            <div className="text-sm font-semibold text-slate-900">分析说明</div>
                            <div className="mt-3 text-sm leading-7 text-slate-600">{row.detail}</div>
                          </div>
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </InfoCard>
  );
}
