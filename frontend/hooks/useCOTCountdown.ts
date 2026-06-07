'use client'
import { useState, useEffect } from 'react'

export interface COTCountdownState {
  nextReleaseUTC: Date
  minutesUntil: number
  hoursUntil: number
  daysUntil: number
  isToday: boolean
  isImminent: boolean      // within 30 minutes
  isLive: boolean          // within 5 minutes of release
  justReleased: boolean    // within 60 minutes after release
  formattedCountdown: string
  localTimeString: string  // user's local timezone display (Europe/London = UTC+1 in summer)
  dayLabel: string
}

// CFTC COT data is released every Friday at 3:30pm ET == 20:30 UTC (summer) / 21:30 UTC+1 London
function getNextCOTRelease(): Date {
  const now = new Date()
  const next = new Date(now)
  const dayOfWeek = now.getUTCDay() // 0=Sun ... 5=Fri ... 6=Sat
  const daysUntilFriday = (5 - dayOfWeek + 7) % 7

  if (daysUntilFriday === 0) {
    const todayRelease = new Date(now)
    todayRelease.setUTCHours(20, 30, 0, 0)
    if (now < todayRelease) {
      return todayRelease
    } else {
      next.setUTCDate(next.getUTCDate() + 7)
    }
  } else {
    next.setUTCDate(next.getUTCDate() + daysUntilFriday)
  }

  next.setUTCHours(20, 30, 0, 0)
  return next
}

function compute(): COTCountdownState {
  const now = new Date()
  const next = getNextCOTRelease()
  const diffMs = next.getTime() - now.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMins / 60)
  const diffDays = Math.floor(diffHours / 24)

  const isToday = diffDays === 0 && diffMins >= 0
  const isImminent = diffMins <= 30 && diffMins >= 0
  const isLive = diffMins <= 5 && diffMins >= -5
  const justReleased = diffMins >= -60 && diffMins < -5

  let formattedCountdown = ''
  if (isLive) {
    formattedCountdown = '● RELEASING NOW'
  } else if (justReleased) {
    formattedCountdown = '● DATA RELEASED'
  } else if (diffDays > 1) {
    formattedCountdown = `${diffDays}D ${diffHours % 24}H`
  } else if (diffHours > 0) {
    formattedCountdown = `${diffHours}H ${diffMins % 60}M`
  } else {
    formattedCountdown = `${Math.max(diffMins, 0)}M`
  }

  const localTime = next.toLocaleTimeString('en-GB', {
    hour: '2-digit', minute: '2-digit', timeZone: 'Europe/London',
  })
  const localDate = next.toLocaleDateString('en-GB', {
    weekday: 'short', day: '2-digit', month: 'short', timeZone: 'Europe/London',
  })

  const dayLabel = isToday ? 'TODAY' : diffDays === 1 ? 'TOMORROW' : localDate

  return {
    nextReleaseUTC: next,
    minutesUntil: diffMins,
    hoursUntil: diffHours,
    daysUntil: diffDays,
    isToday, isImminent, isLive, justReleased,
    formattedCountdown,
    localTimeString: localTime,
    dayLabel,
  }
}

export function useCOTCountdown(): COTCountdownState {
  const [state, setState] = useState<COTCountdownState>(() => compute())

  useEffect(() => {
    const tick = () => setState(compute())
    const interval = setInterval(tick, state.isImminent || state.isLive ? 1000 : 30000)
    return () => clearInterval(interval)
  }, [state.isImminent, state.isLive])

  return state
}
