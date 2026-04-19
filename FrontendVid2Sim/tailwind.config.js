/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#0A0A0C",
        surface: "#121216",
        surfaceHover: "#1A1A1E",
        primary: "#E46B45",      // Vibrant orange from Aligno inspiration
        primaryHover: "#FF8C66", 
        border: "rgba(255,255,255,0.05)",
        textPrimary: "#FFFFFF",
        textSecondary: "rgba(255,255,255,0.6)",
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      animation: {
        'pulse-slow': 'pulse 4s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'glow': 'glow 2s ease-in-out infinite alternate',
      },
      keyframes: {
        glow: {
          '0%': { boxShadow: '0 0 10px rgba(228, 107, 69, 0.2)' },
          '100%': { boxShadow: '0 0 20px rgba(228, 107, 69, 0.6), 0 0 40px rgba(228, 107, 69, 0.4)' },
        }
      }
    },
  },
  plugins: [],
}
