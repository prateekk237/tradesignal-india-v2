import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { allocatePortfolio } from '@/api/client';
import { useAppStore } from '@/store/useAppStore';
import { cn, formatINR, confidenceColor } from '@/lib/utils';
import { PieChart, Copy, Check } from 'lucide-react';
import type { Allocation } from '@/lib/types';

export default function Portfolio() {
  const { scanResults, capital, minConfidence, maxPositions } = useAppStore();
  const [allocations, setAllocations] = useState<Allocation[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [copied, setCopied] = useState(false);

  const buySignals = scanResults.filter(r => r.final_signal?.includes('BUY') && r.final_confidence >= minConfidence);

  const allocMutation = useMutation({
    mutationFn: () => allocatePortfolio(capital, buySignals, maxPositions, minConfidence),
    onSuccess: (data) => {
      setAllocations(data.allocations);
      setSummary(data);
    },
  });

  const copyOrderSheet = () => {
    const text = allocations.map(a =>
      `BUY  ${a.ticker.replace('.NS', '').padEnd(15)} | Qty: ${String(a.shares).padStart(4)} | Entry: ₹${a.price.toFixed(2).padStart(10)} | Target: ₹${(a.target || 0).toFixed(2).padStart(10)} | SL: ₹${(a.stop_loss || 0).toFixed(2).padStart(10)}`
    ).join('\n');
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-display font-semibold text-lg text-white/90">Portfolio Allocation</h3>
          <p className="text-xs text-white/40 mt-1">Capital: {formatINR(capital)} • Max {maxPositions} positions • {buySignals.length} candidates</p>
        </div>
        <button
          onClick={() => allocMutation.mutate()}
          disabled={buySignals.length === 0}
          className="btn-primary flex items-center gap-2 disabled:opacity-40"
        >
          <PieChart className="w-4 h-4" /> Compute Allocation
        </button>
      </div>

      {summary && (
        <>
          {/* Summary Metrics */}
          <div className="grid grid-cols-4 gap-4">
            {[
              { label: 'Invested', value: formatINR(summary.total_invested), color: 'text-accent-cyan' },
              { label: 'Cash Reserve', value: formatINR(summary.cash_reserve), color: 'text-accent-amber' },
              { label: 'Positions', value: summary.positions, color: 'text-white' },
              { label: 'Max Positions', value: maxPositions, color: 'text-white/50' },
            ].map(m => (
              <div key={m.label} className="glass-card p-4 text-center">
                <div className="text-[10px] text-white/40 uppercase">{m.label}</div>
                <div className={cn('font-mono font-bold text-xl mt-1', m.color)}>{m.value}</div>
              </div>
            ))}
          </div>

          {/* Allocation Table */}
          <div className="glass-card overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/[0.06]">
                  {['Stock', 'Sector', 'Price', 'Shares', 'Amount', 'Alloc%', 'Target', 'Stop Loss', 'Confidence'].map(h => (
                    <th key={h} className="px-4 py-3 text-[10px] text-white/40 uppercase tracking-wider text-left font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {allocations.map((a, i) => (
                  <tr key={a.ticker} className="border-b border-white/[0.04] hover:bg-white/[0.02] transition-colors animate-slide-up" style={{ animationDelay: `${i * 50}ms` }}>
                    <td className="px-4 py-3">
                      <span className="font-mono font-bold text-xs">{a.ticker.replace('.NS', '')}</span>
                      <span className="text-white/40 text-xs ml-2">{a.name}</span>
                    </td>
                    <td className="px-4 py-3 text-white/50 text-xs">—</td>
                    <td className="px-4 py-3 font-mono text-xs">{formatINR(a.price)}</td>
                    <td className="px-4 py-3 font-mono text-xs text-accent-cyan">{a.shares}</td>
                    <td className="px-4 py-3 font-mono text-xs">{formatINR(a.amount)}</td>
                    <td className="px-4 py-3 font-mono text-xs text-accent-purple">{a.allocation_pct}%</td>
                    <td className="px-4 py-3 font-mono text-xs text-accent-green">{a.target ? formatINR(a.target) : '—'}</td>
                    <td className="px-4 py-3 font-mono text-xs text-accent-red">{a.stop_loss ? formatINR(a.stop_loss) : '—'}</td>
                    <td className="px-4 py-3">
                      <span className={cn('font-mono font-bold text-xs', confidenceColor(a.confidence))}>{a.confidence}%</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Order Sheet */}
          <div className="glass-card p-4">
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-sm font-display font-semibold text-white/70">Order Sheet</h4>
              <button onClick={copyOrderSheet} className="text-xs text-accent-cyan hover:text-white transition-colors flex items-center gap-1.5">
                {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                {copied ? 'Copied!' : 'Copy All'}
              </button>
            </div>
            <div className="space-y-1">
              {allocations.map(a => (
                <code key={a.ticker} className="block text-[11px] font-mono text-white/60 bg-white/[0.03] rounded px-3 py-1.5">
                  BUY  {a.ticker.replace('.NS', '').padEnd(15)} | Qty: {String(a.shares).padStart(4)} | Entry: ₹{a.price.toFixed(2).padStart(10)} | Target: ₹{(a.target || 0).toFixed(2).padStart(10)} | SL: ₹{(a.stop_loss || 0).toFixed(2).padStart(10)}
                </code>
              ))}
            </div>
          </div>
        </>
      )}

      {!summary && buySignals.length === 0 && (
        <div className="glass-card p-12 text-center">
          <PieChart className="w-12 h-12 mx-auto text-white/10 mb-4" />
          <p className="text-white/40 text-sm">No buy signals available. Run a market scan first.</p>
        </div>
      )}
    </div>
  );
}
