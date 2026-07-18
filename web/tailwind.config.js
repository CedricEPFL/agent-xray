/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{js,ts,jsx,tsx}", "./components/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["IBM Plex Mono", "SFMono-Regular", "Consolas", "monospace"],
      },
      colors: {
        ink: "#080b10",
        panel: "#0e131b",
        line: "#243040",
        cyan: "#58d7e8",
        lime: "#a6e36f",
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(88,215,232,.08), 0 20px 70px rgba(0,0,0,.28)",
      },
    },
  },
  plugins: [],
};
