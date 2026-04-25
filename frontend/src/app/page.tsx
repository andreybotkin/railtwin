/**
 * Main application page — a full-viewport MapLibre canvas with floating
 * glass-morphic controls. The train info sheet pops up in the bottom-right
 * whenever a train is selected.
 */

'use client';

import { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import { Loader2, Moon, Satellite, Search, Sun, Train } from 'lucide-react';
import { useTranslations } from 'next-intl';

import LanguageSwitcher from '@/components/LanguageSwitcher';
import { SearchPanel } from '@/components/Search';
import { StationInfoSheet, TrainInfoSheet } from '@/components/TrainInfo';
import { Button } from '@/components/ui';
import { useTheme } from '@/lib/hooks';

const RailMap = dynamic(() => import('@/components/Map/RailMap'), {
  ssr: false,
  loading: () => (
    <div className="flex h-full w-full items-center justify-center" style={{ background: 'var(--page-bg, #f4f4f5)' }}>
      <Loader2 className="h-8 w-8 animate-spin text-zinc-500" />
    </div>
  ),
});

const THEME_ICONS = {
  light: Moon,
  dark: Satellite,
  satellite: Sun,
} as const;

const THEME_TITLES = {
  light: 'Switch to dark mode',
  dark: 'Switch to satellite view',
  satellite: 'Switch to light mode',
} as const;

export default function HomePage() {
  const t = useTranslations();
  const { theme, cycleTheme } = useTheme();
  const [searchOpen, setSearchOpen] = useState(false);

  const ThemeIcon = THEME_ICONS[theme];

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
    <div
      className="relative h-dvh overflow-hidden"
      style={{ background: 'var(--page-bg)', color: 'var(--panel-text)' }}
    >
      <div className="absolute inset-0">
        <RailMap />
      </div>

      <header className="pointer-events-none absolute inset-x-0 top-0 z-[900] p-3 sm:p-4">
        <div
          className="pointer-events-auto mx-auto flex w-full max-w-5xl items-center justify-between gap-3 rounded-3xl px-3 py-2 backdrop-blur-xl"
          style={{
            background: 'var(--panel-bg)',
            border: '1px solid var(--panel-border)',
            boxShadow: 'var(--panel-shadow)',
          }}
        >
          <div className="flex min-w-0 items-center gap-2">
            <div
              className="flex h-9 w-9 items-center justify-center rounded-2xl"
              style={{ background: 'var(--header-logo-bg)', color: 'var(--header-logo-text)' }}
            >
              <Train className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <h1
                className="truncate text-sm font-semibold tracking-tight"
                style={{ color: 'var(--panel-text)' }}
              >
                {t('appTitle')}
              </h1>
              <p className="hidden text-xs sm:block" style={{ color: 'var(--panel-subtext)' }}>
                {t('header.subtitle')}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setSearchOpen(true)}
              title="Search (⌘K)"
              aria-label="Open search"
              className="rounded-2xl transition-colors"
              style={{ color: 'var(--panel-subtext)' }}
            >
              <Search className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={cycleTheme}
              title={THEME_TITLES[theme]}
              aria-label={THEME_TITLES[theme]}
              className="rounded-2xl transition-colors"
              style={{ color: 'var(--panel-subtext)' }}
            >
              <ThemeIcon className="h-4 w-4" />
            </Button>
            <LanguageSwitcher />
          </div>
        </div>
      </header>

      <TrainInfoSheet />
      <StationInfoSheet />
      <SearchPanel open={searchOpen} onClose={() => setSearchOpen(false)} />
    </div>
  );
}
