/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        card: "var(--card)",
        soft: "var(--soft)",
        text: "var(--text)",
        muted: "var(--muted)",
        line: "var(--border)",
        primary: "var(--primary)",
        "primary-2": "var(--primary-2)",
        "primary-soft": "var(--primary-soft)",
        ring2: "var(--ring)",
      },
      borderRadius: {
        xl2: "18px",
        xl3: "22px",
      },
      boxShadow: {
        soft: "var(--shadow)",
        lg2: "var(--shadow-lg)",
        glow: "0 14px 34px rgba(37,99,235,.35)",
      },
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          "system-ui",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "none" },
        },
      },
      animation: {
        "fade-up": "fade-up .24s ease",
      },
    },
  },
  plugins: [],
};
