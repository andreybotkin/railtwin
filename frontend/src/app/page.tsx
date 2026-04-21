/**
 * Main application page — a full-viewport MapLibre canvas with floating
 * glass-morphic controls. The train info sheet pops up in the bottom-right
 * whenever a train is selected.
 */

'use client';

import { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import { Loader2, Moon, Search, Sun, Train } from 'lucide-react';
import { useTranslations } from 'next-intl';

import LanguageSwitcher from '@/components/LanguageSwitcher';
import { SearchPanel } from '@/components/Search';
import { StationInfoSheet, TrainInfoSheet } from '@/components/TrainInfo';
import { Button } from '@/components/ui';
import { ROUTE_COLORS } from '@/components/Map/map-style';
import { useDarkMode } from '@/lib/hooks';

const RailMap = dynamic(() => import('@/components/Map/RailMap'), {
  ssr: false,
  loading: () => (
    <div className="flex h-full w-full items-center justify-center bg-zinc-100">
      <Loader2 className="h-8 w-8 animate-spin text-zinc-500" />
    </div>
  ),
});

// const LEGEND_ROWS: Array<{ key: 'northern' | 'northeastern' | 'southern' | 'eastern'; label: string }> = [
//   { key: 'northern', label: 'Northern' },
//   { key: 'northeastern', label: 'Northeastern' },
//   { key: 'southern', label: 'Southern' },
//   { key: 'eastern', label: 'Eastern' },
// ];

export default function HomePage() {
  const t = useTranslations();
  const { isDark, toggle: toggleDark } = useDarkMode();
  const [searchOpen, setSearchOpen] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setSearchOpen((v) => !v);
      } else if (e.key === '/' && !searchOpen) {
        const target = e.target as HTMLElement | null;
        if (target && ['INPUT', 'TEXTAREA'].includes(target.tagName)) return;
        e.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [searchOpen]);

  return (
    <div className="relative h-dvh overflow-hidden bg-zinc-100 text-zinc-900">
      <div className="absolute inset-0">
        <RailMap />
      </div>

      <header className="pointer-events-none absolute inset-x-0 top-0 z-[900] p-3 sm:p-4">
        <div className="pointer-events-auto mx-auto flex w-full max-w-5xl items-center justify-between gap-3 rounded-3xl border border-white/55 bg-[rgba(252,249,242,0.86)] px-3 py-2 shadow-[0_18px_40px_-28px_rgba(15,23,42,0.55)] backdrop-blur-xl">
          <div className="flex min-w-0 items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-2xl bg-zinc-950 text-white">
              <Train className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <h1 className="truncate text-sm font-semibold tracking-tight text-zinc-950">
                {t('appTitle')}
              </h1>
              <p className="hidden text-xs text-zinc-500 sm:block">Live railway digital twin</p>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setSearchOpen(true)}
              title="Search (⌘K)"
              aria-label="Open search"
              className="rounded-2xl text-zinc-700 hover:bg-zinc-950 hover:text-white"
            >
              <Search className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={toggleDark}
              title="Toggle theme"
              aria-label="Toggle theme"
              className="rounded-2xl text-zinc-700 hover:bg-zinc-950 hover:text-white"
            >
              {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </Button>
            <LanguageSwitcher className="rounded-2xl text-zinc-700 hover:bg-zinc-950 hover:text-white" />
          </div>
        </div>
      </header>

      {/* <div className="pointer-events-auto absolute bottom-4 left-4 z-[850] hidden rounded-3xl border border-white/55 bg-[rgba(252,249,242,0.86)] px-4 py-3 text-xs shadow-[0_18px_40px_-28px_rgba(15,23,42,0.55)] backdrop-blur-xl sm:block">
        <p className="text-[10px] uppercase tracking-[0.24em] text-zinc-500">Legend</p>
        <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-zinc-700">
          {LEGEND_ROWS.map((row) => (
            <div key={row.key} className="flex items-center gap-1.5">
              <span
                className="h-2.5 w-2.5 rounded-full"
                style={{ backgroundColor: ROUTE_COLORS[row.key] }}
              />
              <span>{row.label}</span>
            </div>
          ))}
        </div>
      </div> */}

      <TrainInfoSheet />
      <StationInfoSheet />
      <SearchPanel open={searchOpen} onClose={() => setSearchOpen(false)} />
    </div>
  );
}
