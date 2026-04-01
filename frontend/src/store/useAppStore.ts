import { create } from 'zustand';
import type { ScanResult, ScanSummary } from '@/lib/types';

interface AppState {
  // Scan state
  currentScanId: string | null;
  scanSummary: ScanSummary | null;
  scanResults: ScanResult[];
  isScanning: boolean;
  scanProgress: { current: number; total: number; stock: string } | null;

  // Settings
  capital: number;
  minConfidence: number;
  maxPositions: number;
  holdingMode: 'weekly' | 'monthly';
  scope: string;
  selectedSectors: string[];
  useAI: boolean;

  // Actions
  setScanResults: (id: string, summary: ScanSummary, results: ScanResult[]) => void;
  setIsScanning: (v: boolean) => void;
  setScanProgress: (p: { current: number; total: number; stock: string } | null) => void;
  setCapital: (v: number) => void;
  setMinConfidence: (v: number) => void;
  setMaxPositions: (v: number) => void;
  setHoldingMode: (v: 'weekly' | 'monthly') => void;
  setScope: (v: string) => void;
  setSelectedSectors: (v: string[]) => void;
  setUseAI: (v: boolean) => void;
}

export const useAppStore = create<AppState>((set) => ({
  currentScanId: null,
  scanSummary: null,
  scanResults: [],
  isScanning: false,
  scanProgress: null,

  capital: 100000,
  minConfidence: 65,
  maxPositions: 5,
  holdingMode: 'weekly',
  scope: 'all',
  selectedSectors: [],
  useAI: true,

  setScanResults: (id, summary, results) => set({ currentScanId: id, scanSummary: summary, scanResults: results }),
  setIsScanning: (v) => set({ isScanning: v }),
  setScanProgress: (p) => set({ scanProgress: p }),
  setCapital: (v) => set({ capital: v }),
  setMinConfidence: (v) => set({ minConfidence: v }),
  setMaxPositions: (v) => set({ maxPositions: v }),
  setHoldingMode: (v) => set({ holdingMode: v }),
  setScope: (v) => set({ scope: v }),
  setSelectedSectors: (v) => set({ selectedSectors: v }),
  setUseAI: (v) => set({ useAI: v }),
}));
