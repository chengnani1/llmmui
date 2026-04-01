/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0f172a",
        mist: "#f8fafc",
        panel: "#ffffff",
        accent: "#1d4ed8",
        accentSoft: "#dbeafe",
        line: "#cbd5e1",
        success: "#047857",
        warning: "#b45309",
        danger: "#b91c1c",
      },
      boxShadow: {
        panel: "0 20px 45px -24px rgba(15, 23, 42, 0.35)",
      },
      fontFamily: {
        sans: ["PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "sans-serif"],
      },
      backgroundImage: {
        grid: "linear-gradient(to right, rgba(148,163,184,0.12) 1px, transparent 1px), linear-gradient(to bottom, rgba(148,163,184,0.12) 1px, transparent 1px)",
      },
    },
  },
  plugins: [],
};
