import axios from 'axios';
import type { ScanRequest, ScanResult, ScanSummary, Allocation, NewsArticle } from '@/lib/types';

const API_BASE = import.meta.env.VITE_API_URL || '';

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 300000, // 5 min for scans
  headers: { 'Content-Type': 'application/json' },
});

// ── Stocks ────────────────────────────────────────────────
export const fetchStocks = (params?: { cap?: string; sector?: string }) =>
  api.get('/api/stocks', { params }).then(r => r.data);

export const fetchSectors = () =>
  api.get('/api/stocks/sectors').then(r => r.data.sectors as string[]);

// ── Scans ─────────────────────────────────────────────────
export const triggerScan = (req: ScanRequest) =>
  api.post<ScanSummary>('/api/scans', req).then(r => r.data);

export const fetchScanResults = (scanId: string, minConfidence = 0) =>
  api.get(`/api/scans/${scanId}`, { params: { min_confidence: minConfidence } }).then(r => r.data);

export const fetchBuySignals = (scanId: string, minConfidence = 65) =>
  api.get(`/api/scans/${scanId}/signals`, { params: { min_confidence: minConfidence } }).then(r => r.data);

export const fetchLatestSummary = () =>
  api.get('/api/scans/latest/summary').then(r => r.data);

// ── Portfolio ─────────────────────────────────────────────
export const allocatePortfolio = (capital: number, candidates: any[], maxPositions = 5, minConfidence = 65) =>
  api.post('/api/portfolio/allocate', { capital, candidates, max_positions: maxPositions, min_confidence: minConfidence }).then(r => r.data);

// ── News ──────────────────────────────────────────────────
export const fetchNews = (limit = 50) =>
  api.get('/api/news', { params: { limit } }).then(r => r.data);

export const fetchMarketSentiment = () =>
  api.get('/api/news/sentiment').then(r => r.data);

// ── Settings ──────────────────────────────────────────────
export const fetchSettings = () =>
  api.get('/api/settings').then(r => r.data);

// ── Health ────────────────────────────────────────────────
export const checkHealth = () =>
  api.get('/health').then(r => r.data);

// ── Single Stock Scan ─────────────────────────────────────
export const scanSingleStock = (ticker: string, mode = 'weekly', useAI = true) =>
  api.get(`/api/scan/stock/${ticker}`, { params: { mode, use_ai: useAI } }).then(r => r.data);

// ── Budget Picks ──────────────────────────────────────────
export const fetchBudgetPicks = (budget = 20000, mode = 'weekly', maxPrice = 500) =>
  api.get('/api/budget-picks', { params: { budget, mode, max_price: maxPrice } }).then(r => r.data);

// ── Scan Progress ─────────────────────────────────────────
export const fetchScanProgress = (scanId: string) =>
  api.get(`/api/scans/progress/${scanId}`).then(r => r.data);
