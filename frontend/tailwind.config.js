/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        sentiment: {
          buy: '#22c55e',
          hold: '#eab308',
          sell: '#ef4444',
          mentioned: '#3b82f6',
        }
      }
    },
  },
  plugins: [],
}
