import { History, TrendingUp, TrendingDown } from 'lucide-react';

export default function TradeHistory() {
  return (
    <div className="space-y-6 animate-fade-in">
      <div className="glass-card p-12 text-center">
        <History className="w-16 h-16 mx-auto text-white/10 mb-4" />
        <h3 className="font-display font-semibold text-lg text-white/70 mb-2">Trade History & Analytics</h3>
        <p className="text-white/40 text-sm max-w-md mx-auto leading-relaxed">
          Full trade lifecycle tracking is coming in Sprint 6. This will include entry/exit log, 
          realized P&L, cumulative performance charts, win rate, and signal accuracy metrics.
        </p>
        <div className="grid grid-cols-3 gap-4 mt-8 max-w-lg mx-auto">
          {[
            { icon: TrendingUp, label: 'Win Rate', value: '—', color: 'text-accent-green' },
            { icon: TrendingDown, label: 'Avg P&L', value: '—', color: 'text-white/50' },
            { icon: History, label: 'Total Trades', value: '0', color: 'text-accent-cyan' },
          ].map(m => (
            <div key={m.label} className="glass-card p-4 text-center">
              <m.icon className={`w-5 h-5 mx-auto mb-2 ${m.color}`} />
              <div className="text-[10px] text-white/40 uppercase">{m.label}</div>
              <div className={`font-mono font-bold text-lg mt-1 ${m.color}`}>{m.value}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
