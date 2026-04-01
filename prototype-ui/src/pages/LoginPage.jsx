import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";

export default function LoginPage({ onLogin, isLoggedIn }) {
  const [form, setForm] = useState({ username: "张研究员", password: "123456" });
  const [timeText, setTimeText] = useState("");

  useEffect(() => {
    const update = () => {
      setTimeText(
        new Intl.DateTimeFormat("zh-CN", {
          dateStyle: "full",
          timeStyle: "medium",
        }).format(new Date()),
      );
    };
    update();
    const timer = window.setInterval(update, 1000);
    return () => window.clearInterval(timer);
  }, []);

  if (isLoggedIn) {
    return <Navigate to="/" replace />;
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[radial-gradient(circle_at_top,rgba(29,78,216,0.15),transparent_28%),linear-gradient(180deg,#f8fafc,#e2e8f0)] px-8">
      <div className="grid w-full max-w-6xl grid-cols-[1.1fr_0.9fr] gap-8">
        <section className="panel relative overflow-hidden p-10">
          <div className="absolute inset-x-0 top-0 h-2 bg-gradient-to-r from-blue-700 via-cyan-500 to-emerald-500" />
          <div className="text-sm uppercase tracking-[0.35em] text-slate-400">Research Console</div>
          <h1 className="mt-6 max-w-2xl text-5xl font-semibold leading-[1.25] text-slate-900">
            Android应用权限交互链智能合规分析系统
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-600">
            系统面向 Android 应用权限交互链采集、语义分析与合规判断场景，提供统一的任务接入、过程审查与结果展示界面。
          </p>
          <div className="mt-10 grid grid-cols-3 gap-4">
            {[
              ["交互链采集", "采集页面事件、权限弹窗与用户路径"],
              ["语义判定", "关联用户任务、页面功能与权限用途"],
              ["结果管理", "形成表格化风险记录与历史归档"],
            ].map(([title, desc]) => (
              <div key={title} className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
                <div className="text-base font-semibold text-slate-900">{title}</div>
                <div className="mt-2 text-sm leading-6 text-slate-500">{desc}</div>
              </div>
            ))}
          </div>
          <div className="mt-10 rounded-2xl border border-slate-200 bg-white p-5">
            <div className="text-sm text-slate-500">当前演示时间</div>
            <div className="mt-2 text-base font-medium text-slate-800">{timeText}</div>
          </div>
        </section>

        <section className="panel flex items-center p-8">
          <form
            className="w-full"
            onSubmit={(event) => {
              event.preventDefault();
              onLogin(form.username);
            }}
          >
            <div className="text-sm uppercase tracking-[0.25em] text-slate-400">User Access</div>
            <h2 className="mt-4 text-3xl font-semibold text-slate-900">系统登录</h2>
            <p className="mt-3 text-sm leading-6 text-slate-500">
              本原型为前端 mock 演示环境，输入任意用户名和密码后即可进入系统。
            </p>
            <div className="mt-8 space-y-5">
              <div>
                <label className="mb-2 block text-sm font-medium text-slate-700">用户名</label>
                <input
                  className="input"
                  value={form.username}
                  onChange={(event) => setForm((prev) => ({ ...prev, username: event.target.value }))}
                  placeholder="请输入用户名"
                />
              </div>
              <div>
                <label className="mb-2 block text-sm font-medium text-slate-700">密码</label>
                <input
                  className="input"
                  type="password"
                  value={form.password}
                  onChange={(event) => setForm((prev) => ({ ...prev, password: event.target.value }))}
                  placeholder="请输入密码"
                />
              </div>
            </div>
            <button type="submit" className="btn-primary mt-8 w-full">
              登录系统
            </button>
            <div className="mt-4 text-center text-sm text-slate-500">
              建议用于软件著作权说明书、系统展示与界面截图。
            </div>
          </form>
        </section>
      </div>
    </div>
  );
}
