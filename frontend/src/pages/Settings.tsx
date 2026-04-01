import { useQuery } from '@tanstack/react-query';
import { fetchSettings } from '@/api/client';
import { useAppStore } from '@/store/useAppStore';
import { Settings as SettingsIcon, Key, MessageCircle, DollarSign, Brain, Check, X } from 'lucide-react';
import { cn } from '@/lib/utils';

export default function SettingsPage() {
  const { data: settings, isLoading } = useQuery({ queryKey: ['settings'], queryFn: fetchSettings });
  const store = useAppStore();

  return (
    <div className="space-y-6 animate-fade-in max-w-3xl">
      <h3 className="font-display font-semibold text-lg text-white/90">System Settings</h3>

      {/* API Status */}
      <div className="glass-card p-5 space-y-4">
        <h4 className="font-display font-semibold text-sm text-white/70 flex items-center gap-2">
          <Key className="w-4 h-4 text-accent-purple" /> API Configuration
        </h4>

        <div className="grid grid-cols-2 gap-4">
          <div className="bg-white/[0.03] rounded-xl p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-white/50 flex items-center gap-2">
                <Brain className="w-3.5 h-3.5" /> NVIDIA NIM API
              </span>
              {settings?.nim_api_configured ? (
                <span className="flex items-center gap-1 text-[10px] text-accent-green"><Check className="w-3 h-3" /> Connected</span>
              ) : (
                <span className="flex items-center gap-1 text-[10px] text-accent-red"><X className="w-3 h-3" /> Not configured</span>
              )}
            </div>
            <div className="text-[11px] text-white/30 font-mono">{settings?.nim_model || 'meta/llama-3.3-70b-instruct'}</div>
            <p className="text-[10px] text-white/20 mt-2">Primary: LLM sentiment + stock analysis. Fallback: VADER → TextBlob</p>
          </div>

          <div className="bg-white/[0.03] rounded-xl p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-white/50 flex items-center gap-2">
                <MessageCircle className="w-3.5 h-3.5" /> Telegram Bot
              </span>
              {settings?.telegram_configured ? (
                <span className="flex items-center gap-1 text-[10px] text-accent-green"><Check className="w-3 h-3" /> Connected</span>
              ) : (
                <span className="flex items-center gap-1 text-[10px] text-accent-red"><X className="w-3 h-3" /> Not configured</span>
              )}
            </div>
            <p className="text-[10px] text-white/20 mt-2">Alerts for BUY signals, exits, and weekly summaries</p>
          </div>
        </div>

        <p className="text-[10px] text-white/20">API keys are configured via environment variables for security. Set <code className="text-accent-cyan/50">NIM_API_KEY</code> and <code className="text-accent-cyan/50">TELEGRAM_BOT_TOKEN</code> in Railway secrets or <code className="text-accent-cyan/50">.env</code> file.</p>
      </div>

      {/* Trading Defaults */}
      <div className="glass-card p-5 space-y-4">
        <h4 className="font-display font-semibold text-sm text-white/70 flex items-center gap-2">
          <DollarSign className="w-4 h-4 text-accent-green" /> Trading Defaults
        </h4>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-[11px] text-white/40 block mb-1.5">Default Capital (₹)</label>
            <input type="number" value={store.capital} onChange={e => store.setCapital(Number(e.target.value))}
              className="w-full bg-white/[0.04] border border-white/[0.08] rounded-lg px-3 py-2 text-sm font-mono text-white focus:outline-none focus:border-accent-purple" />
          </div>
          <div>
            <label className="text-[11px] text-white/40 block mb-1.5">Holding Mode</label>
            <select value={store.holdingMode} onChange={e => store.setHoldingMode(e.target.value as any)}
              className="w-full bg-white/[0.04] border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-accent-purple appearance-none">
              <option value="weekly">Weekly (5-day)</option>
              <option value="monthly">Monthly (20-day)</option>
            </select>
          </div>
          <div>
            <label className="text-[11px] text-white/40 block mb-1.5">Min Confidence: {store.minConfidence}%</label>
            <input type="range" min={50} max={95} step={5} value={store.minConfidence}
              onChange={e => store.setMinConfidence(Number(e.target.value))} className="w-full accent-accent-purple" />
          </div>
          <div>
            <label className="text-[11px] text-white/40 block mb-1.5">Max Positions</label>
            <input type="number" min={1} max={10} value={store.maxPositions} onChange={e => store.setMaxPositions(Number(e.target.value))}
              className="w-full bg-white/[0.04] border border-white/[0.08] rounded-lg px-3 py-2 text-sm font-mono text-white focus:outline-none focus:border-accent-purple" />
          </div>
        </div>
      </div>

      {/* System Info */}
      <div className="glass-card p-5 space-y-3">
        <h4 className="font-display font-semibold text-sm text-white/70 flex items-center gap-2">
          <SettingsIcon className="w-4 h-4 text-white/50" /> System Info
        </h4>
        <div className="grid grid-cols-2 gap-3 text-xs">
          {[
            ['Version', 'v2.0.0'],
            ['Total Stocks', `${settings?.total_stocks || 130}`],
            ['Sectors', `${settings?.sectors?.length || 0}`],
            ['Indicators', '15 categories'],
            ['Sentiment Engine', 'LLM → VADER → TextBlob'],
            ['News Sources', '8 RSS feeds'],
            ['Scoring Model', '127-point normalized to 100'],
            ['Framework', 'React + FastAPI + PostgreSQL'],
          ].map(([label, value]) => (
            <div key={label} className="flex justify-between py-1.5 border-b border-white/[0.03]">
              <span className="text-white/40">{label}</span>
              <span className="font-mono text-white/70">{value}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
