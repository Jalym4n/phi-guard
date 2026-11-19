/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: ["system-ui", "-apple-system", "Segoe UI", "Roboto", "Helvetica Neue", "Arial", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      keyframes: {
        flash: { "0%, 100%": { boxShadow: "0 0 0 0 rgba(0,0,0,0)" }, "30%": { boxShadow: "0 0 0 4px rgb(37 99 235)" } },
      },
      animation: { flash: "flash 1.2s ease-in-out 2" },
    },
  },
  plugins: [],
};
