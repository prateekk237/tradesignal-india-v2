import { useQuery } from '@tanstack/react-query';
import { fetchSettings, checkHealth } from '@/api/client';
import { cn } from '@/lib/utils';

export default function StatusBar() {
  const { data: settings } = useQuery({ queryKey: ['settings'], queryFn: fetchSettings, refetchInterval: 30000 });
  const { data: health } = useQuery({ queryKey: ['health'], queryFn: checkHealth, refetchInterval: 15000 });

  const isOnline = health?.status === 'ok';

  return (
    <div className="h-7 bg-surface-0 border-t border-white/[0.06] flex items-center justify-between px-4 text-[10px] font-mono">
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-1.5">
          <div className={cn('w-1.5 h-1.5 rounded-full', isOnline ? 'bg-emerald-400 animate-pulse-slow' : 'bg-red-400')} />
          <span className={cn(isOnline ? 'text-emerald-400/70' : 'text-red-400/70')}>
            {isOnline ? 'Connected' : 'Offline'}
          </span>
        </div>
        <span className="text-white/20">|</span>
        <span className="text-white/40">
          Sched: <span className="text-white/60">4</span>
        </span>
        <span className="text-white/40">
          Cache: <span className="text-white/60">{settings?.total_stocks || 0}</span>
        </span>
        <span className="text-white/40">
          LLM: <span className={cn(settings?.nim_api_configured ? 'text-emerald-400' : 'text-red-400/60')}>
            {settings?.nim_api_configured ? '1' : '0'}
          </span>
        </span>
        <span className="text-white/40">
          News: <span className="text-white/60">8 feeds</span>
        </span>
      </div>
      <div className="flex items-center gap-4">
        <span className="text-white/30">{settings?.nim_model || ''}</span>
        <span className="text-white/20">TradeSignal India v2.0</span>
      </div>
    </div>
  );
}
