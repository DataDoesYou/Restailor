import type { Config } from "tailwindcss";
import typography from "@tailwindcss/typography";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./pages/**/*.{ts,tsx}",
    "./src/**/*.{ts,tsx}"
  ],
  theme: {
    container: {
      center: true,
      padding: "1rem"
    },
    extend: {
      boxShadow: {
        sm: "0 1px 0 rgba(0,0,0,0.10)",
        DEFAULT: "0 1px 2px rgba(0,0,0,0.16)",
        md: "0 2px 4px rgba(0,0,0,0.18)",
        lg: "0 4px 8px rgba(0,0,0,0.20)",
        xl: "0 8px 16px rgba(0,0,0,0.22)",
        none: "none",
      },
      borderColor: {
        DEFAULT: "hsl(220 8% 22%)",
      },
      spacing: {
        3.5: "0.875rem",
        5.5: "1.375rem",
        7: "1.75rem",
      },
      ringColor: {
        DEFAULT: "hsl(210 100% 56%)",
      },
      ringOffsetColor: {
        DEFAULT: "transparent",
      },
      colors: {
        surface: {
          DEFAULT: "hsl(220 13% 10%)",
          light: "hsl(220 13% 98%)",
        },
        outline: "hsl(220 8% 22%)",
        subtle: "hsl(220 10% 16%)",
      },
    }
  },
  plugins: [typography]
};

export default config;
