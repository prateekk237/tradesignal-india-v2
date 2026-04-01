import { useState, useEffect, useRef } from 'react';
import { cn } from '@/lib/utils';
import { Trash2 } from 'lucide-react';

export type LogLevel = 'info' | 'rest' | 'ws' | 'error' | 'warn';
export type LogEntry = {
  time: string;
  level: LogLevel;
  tag: string;
  status?: number;
  message: string;
};

// Global log store
let _logs: LogEntry[] = [];
let _listeners: Array<() => void> = [];

export function pushLog(level: LogLevel, tag: string, message: string, status?: number) {
  const now = new Date();
  const time = now.toLocaleTimeString('en-IN', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
  _logs = [..._logs.slice(-200), { time, level, tag, status, message }];
  _listeners.forEach(fn => fn());
}

export function clearLogs() {
  _logs = [];
  _listeners.forEach(fn => fn());
}

function useLogs() {
  const [, setTick] = useState(0);
  useEffect(() => {
    const fn = () => setTick(t => t + 1);
    _listeners.push(fn);
    return () => { _listeners = _listeners.filter(l => l !== fn); };
  }, []);
  return _logs;
}

const LEVEL_COLORS: Record<LogLevel, string> = {
  info: 'text-emerald-400',
  rest: 'text-sky-400',
  ws: 'text-violet-400',
  error: 'text-red-400',
  warn: 'text-amber-400',
};

const FILTERS = ['ALL', 'WS', 'REST', 'ERROR', 'INFO'] as const;

export default function SystemLogs() {
  const logs = useLogs();
  const [filter, setFilter] = useState<typeof FILTERS[number]>('ALL');
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs.length]);

  const filtered = filter === 'ALL' ? logs : logs.filter(l => {
    if (filter === 'REST') return l.level === 'rest';
    if (filter === 'WS') return l.level === 'ws';
    if (filter === 'ERROR') return l.level === 'error' || l.level === 'warn';
    if (filter === 'INFO') return l.level === 'info';
    return true;
  });

  return (
    <div className="border-t border-white/[0.06] bg-surface-0">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-white/[0.06]">
        <div className="flex items-center gap-4">
          <span className="text-[11px] font-mono font-bold text-white/70 uppercase tracking-wider">System Logs</span>
          <span className="text-[10px] text-white/30 font-mono">WS · REST · Errors</span>
        </div>
        <div className="flex items-center gap-2">
          {/* Filter Tabs */}
          {FILTERS.map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={cn(
                'text-[10px] font-mono px-2.5 py-1 rounded transition-all',
                filter === f
                  ? 'bg-white/10 text-white'
                  : 'text-white/30 hover:text-white/60'
              )}
            >
              {f}
            </button>
          ))}
          <button onClick={clearLogs} className="text-white/20 hover:text-white/50 transition-colors ml-2" title="Clear logs">
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Log entries */}
      <div ref={scrollRef} className="h-[180px] overflow-y-auto font-mono text-[11px] leading-[22px] px-4 py-1">
        {filtered.length === 0 ? (
          <div className="text-white/20 py-4 text-center">No logs yet</div>
        ) : (
          filtered.map((log, i) => (
            <div key={i} className="flex items-center gap-3 hover:bg-white/[0.02] px-1 rounded">
              <span className="text-white/25 w-[60px] flex-shrink-0">{log.time}</span>
              <span className={cn('w-[36px] flex-shrink-0 font-medium', LEVEL_COLORS[log.level])}>{log.level}</span>
              <span className="text-white/40 w-[48px] flex-shrink-0 truncate">{log.tag}</span>
              {log.status !== undefined && (
                <span className={cn('w-[28px] flex-shrink-0 font-medium',
                  log.status >= 200 && log.status < 300 ? 'text-emerald-400' :
                  log.status >= 400 ? 'text-red-400' : 'text-amber-400'
                )}>{log.status}</span>
              )}
              <span className="text-white/50 truncate">{log.message}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
