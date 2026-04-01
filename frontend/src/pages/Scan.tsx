import { useState, useEffect, useRef } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { triggerScan, fetchScanResults, fetchSectors, api, scanSingleStock, fetchBudgetPicks } from '@/api/client';
import { useAppStore } from '@/store/useAppStore';
import { cn, confidenceColor, signalBg, formatINR, sentimentEmoji } from '@/lib/utils';
import { Loader2, Rocket, ChevronDown, Brain, Activity, Search, Wallet, TrendingUp } from 'lucide-react';
import type { ScanRequest, ScanResult } from '@/lib/types';

const fetchProgress = (scanId: string) =>
  api.get(`/api/scans/progress/${scanId}`).then(r => r.data);

export default function Scan() {
  const store = useAppStore();
  const [expandedTicker, setExpandedTicker] = useState<string | null>(null);
  const [progress, setProgress] = useState<any>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Single Stock Scan state ──
  const [singleTicker, setSingleTicker] = useState('');
  const [singleMode, setSingleMode] = useState('weekly');
  const [singleResult, setSingleResult] = useState<any>(null);
  const [singleLoading, setSingleLoading] = useState(false);
  const [singleError, setSingleError] = useState('');

  // ── Budget Picks state ──
  const [budgetAmount, setBudgetAmount] = useState(20000);
  const [budgetPicks, setBudgetPicks] = useState<any>(null);
  const [budgetLoading, setBudgetLoading] = useState(false);

  const doSingleScan = async () => {
    if (!singleTicker.trim()) return;
    setSingleLoading(true);
    setSingleError('');
    setSingleResult(null);
    try {
      const data = await scanSingleStock(singleTicker.trim(), singleMode, store.useAI);
      setSingleResult(data);
    } catch (e: any) {
      setSingleError(e.response?.data?.detail || e.message || 'Scan failed');
    }
    setSingleLoading(false);
  };

  const doBudgetPicks = async () => {
    setBudgetLoading(true);
    try {
      const data = await fetchBudgetPicks(budgetAmount, store.holdingMode, 500);
      setBudgetPicks(data);
    } catch { }
    setBudgetLoading(false);
  };

  // Use GLOBAL store scanId (survives tab switches)
  const scanId = store.currentScanId;

  // Poll for progress — runs whenever component mounts AND a scan is active
  useEffect(() => {
    if (!scanId || !store.isScanning) return;

    // Start polling immediately
    const poll = async () => {
      try {
        const p = await fetchProgress(scanId);
        setProgress(p);
        store.setScanProgress(p.stock ? { current: p.current, total: p.total, stock: p.stock } : null);

        if (p.status === 'complete') {
          store.setIsScanning(false);
          if (pollRef.current) clearInterval(pollRef.current);
          // Fetch full results
          try {
            const full = await fetchScanResults(scanId);
            store.setScanResults(scanId, {
              scan_id: scanId, analyzed: p.current, total_stocks: p.total,
              errors: 0, mode: store.holdingMode, news_articles_fetched: 0,
              buy_signals_count: p.buy_signals_count || 0,
              scan_date: new Date().toISOString(), scope: store.scope,
            }, full.results || []);
          } catch { /* results fetch failed */ }
        } else if (p.status === 'error') {
          store.setIsScanning(false);
          if (pollRef.current) clearInterval(pollRef.current);
        }
      } catch { /* ignore poll errors */ }
    };

    // Poll immediately on mount (reconnect after tab switch)
    poll();

    // Then poll every 1.5s
    pollRef.current = setInterval(poll, 1500);

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [scanId, store.isScanning]);

  const startScan = async () => {
    store.setIsScanning(true);
    store.setScanResults('', null as any, []);
    setProgress(null);

    try {
      const req: ScanRequest = {
        scope: store.scope, sectors: store.selectedSectors,
        mode: store.holdingMode, use_ai: store.useAI,
        min_confidence: store.minConfidence, max_positions: store.maxPositions,
        capital: store.capital,
      };
      const resp = await triggerScan(req);
      // Store scanId in GLOBAL store — survives tab switches
      store.setScanResults(resp.scan_id, null as any, []);
    } catch {
      store.setIsScanning(false);
    }
  };

  const buySignals = store.scanResults.filter(
    r => r.final_signal?.includes('BUY') && r.final_confidence >= store.minConfidence
  );

  return (
    <div className="space-y-6 animate-fade-in">

      {/* ── Quick Stock Scan ── */}
      <div className="glass-card p-5">
        <h3 className="text-sm font-semibold text-white/80 mb-3 flex items-center gap-2">
          <Search className="w-4 h-4 text-accent-cyan" />
          Scan Single Stock
        </h3>
        <div className="flex flex-wrap gap-3 items-end">
          <div className="flex-1 min-w-[160px]">
            <label className="text-[11px] text-white/40 uppercase tracking-wider block mb-1">Stock Name / Ticker</label>
            <input type="text" value={singleTicker}
              onChange={e => setSingleTicker(e.target.value.toUpperCase())}
              onKeyDown={e => e.key === 'Enter' && doSingleScan()}
              placeholder="e.g. SUZLON, SBI, RTN, NALCO"
              className="input-dark" />
          </div>
          <div className="w-[130px]">
            <label className="text-[11px] text-white/40 uppercase tracking-wider block mb-1">Mode</label>
            <select value={singleMode} onChange={e => setSingleMode(e.target.value)} className="select-dark">
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
            </select>
          </div>
          <button onClick={doSingleScan} disabled={singleLoading || !singleTicker.trim()}
            className="btn-primary px-5 py-2.5 flex items-center gap-2 disabled:opacity-40">
            {singleLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
            Analyze
          </button>
        </div>

        {singleError && <p className="text-red-400 text-sm mt-3">{singleError}</p>}

        {singleResult && (
          <div className="mt-4 p-4 rounded-xl bg-white/[0.03] border border-white/[0.06]">
            <div className="flex items-center justify-between mb-3">
              <div>
                <span className="text-lg font-bold text-white">{singleResult.ticker?.replace('.NS','')}</span>
                <span className="text-white/40 text-sm ml-2">{singleResult.name}</span>
                <span className="text-white/30 text-xs ml-2">{singleResult.sector} · {singleResult.cap}</span>
              </div>
              <div className={cn('px-3 py-1 rounded-lg text-sm font-bold', signalBg(singleResult.final_signal))}>
                {singleResult.final_signal} ({singleResult.final_confidence?.toFixed(0)}%)
              </div>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
              <div><span className="text-white/40">Price</span><br/><span className="text-white font-mono">₹{singleResult.current_price?.toLocaleString('en-IN', {minimumFractionDigits:2})}</span></div>
              <div><span className="text-white/40">Target</span><br/><span className="text-green-400 font-mono">₹{singleResult.entry_exit?.target_price?.toLocaleString('en-IN', {minimumFractionDigits:2}) || 'N/A'}</span>
                {singleResult.entry_exit?.potential_profit_pct ? <span className="text-green-400/60 text-xs ml-1">(+{singleResult.entry_exit.potential_profit_pct}%)</span> : null}
              </div>
              <div><span className="text-white/40">Stop Loss</span><br/><span className="text-red-400 font-mono">₹{singleResult.entry_exit?.stop_loss?.toLocaleString('en-IN', {minimumFractionDigits:2}) || 'N/A'}</span></div>
              <div><span className="text-white/40">R:R Ratio</span><br/><span className="text-accent-cyan font-mono">1:{singleResult.entry_exit?.risk_reward?.toFixed(1) || '0'}</span></div>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm mt-2">
              <div><span className="text-white/40">Base Score</span><br/><span className="font-mono">{singleResult.base_confidence?.toFixed(0)}%</span></div>
              <div><span className="text-white/40">News Impact</span><br/><span className="font-mono">{singleResult.news_modifier > 0 ? '+' : ''}{singleResult.news_modifier?.toFixed(1)}</span></div>
              <div><span className="text-white/40">AI Impact</span><br/><span className="font-mono">{singleResult.ai_modifier > 0 ? '+' : ''}{singleResult.ai_modifier?.toFixed(1)}</span></div>
              <div><span className="text-white/40">News Sentiment</span><br/><span>{singleResult.news_sentiment?.sentiment || singleResult.news_sentiment?.overall_sentiment || 'N/A'}</span></div>
            </div>
            {singleResult.ai_data?.ai_analysis && (
              <div className="mt-3 p-3 rounded-lg bg-violet-500/5 border border-violet-500/10 text-sm text-white/70">
                <span className="text-violet-400 text-xs font-medium">AI Analysis:</span> {singleResult.ai_data.ai_analysis}
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Budget Picks ── */}
      <div className="glass-card p-5">
        <h3 className="text-sm font-semibold text-white/80 mb-3 flex items-center gap-2">
          <Wallet className="w-4 h-4 text-green-400" />
          Budget Stock Picks (Low Price ≤₹500)
        </h3>
        <div className="flex flex-wrap gap-3 items-end">
          <div className="w-[180px]">
            <label className="text-[11px] text-white/40 uppercase tracking-wider block mb-1">Your Budget (₹)</label>
            <input type="number" value={budgetAmount} onChange={e => setBudgetAmount(Number(e.target.value))}
              className="input-dark" placeholder="15000" />
          </div>
          <button onClick={doBudgetPicks} disabled={budgetLoading}
            className="btn-primary px-5 py-2.5 flex items-center gap-2 disabled:opacity-40">
            {budgetLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <TrendingUp className="w-4 h-4" />}
            Find Picks
          </button>
          {budgetPicks && (
            <span className="text-xs text-white/30">
              From scan: {budgetPicks.scan_date?.slice(0,16) || 'N/A'}
            </span>
          )}
        </div>

        {budgetPicks?.message && <p className="text-yellow-400/70 text-sm mt-3">{budgetPicks.message}</p>}

        {budgetPicks?.picks?.length > 0 && (
          <div className="mt-4 space-y-2">
            {budgetPicks.picks.map((p: any, i: number) => (
              <div key={i} className="flex items-center justify-between p-3 rounded-xl bg-white/[0.03] border border-white/[0.06] text-sm">
                <div>
                  <span className="text-white font-semibold">{p.ticker}</span>
                  <span className="text-white/40 ml-2">{p.name}</span>
                  <div className="text-xs text-white/30 mt-0.5">{p.sector} · {p.signal} ({p.confidence?.toFixed(0)}%)</div>
                </div>
                <div className="text-right">
                  <div className="font-mono text-white">₹{p.price?.toFixed(2)} × {p.shares} = ₹{p.amount?.toLocaleString('en-IN')}</div>
                  <div className="text-xs">
                    <span className="text-green-400">🎯 ₹{p.target?.toFixed(2)} (+{p.expected_profit_pct}%)</span>
                    <span className="text-red-400 ml-3">🛑 ₹{p.stop_loss?.toFixed(2)} (-{p.risk_pct}%)</span>
                  </div>
                </div>
              </div>
            ))}
            <div className="flex justify-between text-xs text-white/40 pt-2">
              <span>Invested: ₹{budgetPicks.total_invested?.toLocaleString('en-IN')}</span>
              <span>Cash Reserve: ₹{budgetPicks.cash_reserve?.toLocaleString('en-IN')}</span>
            </div>
          </div>
        )}
      </div>

      {/* ── Full Market Scan Controls ── */}
      <div className="glass-card p-5">
        <div className="grid grid-cols-2 lg:grid-cols-6 gap-4 items-end">
          <div>
            <label className="text-[11px] text-white/40 uppercase tracking-wider block mb-2 font-medium">Capital (₹)</label>
            <input type="number" value={store.capital}
              onChange={e => store.setCapital(Number(e.target.value))}
              className="input-dark" />
          </div>
          <div>
            <label className="text-[11px] text-white/40 uppercase tracking-wider block mb-2 font-medium">Holding Period</label>
            <select value={store.holdingMode}
              onChange={e => store.setHoldingMode(e.target.value as 'weekly' | 'monthly')}
              className="select-dark">
              <option value="weekly">Weekly (5-day)</option>
              <option value="monthly">Monthly (20-day)</option>
            </select>
          </div>
          <div>
            <label className="text-[11px] text-white/40 uppercase tracking-wider block mb-2 font-medium">Universe</label>
            <select value={store.scope} onChange={e => store.setScope(e.target.value)}
              className="select-dark">
              <option value="all">All Stocks (~130)</option>
              <option value="large">Large Cap (~50)</option>
              <option value="mid">Mid Cap (~50)</option>
              <option value="small">Small Cap (~30)</option>
            </select>
          </div>
          <div>
            <label className="text-[11px] text-white/40 uppercase tracking-wider block mb-2 font-medium">
              Min Confidence: <span className="text-accent-cyan">{store.minConfidence}%</span>
            </label>
            <div className="pt-1.5">
              <input type="range" min={50} max={95} step={5}
                value={store.minConfidence}
                onChange={e => store.setMinConfidence(Number(e.target.value))}
                className="w-full" />
            </div>
          </div>
          <div>
            <label className="text-[11px] text-white/40 uppercase tracking-wider block mb-2 font-medium">NIM AI</label>
            <button onClick={() => store.setUseAI(!store.useAI)}
              className={cn(
                'w-full px-4 py-2.5 rounded-xl text-sm font-medium border transition-all duration-200 flex items-center justify-center gap-2',
                store.useAI
                  ? 'bg-violet-500/15 border-violet-500/30 text-violet-400'
                  : 'bg-white/[0.03] border-white/[0.08] text-white/30'
              )}>
              <Brain className="w-4 h-4" />
              {store.useAI ? 'AI ON' : 'AI OFF'}
            </button>
          </div>
          <div>
            <label className="text-[11px] text-white/40 uppercase tracking-wider block mb-2 font-medium">&nbsp;</label>
            <button onClick={startScan} disabled={store.isScanning}
              className="btn-primary w-full flex items-center justify-center gap-2 py-2.5">
              {store.isScanning ? (
                <><Loader2 className="w-4 h-4 animate-spin" /> Scanning...</>
              ) : (
                <><Rocket className="w-4 h-4" /> SCAN MARKET</>
              )}
            </button>
          </div>
        </div>

        {/* ── Live Progress Bar ── */}
        {store.isScanning && progress && progress.status === 'running' && (
          <div className="mt-5 space-y-3">
            <div className="w-full h-2 bg-white/[0.06] rounded-full overflow-hidden">
              <div className="h-full bg-gradient-to-r from-violet-500 via-cyan-400 to-emerald-400 rounded-full transition-all duration-500 ease-out"
                style={{ width: `${progress.percent || 0}%` }} />
            </div>
            <div className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-3">
                <span className="font-mono text-cyan-400 font-bold text-lg">{progress.percent || 0}%</span>
                <div>
                  <div className="text-white/70 font-medium">{progress.stock || 'Starting...'}</div>
                  <div className="text-white/30 font-mono text-[10px]">
                    {progress.current || 0} / {progress.total || '?'} stocks
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-4 text-white/30 font-mono text-[10px]">
                <span>Signals: <span className="text-emerald-400">{progress.results_so_far || 0}</span></span>
                <span className="flex items-center gap-1">
                  <Activity className="w-3 h-3 text-violet-400 animate-pulse" /> Live
                </span>
              </div>
            </div>
          </div>
        )}

        {store.isScanning && (!progress || progress.status !== 'running') && (
          <div className="mt-4 text-center">
            <div className="w-full h-1.5 bg-white/[0.06] rounded-full overflow-hidden">
              <div className="h-full bg-gradient-to-r from-violet-500 to-cyan-400 rounded-full animate-pulse w-1/3" />
            </div>
            <p className="text-[11px] text-white/30 mt-2 font-mono">Initializing scan engine...</p>
          </div>
        )}
      </div>

      {/* ── Quick Single Stock Scan ── */}
      <div className="glass-card p-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex-1 min-w-[200px]">
            <label className="text-[11px] text-white/40 uppercase tracking-wider block mb-2 font-medium">Quick Stock Scan</label>
            <input type="text" placeholder="Enter ticker: SUZLON, SBI, RTN..."
              id="single-stock-input"
              onKeyDown={e => { if (e.key === 'Enter') document.getElementById('scan-single-btn')?.click(); }}
              className="input-dark" />
          </div>
          <button id="scan-single-btn"
            onClick={async () => {
              const inp = document.getElementById('single-stock-input') as HTMLInputElement;
              const ticker = inp?.value?.trim();
              if (!ticker) return;
              const resultDiv = document.getElementById('single-result');
              if (resultDiv) resultDiv.innerHTML = '<div class="text-cyan-400 text-sm animate-pulse">Scanning ' + ticker.toUpperCase() + '...</div>';
              try {
                const { scanSingleStock } = await import('@/api/client');
                const r = await scanSingleStock(ticker, store.holdingMode, store.useAI);
                const ee = r.entry_exit || {};
                const targetStr = ee.target_price ? `₹${Number(ee.target_price).toLocaleString('en-IN', {minimumFractionDigits:2})}` : 'N/A';
                const slStr = ee.stop_loss ? `₹${Number(ee.stop_loss).toLocaleString('en-IN', {minimumFractionDigits:2})}` : 'N/A';
                const profitPct = ee.potential_profit_pct || 0;
                const sigColor = r.final_signal?.includes('BUY') ? 'text-emerald-400' : r.final_signal?.includes('SELL') ? 'text-red-400' : 'text-amber-400';
                if (resultDiv) resultDiv.innerHTML = `
                  <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-2">
                    <div><div class="text-[10px] text-white/30">SIGNAL</div><div class="${sigColor} font-bold">${r.final_signal} (${r.final_confidence}%)</div></div>
                    <div><div class="text-[10px] text-white/30">PRICE</div><div class="text-white font-mono">₹${Number(r.current_price).toLocaleString('en-IN', {minimumFractionDigits:2})}</div></div>
                    <div><div class="text-[10px] text-white/30">TARGET (+${profitPct}%)</div><div class="text-emerald-400 font-mono">${targetStr}</div></div>
                    <div><div class="text-[10px] text-white/30">STOP LOSS</div><div class="text-red-400 font-mono">${slStr}</div></div>
                  </div>
                  <div class="mt-2 text-[11px] text-white/40">${r.name} · ${r.sector} · ${r.cap} Cap · R:R 1:${ee.risk_reward || 0} · News: ${r.news_sentiment?.overall_sentiment || 'N/A'}</div>
                `;
              } catch (err: any) {
                if (resultDiv) resultDiv.innerHTML = `<div class="text-red-400 text-sm">${err?.response?.data?.detail || err.message || 'Scan failed'}</div>`;
              }
            }}
            className="btn-primary px-6 py-2.5 flex items-center gap-2 text-sm">
            <Activity className="w-4 h-4" /> Scan Stock
          </button>
          <button
            onClick={async () => {
              const resultDiv = document.getElementById('budget-result');
              if (resultDiv) resultDiv.innerHTML = '<div class="text-cyan-400 text-sm animate-pulse">Finding budget picks...</div>';
              try {
                const { fetchBudgetPicks } = await import('@/api/client');
                const data = await fetchBudgetPicks(store.capital, store.holdingMode, 500);
                if (!data.picks?.length) {
                  if (resultDiv) resultDiv.innerHTML = '<div class="text-amber-400 text-sm">No budget picks found. Run a scan first.</div>';
                  return;
                }
                let html = `<div class="text-[11px] text-white/40 mb-2">Budget: ₹${data.budget.toLocaleString()} | Invested: ₹${data.total_invested.toLocaleString()} | Cash: ₹${data.cash_reserve.toLocaleString()}</div>`;
                for (const p of data.picks) {
                  html += `<div class="flex items-center justify-between py-1.5 border-b border-white/[0.04]">
                    <div><span class="text-white font-medium">${p.ticker}</span> <span class="text-white/30 text-xs">${p.name}</span></div>
                    <div class="text-right text-xs font-mono">
                      <span class="text-emerald-400">${p.shares} shares</span> · ₹${p.amount.toLocaleString()} · <span class="text-cyan-400">+${p.expected_profit_pct}%</span>
                    </div>
                  </div>`;
                }
                if (resultDiv) resultDiv.innerHTML = html;
              } catch (err: any) {
                if (resultDiv) resultDiv.innerHTML = `<div class="text-red-400 text-sm">${err?.message || 'Failed'}</div>`;
              }
            }}
            className="btn-secondary px-4 py-2.5 text-sm">
            💰 Budget Picks (≤₹500)
          </button>
        </div>
        <div id="single-result" className="mt-3"></div>
        <div id="budget-result" className="mt-3"></div>
      </div>

      {/* ── Scan Summary ── */}
      {store.scanSummary && !store.isScanning && (
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          {[
            { label: 'Scanned', value: store.scanSummary.analyzed || 0, color: 'text-white/90' },
            { label: 'BUY Signals', value: buySignals.length, color: 'text-emerald-400' },
            { label: 'Mode', value: store.scanSummary.mode || store.holdingMode, color: 'text-cyan-400' },
            { label: 'News', value: store.scanSummary.news_articles_fetched || 0, color: 'text-amber-400' },
            { label: 'Errors', value: store.scanSummary.errors || 0, color: (store.scanSummary.errors || 0) > 0 ? 'text-red-400' : 'text-emerald-400' },
          ].map(m => (
            <div key={m.label} className="glass-card p-3 text-center">
              <div className="text-[10px] text-white/30 uppercase tracking-wider">{m.label}</div>
              <div className={cn('font-mono font-bold text-lg mt-0.5', m.color)}>{m.value}</div>
            </div>
          ))}
        </div>
      )}

      {/* ── Results ── */}
      {store.scanResults.length > 0 && !store.isScanning && (
        <div className="space-y-3">
          <div className="flex items-center justify-between px-1">
            <h3 className="font-display font-semibold text-sm text-white/60">
              BUY Signals ({buySignals.length}) — Confidence ≥ {store.minConfidence}%
            </h3>
          </div>

          {buySignals.length === 0 ? (
            <div className="glass-card p-10 text-center text-white/30 text-sm">
              No stocks meet the {store.minConfidence}% threshold. Try lowering it.
            </div>
          ) : (
            buySignals.map((sig, i) => (
              <div key={sig.ticker}
                className={cn(signalBg(sig.final_signal), 'p-5 cursor-pointer')}
                onClick={() => setExpandedTicker(expandedTicker === sig.ticker ? null : sig.ticker)}>

                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-white/[0.05] flex items-center justify-center font-mono text-[11px] font-bold text-cyan-400">
                      #{i + 1}
                    </div>
                    <div>
                      <span className="font-mono font-bold text-[15px] text-white">{sig.ticker.replace('.NS', '')}</span>
                      <span className="text-white/35 text-xs ml-2">{sig.name}</span>
                    </div>
                    <span className="text-[9px] px-2 py-0.5 rounded-full bg-white/[0.04] text-white/25 border border-white/[0.06] hidden sm:inline">
                      {sig.sector} · {sig.cap}
                    </span>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="text-right">
                      <div className={cn('font-mono font-bold text-2xl', confidenceColor(sig.final_confidence))}>
                        {sig.final_confidence}%
                      </div>
                      <div className="text-[9px] text-white/30 font-mono">{sig.final_signal}</div>
                    </div>
                    <ChevronDown className={cn('w-4 h-4 text-white/20 transition-transform', expandedTicker === sig.ticker && 'rotate-180')} />
                  </div>
                </div>

                <div className="grid grid-cols-4 sm:grid-cols-7 gap-3 mt-4 text-xs">
                  {[
                    { label: 'Price', value: formatINR(sig.current_price), color: 'text-white/80' },
                    { label: 'Entry', value: sig.entry_exit?.entry_price ? formatINR(sig.entry_exit.entry_price) : '—', color: 'text-cyan-400' },
                    { label: 'Target', value: sig.entry_exit?.target_price ? formatINR(sig.entry_exit.target_price) : '—', color: 'text-emerald-400' },
                    { label: 'Stop Loss', value: sig.entry_exit?.stop_loss ? formatINR(sig.entry_exit.stop_loss) : '—', color: 'text-red-400' },
                    { label: 'R:R', value: sig.entry_exit?.risk_reward?.toFixed(1) || '—', color: 'text-white/60' },
                    { label: 'Profit%', value: sig.entry_exit?.potential_profit_pct ? `+${sig.entry_exit.potential_profit_pct}%` : '—', color: 'text-emerald-400' },
                    { label: 'News', value: sig.news_sentiment?.sentiment || '—', color: 'text-white/60' },
                  ].map(m => (
                    <div key={m.label}>
                      <div className="text-white/25 text-[10px] mb-0.5">{m.label}</div>
                      <div className={cn('font-mono', m.color)}>{m.value}</div>
                    </div>
                  ))}
                </div>

                {/* Expanded */}
                {expandedTicker === sig.ticker && (
                  <div className="mt-5 pt-5 border-t border-white/[0.06] space-y-4">
                    {sig.indicator_scores && (
                      <div>
                        <h4 className="text-[10px] text-white/30 uppercase tracking-wider mb-3">Indicator Breakdown</h4>
                        <div className="grid grid-cols-3 lg:grid-cols-5 gap-2">
                          {Object.entries(sig.indicator_scores).map(([key, val]: [string, any]) => (
                            <div key={key} className="bg-white/[0.02] rounded-xl p-2.5 border border-white/[0.04]">
                              <div className="text-[9px] text-white/30 truncate mb-1">{key}</div>
                              <div className={cn('font-mono text-xs font-bold',
                                val.score > 0 ? 'text-emerald-400' : val.score < 0 ? 'text-red-400' : 'text-white/25')}>
                                {val.score > 0 ? '+' : ''}{val.score}/{val.max}
                              </div>
                              <div className="text-[8px] text-white/20 truncate mt-0.5">{val.reason}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {sig.ai_data?.ai_analysis && (
                      <div className="bg-violet-500/[0.04] border border-violet-500/10 rounded-xl p-4">
                        <div className="flex items-center gap-2 mb-2">
                          <Brain className="w-3.5 h-3.5 text-violet-400" />
                          <span className="text-[11px] text-violet-400 font-semibold">NIM AI Analysis</span>
                        </div>
                        <p className="text-[12px] text-white/50 leading-relaxed">{sig.ai_data.ai_analysis}</p>
                        {(sig.ai_data?.ai_key_factors?.length ?? 0) > 0 && (
                          <div className="mt-2 flex flex-wrap gap-1.5">
                            {sig.ai_data?.ai_key_factors?.map((f: string, j: number) => (
                              <span key={j} className="text-[8px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400">{f}</span>
                            ))}
                          </div>
                        )}
                      </div>
                    )}

                    <div className="flex gap-4 text-[11px] text-white/25 font-mono">
                      <span>Base: <span className="text-white/60">{sig.base_confidence}%</span></span>
                      <span>News: <span className={sig.news_modifier > 0 ? 'text-emerald-400' : sig.news_modifier < 0 ? 'text-red-400' : 'text-white/40'}>{sig.news_modifier > 0 ? '+' : ''}{sig.news_modifier}</span></span>
                      <span>AI: <span className={sig.ai_modifier > 0 ? 'text-emerald-400' : sig.ai_modifier < 0 ? 'text-red-400' : 'text-white/40'}>{sig.ai_modifier > 0 ? '+' : ''}{sig.ai_modifier}</span></span>
                    </div>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
