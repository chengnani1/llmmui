import { useState } from "react";
import InfoCard from "../components/InfoCard";
import StatusBadge from "../components/StatusBadge";
import { deviceInfo, importLogs } from "../mock/data";

export default function DeviceImportPage() {
  const [taskForm, setTaskForm] = useState({
    appName: "示例出行应用",
    taskId: "TASK-20260401-003",
    mode: "标准全量采集",
  });
  const [started, setStarted] = useState(false);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-[0.82fr_1.18fr] gap-6">
        <InfoCard title="设备连接信息">
          <div className="rounded-2xl bg-slate-950 p-6 text-slate-100">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm uppercase tracking-[0.25em] text-slate-500">Device Monitor</div>
                <div className="mt-3 text-2xl font-semibold">{deviceInfo.model}</div>
              </div>
              <StatusBadge text={deviceInfo.status} />
            </div>
            <div className="mt-6 space-y-4 rounded-2xl border border-slate-800 bg-slate-900 p-5 text-sm">
              <div className="flex justify-between">
                <span className="text-slate-400">设备编号</span>
                <span>{deviceInfo.id}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">系统版本</span>
                <span>{deviceInfo.osVersion}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">调试状态</span>
                <span>USB/本地模拟器已启用</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">最近心跳</span>
                <span>2026-04-01 10:31:24</span>
              </div>
            </div>
          </div>
        </InfoCard>

        <InfoCard title="APK 上传与任务配置">
          <div className="grid grid-cols-[0.92fr_1.08fr] gap-5">
            <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-6">
              <div className="text-sm uppercase tracking-[0.25em] text-slate-400">APK Upload</div>
              <div className="mt-4 text-xl font-semibold text-slate-900">拖拽或点击上传 APK 文件</div>
              <div className="mt-3 text-sm leading-7 text-slate-500">
                原型项目使用本地 mock 数据，上传区域仅作界面演示。建议截图时展示标准上传流程。
              </div>
              <div className="mt-8 rounded-2xl border border-slate-200 bg-white p-5 text-sm text-slate-600">
                已选择文件：`sample-travel-app.apk`
              </div>
            </div>
            <div className="space-y-4">
              <div>
                <label className="mb-2 block text-sm font-medium text-slate-700">应用名称</label>
                <input
                  className="input"
                  value={taskForm.appName}
                  onChange={(event) => setTaskForm((prev) => ({ ...prev, appName: event.target.value }))}
                />
              </div>
              <div>
                <label className="mb-2 block text-sm font-medium text-slate-700">任务编号</label>
                <input
                  className="input"
                  value={taskForm.taskId}
                  onChange={(event) => setTaskForm((prev) => ({ ...prev, taskId: event.target.value }))}
                />
              </div>
              <div>
                <label className="mb-2 block text-sm font-medium text-slate-700">采集模式</label>
                <select
                  className="input"
                  value={taskForm.mode}
                  onChange={(event) => setTaskForm((prev) => ({ ...prev, mode: event.target.value }))}
                >
                  <option>标准全量采集</option>
                  <option>快速链路采集</option>
                  <option>高风险重点采集</option>
                </select>
              </div>
              <button className="btn-primary w-full" onClick={() => setStarted(true)}>
                开始采集
              </button>
              {started && (
                <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
                  已创建 mock 任务，当前状态：正在采集交互链与权限事件。
                </div>
              )}
            </div>
          </div>
        </InfoCard>
      </div>

      <InfoCard title="采集日志时间线">
        <div className="space-y-4">
          {importLogs.map((log, index) => (
            <div key={`${log.time}-${index}`} className="grid grid-cols-[110px_24px_1fr] gap-4">
              <div className="pt-1 text-sm font-medium text-slate-500">{log.time}</div>
              <div className="flex flex-col items-center">
                <div className="h-3 w-3 rounded-full bg-blue-700" />
                {index !== importLogs.length - 1 && <div className="mt-2 h-full w-px bg-slate-300" />}
              </div>
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <div className="text-base font-semibold text-slate-900">{log.title}</div>
                <div className="mt-2 text-sm leading-7 text-slate-600">{log.detail}</div>
              </div>
            </div>
          ))}
        </div>
      </InfoCard>
    </div>
  );
}
