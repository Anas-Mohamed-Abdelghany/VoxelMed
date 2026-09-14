/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        'med-dark': '#0a0a0f',
        'med-panel': '#12121a',
        'med-border': '#2a2a3a',
        'med-accent': '#3b82f6',
        'med-accent-hover': '#2563eb',
        'med-text': '#e2e8f0',
        'med-text-dim': '#94a3b8',
      },
    },
  },
  plugins: [],
};
