import { useState, useMemo } from 'react';
import { useAppStore } from '@/store/useAppStore';
import { cn, confidenceColor, formatINR, sentimentEmoji } from '@/lib/utils';
import { ArrowUpDown, Filter } from 'lucide-react';

type SortKey = 'final_confidence' | 'current_price' | 'sector' | 'name';

export default function Screener() {
  const { scanResults } = useAppStore();
  const [signalFilter, setSignalFilter] = useState<string[]>(['STRONG BUY', 'BUY']);
  const [capFilter, setCapFilter] = useState<string[]>(['Large', 'Mid', 'Small']);
  const [sortKey, setSortKey] = useState<SortKey>('final_confidence');
  const [sortAsc, setSortAsc] = useState(false);
  const [search, setSearch] = useState('');

  const filtered = useMemo(() => {
    let data = scanResults.filter(r =>
      signalFilter.some(s => r.final_signal?.includes(s)) &&
      capFilter.includes(r.cap) &&
      (search === '' || r.name.toLowerCase().includes(search.toLowerCase()) || r.ticker.toLowerCase().includes(search.toLowerCase()))
    );
    data.sort((a, b) => {
      const av = a[sortKey] ?? 0;
      const bv = b[sortKey] ?? 0;
      if (typeof av === 'string') return sortAsc ? (av as string).localeCompare(bv as string) : (bv as string).localeCompare(av as string);
      return sortAsc ? (av as number) - (bv as number) : (bv as number) - (av as number);
    });
    return data;
  }, [scanResults, signalFilter, capFilter, sortKey, sortAsc, search]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortAsc(!sortAsc);
    else { setSortKey(key); setSortAsc(false); }
  };

  const signalOptions = ['STRONG BUY', 'BUY', 'HOLD / NEUTRAL', 'SELL', 'STRONG SELL'];
  const capOptions = ['Large', 'Mid', 'Small'];

  if (scanResults.length === 0) {
    return (
      <div className="glass-card p-12 text-center animate-fade-in">
        <Filter className="w-12 h-12 mx-auto text-white/10 mb-4" />
        <p className="text-white/40 text-sm">No data available. Run a scan first.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4 animate-fade-in">
      {/* Filters */}
      <div className="glass-card p-4 flex items-center gap-6">
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-white/40 uppercase">Signal:</span>
          {signalOptions.map(s => (
            <button key={s} onClick={() => setSignalFilter(prev => prev.includes(s) ? prev.filter(x => x !== s) : [...prev, s])}
              className={cn('text-[10px] px-2 py-1 rounded-md border transition-all', signalFilter.includes(s) ? 'border-accent-purple/50 bg-accent-purple/10 text-accent-purple' : 'border-white/[0.06] text-white/30 hover:text-white/50')}>
              {s}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-white/40 uppercase">Cap:</span>
          {capOptions.map(c => (
            <button key={c} onClick={() => setCapFilter(prev => prev.includes(c) ? prev.filter(x => x !== c) : [...prev, c])}
              className={cn('text-[10px] px-2 py-1 rounded-md border transition-all', capFilter.includes(c) ? 'border-accent-cyan/50 bg-accent-cyan/10 text-accent-cyan' : 'border-white/[0.06] text-white/30')}>
              {c}
            </button>
          ))}
        </div>
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search ticker or name..."
          className="ml-auto bg-white/[0.04] border border-white/[0.08] rounded-lg px-3 py-1.5 text-xs text-white w-48 focus:outline-none focus:border-accent-purple" />
      </div>

      <div className="text-[11px] text-white/30 px-1">Showing {filtered.length} of {scanResults.length} stocks</div>

      {/* Table */}
      <div className="glass-card overflow-hidden">
        <div className="max-h-[600px] overflow-auto">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-surface-2 z-10">
              <tr className="border-b border-white/[0.08]">
                {[
                  { key: 'name' as SortKey, label: 'Stock' },
                  { key: null, label: 'Sector' },
                  { key: null, label: 'Cap' },
                  { key: 'current_price' as SortKey, label: 'Price' },
                  { key: 'final_confidence' as SortKey, label: 'Confidence' },
                  { key: null, label: 'Signal' },
                  { key: null, label: 'RSI' },
                  { key: null, label: 'MACD' },
                  { key: null, label: 'Vol Ratio' },
                  { key: null, label: 'News' },
                ].map((h, i) => (
                  <th key={i} className="px-3 py-2.5 text-left text-[10px] text-white/40 uppercase tracking-wider font-medium">
                    {h.key ? (
                      <button onClick={() => toggleSort(h.key!)} className="flex items-center gap-1 hover:text-white/70 transition-colors">
                        {h.label} <ArrowUpDown className="w-2.5 h-2.5" />
                      </button>
                    ) : h.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((r, i) => (
                <tr key={r.ticker} className="border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors">
                  <td className="px-3 py-2.5">
                    <span className="font-mono font-bold text-white">{r.ticker.replace('.NS', '')}</span>
                    <span className="text-white/30 ml-1.5">{r.name}</span>
                  </td>
                  <td className="px-3 py-2.5 text-white/50">{r.sector}</td>
                  <td className="px-3 py-2.5 text-white/50">{r.cap}</td>
                  <td className="px-3 py-2.5 font-mono text-white">{formatINR(r.current_price)}</td>
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-2">
                      <div className="w-14 h-1.5 bg-white/[0.06] rounded-full overflow-hidden">
                        <div className={cn('h-full rounded-full', r.final_confidence >= 65 ? 'bg-accent-green' : r.final_confidence >= 45 ? 'bg-accent-amber' : 'bg-accent-red')}
                          style={{ width: `${r.final_confidence}%` }} />
                      </div>
                      <span className={cn('font-mono font-bold', confidenceColor(r.final_confidence))}>{r.final_confidence}%</span>
                    </div>
                  </td>
                  <td className="px-3 py-2.5">
                    <span className={cn('text-[10px] font-medium px-2 py-0.5 rounded-full',
                      r.final_signal?.includes('STRONG BUY') ? 'bg-accent-green/15 text-accent-green' :
                      r.final_signal?.includes('BUY') ? 'bg-accent-green/10 text-accent-green/80' :
                      r.final_signal?.includes('SELL') ? 'bg-accent-red/10 text-accent-red' :
                      'bg-accent-amber/10 text-accent-amber'
                    )}>{r.final_signal}</span>
                  </td>
                  <td className="px-3 py-2.5 font-mono text-white/60">{r.technical_details?.rsi || '—'}</td>
                  <td className="px-3 py-2.5 font-mono text-white/60">{r.technical_details?.macd_hist?.toFixed(2) || '—'}</td>
                  <td className="px-3 py-2.5 font-mono text-white/60">{r.technical_details?.vol_ratio?.toFixed(1) || '—'}x</td>
                  <td className="px-3 py-2.5 text-xs">
                    {sentimentEmoji(r.news_sentiment?.sentiment || '')} {r.news_sentiment?.article_count || 0}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
