import { NavLink, Outlet } from "react-router-dom";

const navItems = [
  { to: "/", label: "首页" },
  { to: "/import", label: "应用导入" },
  { to: "/analysis", label: "交互链分析" },
  { to: "/results", label: "结果展示" },
  { to: "/history", label: "历史记录" },
];

export default function AppLayout({ currentUser }) {
  return (
    <div className="min-h-screen bg-grid bg-[size:36px_36px]">
      <div className="grid min-h-screen grid-cols-[260px_1fr]">
        <aside className="border-r border-slate-200 bg-slate-950 px-6 py-8 text-slate-100">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5">
            <div className="text-xs uppercase tracking-[0.3em] text-slate-400">Academic Prototype</div>
            <div className="mt-3 text-xl font-semibold leading-8">
              Android应用权限交互链智能合规分析系统
            </div>
            <div className="mt-3 text-sm leading-6 text-slate-400">
              面向应用权限触发场景、交互链采集与风险研判的前端原型界面。
            </div>
          </div>
          <nav className="mt-8 space-y-2">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  `block rounded-xl px-4 py-3 text-sm font-medium transition ${
                    isActive
                      ? "bg-blue-700 text-white"
                      : "text-slate-300 hover:bg-slate-900 hover:text-white"
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="mt-8 rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
            <div className="text-sm text-slate-400">当前状态</div>
            <div className="mt-2 text-lg font-semibold text-white">本地 Mock 演示环境</div>
            <div className="mt-2 text-sm leading-6 text-slate-400">
              所有数据均来自静态 mock 文件，可直接用于说明书截图与页面展示。
            </div>
          </div>
        </aside>
        <main className="overflow-hidden">
          <header className="flex h-24 items-center justify-between border-b border-slate-200 bg-white/80 px-8 backdrop-blur">
            <div>
              <div className="text-sm uppercase tracking-[0.25em] text-slate-400">System Console</div>
              <h1 className="mt-1 text-2xl font-semibold text-slate-900">
                Android应用权限交互链智能合规分析系统
              </h1>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-slate-50 px-5 py-3 text-right">
              <div className="text-xs uppercase tracking-[0.2em] text-slate-400">当前用户</div>
              <div className="mt-1 text-sm font-semibold text-slate-800">{currentUser}</div>
            </div>
          </header>
          <div className="h-[calc(100vh-6rem)] overflow-auto p-8">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
