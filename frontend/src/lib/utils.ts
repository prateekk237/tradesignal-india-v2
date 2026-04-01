import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatINR(value: number): string {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency', currency: 'INR', maximumFractionDigits: 2,
  }).format(value);
}

export function formatCompact(value: number): string {
  if (value >= 10000000) return `₹${(value / 10000000).toFixed(1)}Cr`;
  if (value >= 100000) return `₹${(value / 100000).toFixed(1)}L`;
  if (value >= 1000) return `₹${(value / 1000).toFixed(1)}K`;
  return `₹${value.toFixed(0)}`;
}

export function signalColor(signal: string): string {
  if (signal.includes('STRONG BUY')) return 'text-accent-green metric-glow-green';
  if (signal.includes('BUY')) return 'text-accent-green';
  if (signal.includes('SELL')) return 'text-accent-red';
  return 'text-accent-amber';
}

export function signalBg(signal: string): string {
  if (signal.includes('BUY')) return 'signal-buy';
  if (signal.includes('SELL')) return 'signal-sell';
  return 'signal-hold';
}

export function confidenceColor(conf: number): string {
  if (conf >= 80) return 'text-accent-green';
  if (conf >= 65) return 'text-accent-cyan';
  if (conf >= 50) return 'text-accent-amber';
  return 'text-accent-red';
}

export function sentimentEmoji(sentiment: string): string {
  const s = sentiment.toUpperCase();
  if (s.includes('VERY_BULLISH') || s.includes('STRONG')) return '🟢🟢';
  if (s.includes('BULLISH') || s.includes('POSITIVE')) return '🟢';
  if (s.includes('VERY_BEARISH')) return '🔴🔴';
  if (s.includes('BEARISH') || s.includes('NEGATIVE')) return '🔴';
  return '🟡';
}
