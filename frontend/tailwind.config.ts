import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        mono:    ["'JetBrains Mono'", 'monospace'],
        display: ["'Space Grotesk'",  'sans-serif'],
      },
      colors: {
        aurum: {
          base:    '#06070b',
          card:    '#0d0f17',
          primary: '#f00d17',
          amber:   '#ffb347',
          teal:    '#2dd4bf',
          pink:    '#ff4d7a',
          green:   '#22c55e',
          border:  'rgba(240,13,23,0.15)',
          muted:   '#4a5068',
          label:   '#6b7494',
        }
      },
      animation: {
        'glow-pulse':    'glowPulse 2s ease-in-out infinite',
        'card-mount':    'cardMount 0.4s ease-out forwards',
        'ticker-scroll': 'tickerScroll 30s linear infinite',
        'grid-drift':    'gridDrift 20s linear infinite',
        'chart-draw':    'chartDraw 2s ease-out forwards',
        'count-up':      'countUp 0.6s ease-out forwards',
        'prob-fill':     'probFill 1.2s ease-out forwards',
        'bar-expand':    'barExpand 0.8s ease-out forwards',
      },
      keyframes: {
        gridDrift:    { from: { backgroundPosition: '0 0' }, to: { backgroundPosition: '40px 40px' } },
        glowPulse:    { '0%,100%': { opacity: '1' }, '50%': { opacity: '0.3' } },
        countUp:      { from: { opacity: '0', transform: 'translateY(8px)' }, to: { opacity: '1', transform: 'translateY(0)' } },
        probFill:     { from: { width: '0%' } },
        barExpand:    { from: { width: '0' } },
        cardMount:    { from: { opacity: '0', transform: 'translateY(6px)' }, to: { opacity: '1', transform: 'translateY(0)' } },
        chartDraw:    { from: { clipPath: 'inset(0 100% 0 0)' }, to: { clipPath: 'inset(0 0% 0 0)' } },
        tickerScroll: { from: { transform: 'translateY(0)' }, to: { transform: 'translateY(-50%)' } },
      },
      boxShadow: {
        glow:    '0 0 30px rgba(180,20,0,0.12)',
        'glow-text': '0 0 12px rgba(255,80,0,0.8), 0 0 30px rgba(255,40,0,0.4)',
      },
      borderRadius: {
        none: '0px',
      },
    },
  },
  plugins: [],
}

export default config
