import { useState } from 'react';
import { BrowserRouter, Routes, Route, NavLink, useLocation } from 'react-router-dom';
import { LayoutDashboard, ScanSearch, Briefcase, LineChart, Newspaper, History, Settings, TrendingUp, Activity, Menu, X, Terminal } from 'lucide-react';
import { cn } from '@/lib/utils';
import Dashboard from '@/pages/Dashboard';
import Scan from '@/pages/Scan';
import Portfolio from '@/pages/Portfolio';
import Screener from '@/pages/Screener';
import News from '@/pages/News';
import TradeHistory from '@/pages/TradeHistory';
import SettingsPage from '@/pages/Settings';
import SystemLogs, { pushLog } from '@/components/widgets/SystemLogs';
import StatusBar from '@/components/widgets/StatusBar';

// ── Intercept API calls to log them ──────────────────────────
import { api } from '@/api/client';

api.interceptors.request.use((config) => {
  const tag = config.url?.split('/').pop()?.split('?')[0] || '?';
  pushLog('rest', tag, `→ ${config.method?.toUpperCase()} ${config.url}`);
  return config;
});

api.interceptors.response.use(
  (res) => {
    const tag = res.config.url?.split('/').pop()?.split('?')[0] || '?';
    pushLog('rest', tag, `${res.config.method?.toUpperCase()} ${res.config.url}`, res.status);
    return res;
  },
  (err) => {
    const tag = err.config?.url?.split('/').pop()?.split('?')[0] || '?';
    pushLog('error', tag, `${err.message} — ${err.config?.url}`, err.response?.status || 0);
    return Promise.reject(err);
  }
);

// Log startup
pushLog('info', '◉', 'TradeSignal India v2.0 initialized');
pushLog('info', '◉', 'Sentiment: LLM (primary) → VADER → TextBlob');
pushLog('info', '◉', 'Indicators: 15 categories, 127-point model');

const NAV_ITEMS = [
  { path: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { path: '/scan', icon: ScanSearch, label: 'Scanner' },
  { path: '/portfolio', icon: Briefcase, label: 'Portfolio' },
  { path: '/screener', icon: LineChart, label: 'Screener' },
  { path: '/news', icon: Newspaper, label: 'News' },
  { path: '/history', icon: History, label: 'History' },
  { path: '/settings', icon: Settings, label: 'Settings' },
];

function Sidebar({ mobileOpen, onClose }: { mobileOpen: boolean; onClose: () => void }) {
  return (
    <>
      {/* Mobile overlay */}
      {mobileOpen && (
        <div className="fixed inset-0 bg-black/60 z-40 lg:hidden" onClick={onClose} />
      )}

      <aside className={cn(
        'fixed top-0 bottom-0 w-[220px] bg-surface-1 border-r border-white/[0.06] flex flex-col z-50 transition-transform duration-300',
        'lg:translate-x-0',
        mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
      )}>
        {/* Brand */}
        <div className="px-5 pt-6 pb-4 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-accent-cyan to-accent-purple flex items-center justify-center">
              <Activity className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="font-display font-bold text-[15px] leading-tight gradient-text">TradeSignal</h1>
              <span className="text-[10px] text-white/40 font-mono tracking-wider">INDIA v2.0</span>
            </div>
          </div>
          <button onClick={onClose} className="lg:hidden text-white/40 hover:text-white">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-2 space-y-0.5">
          {NAV_ITEMS.map(item => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === '/'}
              onClick={onClose}
              className={({ isActive }) => cn(
                'flex items-center gap-3 px-3 py-2.5 rounded-xl text-[13px] font-medium transition-all duration-200',
                isActive
                  ? 'bg-white/[0.08] text-white'
                  : 'text-white/50 hover:text-white/80 hover:bg-white/[0.04]'
              )}
            >
              <item.icon className="w-[18px] h-[18px]" />
              {item.label}
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div className="px-4 py-4 border-t border-white/[0.06]">
          <div className="flex items-center gap-2 text-[11px] text-white/30">
            <TrendingUp className="w-3.5 h-3.5" />
            <span className="font-mono">NSE · FOSS · AI</span>
          </div>
        </div>
      </aside>
    </>
  );
}

function TopBar({ onMenuClick }: { onMenuClick: () => void }) {
  const location = useLocation();
  const current = NAV_ITEMS.find(n => n.path === location.pathname) || NAV_ITEMS[0];

  return (
    <header className="h-14 border-b border-white/[0.06] bg-surface-1/80 backdrop-blur-md flex items-center justify-between px-4 lg:px-6 sticky top-0 z-30">
      <div className="flex items-center gap-3">
        <button onClick={onMenuClick} className="lg:hidden text-white/50 hover:text-white">
          <Menu className="w-5 h-5" />
        </button>
        <h2 className="font-display font-semibold text-[15px] text-white/90">{current.label}</h2>
      </div>
      <div className="flex items-center gap-4">
        <span className="text-[11px] text-white/40 font-mono hidden sm:block">
          {new Date().toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })}
        </span>
        <div className="w-2 h-2 rounded-full bg-accent-green animate-pulse-slow" title="Online" />
      </div>
    </header>
  );
}

export default function App() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [logsOpen, setLogsOpen] = useState(true);

  return (
    <BrowserRouter>
      <div className="flex min-h-screen flex-col">
        <div className="flex flex-1">
          <Sidebar mobileOpen={mobileOpen} onClose={() => setMobileOpen(false)} />

          <main className="flex-1 lg:ml-[220px] flex flex-col">
            <TopBar onMenuClick={() => setMobileOpen(true)} />

            {/* Page content */}
            <div className="flex-1 p-4 lg:p-6 overflow-auto">
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/scan" element={<Scan />} />
                <Route path="/portfolio" element={<Portfolio />} />
                <Route path="/screener" element={<Screener />} />
                <Route path="/news" element={<News />} />
                <Route path="/history" element={<TradeHistory />} />
                <Route path="/settings" element={<SettingsPage />} />
              </Routes>
            </div>

            {/* Logs toggle */}
            <button
              onClick={() => setLogsOpen(!logsOpen)}
              className="flex items-center gap-2 px-4 py-1.5 text-[10px] font-mono text-white/30 hover:text-white/50 border-t border-white/[0.06] bg-surface-0 transition-colors"
            >
              <Terminal className="w-3 h-3" />
              {logsOpen ? 'Hide' : 'Show'} System Logs
            </button>

            {/* System Logs Panel */}
            {logsOpen && <SystemLogs />}

            {/* Status Bar */}
            <StatusBar />
          </main>
        </div>
      </div>
    </BrowserRouter>
  );
}
