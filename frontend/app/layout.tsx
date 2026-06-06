import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'AURUM-X — Institutional Gold Intelligence',
  description: 'Real-time gold macro intelligence platform powered by Claude AI',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
