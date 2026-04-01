import { useQuery } from '@tanstack/react-query';
import { fetchNews, fetchMarketSentiment } from '@/api/client';
import { cn } from '@/lib/utils';
import { Brain, ExternalLink, RefreshCw } from 'lucide-react';

function sentimentLabel(s: string): { text: string; color: string } {
  const u = (s || '').toUpperCase();
  if (u.includes('BULLISH') || u.includes('POSITIVE')) return { text: 'BULLISH', color: 'text-emerald-400' };
  if (u.includes('BEARISH') || u.includes('NEGATIVE')) return { text: 'BEARISH', color: 'text-red-400' };
  return { text: 'NEUTRAL', color: 'text-amber-400' };
}

export default function News() {
  const { data: newsData, isLoading, refetch: refetchNews } = useQuery({
    queryKey: ['news'], queryFn: () => fetchNews(60), refetchInterval: 300000,
  });
  const { data: sentiment, refetch: refetchSentiment } = useQuery({
    queryKey: ['marketSentiment'], queryFn: fetchMarketSentiment, refetchInterval: 300000,
  });

  const articles = newsData?.articles || [];
  const mktSent = sentiment?.market_sentiment;
  const score = mktSent?.sentiment_score || 0;
  const label = sentimentLabel(mktSent?.overall_sentiment || '');
  const source = mktSent?.source || 'N/A';

  return (
    <div className="space-y-4 animate-fade-in">
      {/* News Panel — screenshot-matching style */}
      <div className="glass-card overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-white/[0.06]">
          <div className="flex items-center gap-3">
            <div className="w-3 h-3 rounded-sm bg-white/20" />
            <span className="font-mono text-xs font-bold text-white/80 uppercase tracking-wider">News</span>
          </div>
          <button onClick={() => { refetchNews(); refetchSentiment(); }}
            className="text-white/30 hover:text-white/60 transition-colors" title="Refresh">
            <RefreshCw className={cn('w-3.5 h-3.5', isLoading && 'animate-spin')} />
          </button>
        </div>

        {/* Sentiment Score */}
        <div className="px-4 pt-3 pb-2">
          <span className={cn('font-mono text-2xl font-bold', score > 0 ? 'text-emerald-400' : score < 0 ? 'text-red-400' : 'text-amber-400')}>
            {score > 0 ? '+' : ''}{score.toFixed(3)}
          </span>
          <span className={cn('text-xs font-mono font-bold uppercase ml-2', label.color)}>{label.text}</span>
          <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-violet-500/15 text-violet-400 ml-2">
            {source === 'llm' ? 'AI' : source.toUpperCase()}
          </span>
        </div>

        {/* Articles */}
        <div className="px-4 pb-3 space-y-0 max-h-[calc(100vh-360px)] overflow-y-auto">
          {isLoading ? (
            <div className="py-8 text-center text-white/30 text-xs font-mono">Loading feeds...</div>
          ) : (
            articles.slice(0, 40).map((article: any, i: number) => {
              const artScore = article.sentiment_score || 0;
              const isPositive = artScore > -0.05;
              return (
                <div key={i} className="group py-2.5 border-b border-white/[0.03] last:border-0 hover:bg-white/[0.02] -mx-1 px-1 rounded transition-colors">
                  <div className="flex items-start gap-2">
                    <span className={cn('text-sm mt-0.5 flex-shrink-0', isPositive ? 'text-emerald-400' : 'text-red-400')}>
                      {isPositive ? '▲' : '▼'}
                    </span>
                    <div className="flex-1 min-w-0">
                      <a href={article.link || '#'} target="_blank" rel="noopener noreferrer"
                        className="text-[13px] text-white/80 font-mono leading-snug hover:text-white transition-colors block">
                        {article.title}
                      </a>
                      <div className="flex items-center gap-2 mt-1 flex-wrap">
                        <span className="text-[10px] text-white/25 font-mono">{article.source}</span>
                        <span className={cn('text-[9px] font-mono px-1 py-0.5 rounded',
                          article.impact_level === 'HIGH' ? 'bg-red-500/15 text-red-400' :
                          article.impact_level === 'MEDIUM' ? 'bg-amber-500/15 text-amber-400' :
                          'bg-white/5 text-white/30'
                        )}>{article.impact_level || 'LOW'}</span>
                        <span className={cn('text-[9px] font-mono px-1 py-0.5 rounded',
                          artScore > 0.1 ? 'bg-emerald-500/10 text-emerald-400/60' :
                          artScore < -0.1 ? 'bg-red-500/10 text-red-400/60' :
                          'bg-white/5 text-white/30'
                        )}>{artScore > 0 ? '+' : ''}{artScore.toFixed(2)}</span>
                        {article.affected_stocks?.slice(0, 3).map((s: any, j: number) => (
                          <span key={j} className={cn('text-[9px] font-mono px-1.5 py-0.5 rounded',
                            s.direction === 'UP' ? 'bg-emerald-500/10 text-emerald-400' :
                            s.direction === 'DOWN' ? 'bg-red-500/10 text-red-400' :
                            'bg-white/5 text-white/40'
                          )}>
                            {s.direction === 'UP' ? '↑' : s.direction === 'DOWN' ? '↓' : '→'} {s.ticker}
                          </span>
                        ))}
                      </div>
                    </div>
                    {article.link && (
                      <a href={article.link} target="_blank" rel="noopener noreferrer"
                        className="opacity-0 group-hover:opacity-100 transition-opacity text-white/20 hover:text-accent-cyan flex-shrink-0 mt-1">
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Sentiment pipeline details */}
      {mktSent && (
        <div className="glass-card p-4">
          <h4 className="font-mono text-[11px] text-white/40 uppercase tracking-wider mb-3">Sentiment Pipeline</h4>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { label: 'Engine', value: source === 'llm' ? 'NVIDIA NIM AI' : source === 'vader' ? 'VADER (fallback)' : 'TextBlob', color: source === 'llm' ? 'text-violet-400' : 'text-amber-400' },
              { label: 'Score', value: `${score > 0 ? '+' : ''}${score.toFixed(3)}`, color: score > 0 ? 'text-emerald-400' : score < 0 ? 'text-red-400' : 'text-white/50' },
              { label: 'Impact', value: mktSent.impact_level || 'LOW', color: mktSent.impact_level === 'HIGH' ? 'text-red-400' : 'text-amber-400' },
              { label: 'Articles', value: String(sentiment?.article_count || 0), color: 'text-white/70' },
            ].map(m => (
              <div key={m.label} className="bg-white/[0.03] rounded-lg p-3">
                <div className="text-[10px] text-white/30">{m.label}</div>
                <div className={cn('font-mono text-xs mt-1', m.color)}>{m.value}</div>
              </div>
            ))}
          </div>
          {mktSent.reasoning && <p className="text-[11px] text-white/30 mt-3 font-mono">{mktSent.reasoning}</p>}
        </div>
      )}
    </div>
  );
}
