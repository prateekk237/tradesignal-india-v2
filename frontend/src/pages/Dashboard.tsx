import { useQuery } from '@tanstack/react-query';
import { fetchLatestSummary, fetchMarketSentiment } from '@/api/client';
import { TrendingUp, TrendingDown, BarChart3, Zap, Target, ShieldAlert } from 'lucide-react';
import { cn, confidenceColor, signalBg, sentimentEmoji, formatINR } from '@/lib/utils';
import { useAppStore } from '@/store/useAppStore';

function MetricCard({ label, value, sub, icon: Icon, color }: {
  label: string; value: string; sub?: string; icon: any; color?: string;
}) {
  return (
    <div className="glass-card p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[11px] text-white/40 uppercase tracking-wider font-medium">{label}</span>
        <Icon className={cn('w-4 h-4', color || 'text-white/20')} />
      </div>
      <div className={cn('font-mono font-bold text-xl', color || 'text-white')}>{value}</div>
      {sub && <div className="text-[11px] text-white/40 mt-1">{sub}</div>}
    </div>
  );
}

export default function Dashboard() {
  const { scanResults, scanSummary } = useAppStore();
  const { data: sentiment } = useQuery({ queryKey: ['marketSentiment'], queryFn: fetchMarketSentiment, retry: false });
  const { data: latest } = useQuery({ queryKey: ['latestSummary'], queryFn: fetchLatestSummary, retry: false });

  const buySignals = scanResults.filter(r => r.final_signal?.includes('BUY'));
  const topPicks = buySignals.slice(0, 5);

  const marketMood = sentiment?.market_sentiment?.overall_sentiment || 'NO DATA';
  const sentimentScore = sentiment?.market_sentiment?.sentiment_score || 0;

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Hero Metrics */}
      <div className="grid grid-cols-4 gap-4">
        <MetricCard
          label="Market Mood"
          value={`${sentimentEmoji(marketMood)} ${marketMood.replace('_', ' ')}`}
          sub={`Score: ${sentimentScore}`}
          icon={BarChart3}
          color={sentimentScore > 0 ? 'text-accent-green' : sentimentScore < 0 ? 'text-accent-red' : 'text-accent-amber'}
        />
        <MetricCard
          label="Buy Signals"
          value={`${latest?.buy_signals || buySignals.length}`}
          sub={`of ${latest?.total_analyzed || scanResults.length} scanned`}
          icon={Zap}
          color="text-accent-cyan"
        />
        <MetricCard
          label="Top Confidence"
          value={topPicks.length > 0 ? `${topPicks[0].final_confidence}%` : '—'}
          sub={topPicks.length > 0 ? topPicks[0].name : 'Run a scan first'}
          icon={Target}
          color="text-accent-green"
        />
        <MetricCard
          label="Avg Confidence"
          value={latest?.avg_confidence ? `${latest.avg_confidence}%` : '—'}
          sub={scanSummary ? `Mode: ${scanSummary.mode}` : 'No scan data'}
          icon={TrendingUp}
          color="text-accent-purple"
        />
      </div>

      {/* Signals + Info */}
      <div className="grid grid-cols-3 gap-6">
        {/* Top Signals */}
        <div className="col-span-2 space-y-3">
          <h3 className="font-display font-semibold text-sm text-white/70">Top Signals This Week</h3>
          {topPicks.length === 0 ? (
            <div className="glass-card p-8 text-center">
              <ScanSearch className="w-10 h-10 mx-auto text-white/20 mb-3" />
              <p className="text-white/40 text-sm">No signals yet. Go to <span className="text-accent-cyan">Scanner</span> to run a market scan.</p>
            </div>
          ) : (
            topPicks.map((sig, i) => (
              <div key={sig.ticker} className={cn(signalBg(sig.final_signal), 'p-4 animate-slide-up')} style={{ animationDelay: `${i * 80}ms` }}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span className="font-mono font-bold text-sm text-white">{sig.ticker.replace('.NS', '')}</span>
                    <span className="text-white/50 text-xs">{sig.name}</span>
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-white/[0.06] text-white/40">{sig.sector} • {sig.cap}</span>
                  </div>
                  <div className="text-right">
                    <span className={cn('font-mono font-bold text-lg', confidenceColor(sig.final_confidence))}>{sig.final_confidence}%</span>
                    <div className="text-[10px] text-white/40">{sig.final_signal}</div>
                  </div>
                </div>
                <div className="grid grid-cols-5 gap-4 mt-3 text-xs">
                  <div>
                    <span className="text-white/40">Price</span>
                    <div className="font-mono text-white">{formatINR(sig.current_price)}</div>
                  </div>
                  <div>
                    <span className="text-white/40">Entry</span>
                    <div className="font-mono text-accent-cyan">{sig.entry_exit?.entry_price ? formatINR(sig.entry_exit.entry_price) : '—'}</div>
                  </div>
                  <div>
                    <span className="text-white/40">Target</span>
                    <div className="font-mono text-accent-green">{sig.entry_exit?.target_price ? formatINR(sig.entry_exit.target_price) : '—'}</div>
                  </div>
                  <div>
                    <span className="text-white/40">Stop Loss</span>
                    <div className="font-mono text-accent-red">{sig.entry_exit?.stop_loss ? formatINR(sig.entry_exit.stop_loss) : '—'}</div>
                  </div>
                  <div>
                    <span className="text-white/40">R:R</span>
                    <div className="font-mono text-white">{sig.entry_exit?.risk_reward?.toFixed(1) || '—'}</div>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Sector Distribution */}
        <div className="space-y-3">
          <h3 className="font-display font-semibold text-sm text-white/70">Sector Strength</h3>
          {latest?.sector_distribution ? (
            <div className="glass-card p-4 space-y-2">
              {Object.entries(latest.sector_distribution as Record<string, number>).slice(0, 8).map(([sector, count]) => (
                <div key={sector} className="flex items-center justify-between">
                  <span className="text-xs text-white/60">{sector}</span>
                  <div className="flex items-center gap-2">
                    <div className="w-20 h-1.5 bg-white/[0.06] rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-accent-purple to-accent-cyan"
                        style={{ width: `${Math.min(100, (count as number) * 20)}%` }}
                      />
                    </div>
                    <span className="font-mono text-[11px] text-white/50 w-4 text-right">{count as number}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="glass-card p-6 text-center text-white/30 text-xs">Scan first to see sector data</div>
          )}

          {/* Quick Stats */}
          <div className="glass-card p-4">
            <h4 className="text-[11px] text-white/40 uppercase tracking-wider mb-3">System Status</h4>
            <div className="space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-white/50">LLM Sentiment</span>
                <span className="font-mono text-accent-green">Active</span>
              </div>
              <div className="flex justify-between">
                <span className="text-white/50">News Sources</span>
                <span className="font-mono text-white/70">8 RSS feeds</span>
              </div>
              <div className="flex justify-between">
                <span className="text-white/50">Indicators</span>
                <span className="font-mono text-white/70">15 categories</span>
              </div>
              <div className="flex justify-between">
                <span className="text-white/50">Stock Universe</span>
                <span className="font-mono text-white/70">130 NSE</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// Used in empty state
function ScanSearch(props: any) {
  return <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...props}><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/><path d="M11 8v6"/><path d="M8 11h6"/></svg>;
}
