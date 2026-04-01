import InfoCard from "../components/InfoCard";
import StatCard from "../components/StatCard";
import StatusBadge from "../components/StatusBadge";
import { dashboardStats, deviceInfo, recentTasks } from "../mock/data";

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-[1.35fr_1fr] gap-6">
        <InfoCard title="系统简介">
          <div className="grid grid-cols-[1.25fr_0.75fr] gap-6">
            <div className="rounded-2xl bg-slate-950 p-6 text-slate-100">
              <div className="text-sm uppercase tracking-[0.25em] text-slate-400">Overview</div>
              <div className="mt-4 text-2xl font-semibold leading-10">
                面向 Android 应用权限交互链的智能合规分析前端原型
              </div>
              <div className="mt-4 text-sm leading-7 text-slate-300">
                系统覆盖应用导入、设备连接、权限事件采集、交互链语义分析、风险结果展示与历史记录管理等核心流程，可为论文展示、说明书撰写与系统截图提供统一界面。
              </div>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-6">
              <div className="text-sm font-medium text-slate-500">当前设备</div>
              <div className="mt-3 flex items-center gap-3">
                <StatusBadge text={deviceInfo.status} />
                <span className="text-sm text-slate-600">{deviceInfo.model}</span>
              </div>
              <dl className="mt-6 space-y-4 text-sm">
                <div className="flex items-center justify-between">
                  <dt className="text-slate-500">设备编号</dt>
                  <dd className="font-medium text-slate-800">{deviceInfo.id}</dd>
                </div>
                <div className="flex items-center justify-between">
                  <dt className="text-slate-500">系统版本</dt>
                  <dd className="font-medium text-slate-800">{deviceInfo.osVersion}</dd>
                </div>
                <div className="flex items-center justify-between">
                  <dt className="text-slate-500">电量状态</dt>
                  <dd className="font-medium text-slate-800">{deviceInfo.battery}</dd>
                </div>
              </dl>
            </div>
          </div>
        </InfoCard>
        <InfoCard title="统计信息">
          <div className="grid grid-cols-2 gap-4">
            {dashboardStats.map((item) => (
              <StatCard key={item.label} {...item} />
            ))}
          </div>
        </InfoCard>
      </div>

      <div className="grid grid-cols-[0.95fr_1.05fr] gap-6">
        <InfoCard title="设备连接状态卡片">
          <div className="rounded-2xl border border-blue-200 bg-blue-50 p-6">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm text-blue-700">连接概览</div>
                <div className="mt-2 text-2xl font-semibold text-slate-900">设备通信稳定，采集链路可用</div>
              </div>
              <StatusBadge text="已连接" />
            </div>
            <div className="mt-6 grid grid-cols-2 gap-4 text-sm">
              {[
                ["ADB 通信状态", "正常"],
                ["截图采集能力", "可用"],
                ["日志写入状态", "已启用"],
                ["最近检测时间", "2026-04-01 10:30"],
              ].map(([label, value]) => (
                <div key={label} className="rounded-xl border border-blue-100 bg-white p-4">
                  <div className="text-slate-500">{label}</div>
                  <div className="mt-2 font-semibold text-slate-800">{value}</div>
                </div>
              ))}
            </div>
          </div>
        </InfoCard>

        <InfoCard title="最近任务列表卡片">
          <div className="overflow-hidden rounded-2xl border border-slate-200">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50 text-left text-slate-500">
                <tr>
                  <th className="px-4 py-3 font-medium">任务编号</th>
                  <th className="px-4 py-3 font-medium">应用名称</th>
                  <th className="px-4 py-3 font-medium">状态</th>
                  <th className="px-4 py-3 font-medium">风险</th>
                  <th className="px-4 py-3 font-medium">时间</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {recentTasks.map((task) => (
                  <tr key={task.id}>
                    <td className="px-4 py-4 font-medium text-slate-800">{task.id}</td>
                    <td className="px-4 py-4 text-slate-600">{task.appName}</td>
                    <td className="px-4 py-4">
                      <StatusBadge text={task.status} />
                    </td>
                    <td className="px-4 py-4">
                      <StatusBadge text={task.risk} />
                    </td>
                    <td className="px-4 py-4 text-slate-500">{task.time}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </InfoCard>
      </div>
    </div>
  );
}
