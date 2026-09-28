import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}", "./pages/**/*.{ts,tsx}", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        "proxy-black": "var(--proxy-black)",
        "proxy-text": "var(--proxy-text)",
        "proxy-muted": "var(--proxy-muted)",
        "proxy-tertiary": "var(--proxy-tertiary)",
        "proxy-cyan": "var(--proxy-cyan)",
        "proxy-purple": "var(--proxy-purple)",
        "proxy-green": "var(--proxy-green)",
        "proxy-amber": "var(--proxy-amber)",
        "proxy-red": "var(--proxy-red)",
        glass: "var(--proxy-glass)",
      },
      boxShadow: {
        "glow-cyan": "0 0 0 1px rgba(0,229,255,.28), 0 0 28px rgba(0,229,255,.24)",
        "glow-purple": "0 0 0 1px rgba(155,92,255,.26), 0 0 34px rgba(155,92,255,.22)",
        "glow-green": "0 0 0 1px rgba(55,242,154,.22), 0 0 24px rgba(55,242,154,.18)",
      },
    },
  },
  plugins: [],
};

export default config;
