/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0b0b0c",
        panel: "#141416",
        line: "#2a2a2e",
        brand: {
          DEFAULT: "#f5a018",
          dim: "#c47d0c",
          fg: "#0b0b0c",
        },
        tg: "#08b508",
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(245, 160, 24, 0.25), 0 18px 40px rgba(0,0,0,.45)",
      },
    },
  },
  plugins: [],
};
