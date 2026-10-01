/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './components/**/*.{vue,js,ts}',
    './layouts/**/*.vue',
    './pages/**/*.vue',
    './plugins/**/*.{js,ts}',
    './app.vue',
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#edf7f6',
          100: '#d3ece9',
          500: '#1c7c73',
          600: '#176860',
          700: '#11534c',
        },
      },
    },
  },
  plugins: [],
}
