/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{js,ts,jsx,tsx}", "./components/**/*.{js,ts,jsx,tsx}", "./features/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#F3EFE8",
        fg: "#1C1917",
        card: "#FFFFFF",
        muted: "#78716C",
        border: "rgba(28, 25, 23, 0.08)",
        accent: "#4F46E5",
        "accent-soft": "#EEF2FF",
        success: "#059669",
        warning: "#D97706",
        danger: "#DC2626",
        cream: "#F3EFE8",
        stone: {
          50: "#fafaf9",
          100: "#f5f5f4",
          200: "#e7e5e4",
          300: "#d6d3d1",
          400: "#a8a29e",
          500: "#78716c",
          600: "#57534e",
          700: "#44403c",
          800: "#292524",
          900: "#1c1917",
        },
      },
      fontFamily: {
        sans: ["var(--font-geist-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["var(--font-display)", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      boxShadow: {
        soft: "0 1px 2px rgba(28, 25, 23, 0.04)",
        lift: "0 10px 30px -18px rgba(28, 25, 23, 0.18)",
        card: "0 8px 24px -16px rgba(28, 25, 23, 0.14)",
        glow: "0 0 0 4px rgba(79, 70, 229, 0.12)",
      },
      borderRadius: {
        "2xl": "1rem",
        "3xl": "1.35rem",
      },
    },
  },
  plugins: [],
};
