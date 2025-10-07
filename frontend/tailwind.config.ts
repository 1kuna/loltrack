import type { Config } from 'tailwindcss'

export default {
  content: [
    './index.html',
    './src/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        accent: {
          DEFAULT: '#22d3ee', // cyan-400
        },
        ok: {
          DEFAULT: '#22c55e', // green-500
        },
        warn: {
          DEFAULT: '#f59e0b', // amber-500
        },
        bad: {
          DEFAULT: '#ef4444', // red-500
        },
      },
    },
  },
  plugins: [],
} satisfies Config

