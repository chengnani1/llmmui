import InfoCard from "../components/InfoCard";
import StatusBadge from "../components/StatusBadge";
import { chainSteps, permissionEvents, semanticCards } from "../mock/data";

export default function AnalysisPage() {
  return (
    <div className="space-y-6">
      <InfoCard
        title="任务信息"
        extra={<button className="btn-secondary">切换任务</button>}
      >
        <div className="grid grid-cols-4 gap-4 text-sm">
          {[
            ["任务编号", "TASK-20260401-001"],
            ["应用名称", "示例出行应用"],
            ["分析模式", "交互链语义分析"],
            ["当前状态", "已完成"],
          ].map(([label, value]) => (
            <div key={label} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="text-slate-500">{label}</div>
              <div className="mt-2 font-semibold text-slate-800">
                {label === "当前状态" ? <StatusBadge text={value} /> : value}
              </div>
            </div>
          ))}
        </div>
      </InfoCard>

      <div className="grid grid-cols-[0.8fr_1.2fr_0.95fr] gap-6">
        <InfoCard title="权限事件列表">
          <div className="space-y-3">
            {permissionEvents.map((event) => (
              <div key={event.id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-semibold text-slate-900">{event.name}</div>
                  <StatusBadge text={event.severity} />
                </div>
                <div className="mt-2 text-xs uppercase tracking-[0.18em] text-slate-400">{event.id}</div>
                <div className="mt-3 text-sm text-slate-600">{event.permission}</div>
              </div>
            ))}
          </div>
        </InfoCard>

        <InfoCard title="交互链步骤流">
          <div className="space-y-4">
            {chainSteps.map((step, index) => (
              <div key={step.step} className="grid grid-cols-[52px_1fr] gap-4">
                <div className="flex flex-col items-center">
                  <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-blue-700 text-sm font-semibold text-white">
                    {step.step}
                  </div>
                  {index !== chainSteps.length - 1 && <div className="mt-2 h-full w-px bg-slate-300" />}
                </div>
                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <div className="flex items-center justify-between">
                    <div className="text-base font-semibold text-slate-900">{step.page}</div>
                    <div className="text-sm text-slate-500">{step.permission}</div>
                  </div>
                  <div className="mt-2 text-sm text-slate-600">操作类型：{step.action}</div>
                  <div className="mt-2 text-sm leading-7 text-slate-500">{step.note}</div>
                </div>
              </div>
            ))}
          </div>
        </InfoCard>

        <InfoCard title="语义分析结果卡片">
          <div className="space-y-4">
            {semanticCards.map((card) => (
              <div key={card.title} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <div className="text-sm font-semibold text-slate-900">{card.title}</div>
                <div className="mt-3 text-sm leading-7 text-slate-600">{card.content}</div>
              </div>
            ))}
          </div>
        </InfoCard>
      </div>
    </div>
  );
}
