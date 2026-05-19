/**
 * Main application page — a full-viewport MapLibre canvas with floating
 * glass-morphic controls. The train info sheet pops up in the bottom-right
 * whenever a train is selected.
 */

'use client';

import { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import {
  Database,
  Loader2,
  LocateFixed,
  Moon,
  Satellite,
  Search,
  Sun,
  Train,
} from 'lucide-react';
import { useTranslations } from 'next-intl';

import LanguageSwitcher from '@/components/LanguageSwitcher';
import { SearchPanel } from '@/components/Search';
import { StationInfoSheet, TrainInfoSheet } from '@/components/TrainInfo';
import { Button } from '@/components/ui';
import { useTheme } from '@/lib/hooks';

const RailMap = dynamic(() => import('@/components/Map/RailMap'), {
  ssr: false,
  loading: () => (
    <div
      className="flex h-full w-full items-center justify-center"
      style={{ background: 'var(--page-bg, #f4f4f5)' }}
    >
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
  const [locateMap, setLocateMap] = useState<(() => void) | null>(null);
  const [cookiesConsentOpen, setCookiesConsentOpen] = useState(false);

  const mapSourceSummary =
    theme === 'satellite'
      ? t('footer.mapSources.satellite')
      : theme === 'dark'
        ? t('footer.mapSources.dark')
        : t('footer.mapSources.light');

  const footerTextColor =
    theme === 'light' ? 'rgba(15,23,42,0.96)' : 'rgba(248,250,252,0.96)';
  const footerMutedColor =
    theme === 'light' ? 'rgba(15,23,42,0.82)' : 'rgba(226,232,240,0.9)';
  const footerTextShadow =
    theme === 'light'
      ? '0 1px 2px rgba(255,255,255,0.96), 0 0 10px rgba(255,255,255,0.92)'
      : '0 1px 2px rgba(2,6,23,0.98), 0 0 10px rgba(2,6,23,0.92)';

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

  useEffect(() => {
    let frameId = 0;

    try {
      const nextOpen = localStorage.getItem('rt-cookie-consent') !== 'accepted';
      frameId = window.requestAnimationFrame(() => {
        setCookiesConsentOpen(nextOpen);
      });
    } catch {
      frameId = window.requestAnimationFrame(() => {
        setCookiesConsentOpen(true);
      });
    }

    return () => {
      if (frameId) {
        window.cancelAnimationFrame(frameId);
      }
    };
  }, []);

  const acceptCookies = () => {
    try {
      localStorage.setItem('rt-cookie-consent', 'accepted');
    } catch {
      // Ignore storage failures; hide the banner for this session anyway.
    }
    setCookiesConsentOpen(false);
  };

  return (
    <div
      className="relative h-dvh overflow-hidden"
      style={{ background: 'var(--page-bg)', color: 'var(--panel-text)' }}
    >
      <div className="absolute inset-0">
        <RailMap onLocateReady={(fn) => setLocateMap(() => fn)} />
      </div>

      <header className="pointer-events-none absolute inset-x-0 top-0 z-[900] p-3 sm:p-4">
        <div
          className="pointer-events-auto mx-auto flex w-full max-w-5xl items-center justify-between gap-3 rounded-3xl px-3 py-2 backdrop-blur-xl"
          style={{
            background: 'var(--panel-bg)',
            border:
              theme === 'light'
                ? '1px solid rgba(148,163,184,0.45)'
                : '1px solid var(--panel-border)',
            boxShadow: 'var(--panel-shadow)',
          }}
        >
          <div className="flex min-w-0 items-center gap-2">
            <div
              className="flex h-9 w-9 items-center justify-center rounded-2xl"
              style={{
                background: 'var(--header-logo-bg)',
                color: 'var(--header-logo-text)',
              }}
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
              <p
                className="hidden text-xs sm:block"
                style={{ color: 'var(--panel-subtext)' }}
              >
                {t('header.subtitle')}
              </p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <Button
              onClick={() => setSearchOpen(true)}
              title="Search (⌘K)"
              aria-label="Open search"
              className="rounded-2xl transition-colors"
              style={{ color: 'var(--panel-subtext)' }}
            >
              <Search className="h-4 w-4" />
            </Button>
            <Button
              asChild
              variant="ghost"
              size="icon"
              title={t('header.openData.buttonLabel')}
              aria-label={t('header.openData.buttonLabel')}
              className="rounded-2xl transition-colors"
              style={{ color: 'var(--panel-subtext)' }}
            >
              <Link href="/open-data">
                <Database className="h-4 w-4" />
              </Link>
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
            <Button
              variant="ghost"
              size="icon"
              onClick={() => locateMap?.()}
              disabled={!locateMap}
              title="Go to current location"
              aria-label="Go to current location"
              className="rounded-2xl transition-colors"
              style={{ color: 'var(--panel-subtext)' }}
            >
              <LocateFixed className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </header>

      <div className="pointer-events-none absolute inset-x-0 bottom-0 z-[880] p-2 sm:p-3">
        <div className="flex w-full flex-col items-start gap-1.5">
          {cookiesConsentOpen && (
            <div
              className="pointer-events-auto flex w-auto max-w-[calc(100vw-1rem)] items-center gap-2 rounded-xl border px-2.5 py-1.5 text-[10px] leading-4 backdrop-blur-xl sm:max-w-[30rem]"
              style={{
                background: 'var(--panel-bg-strong)',
                borderColor: 'var(--panel-border)',
                boxShadow: 'var(--panel-shadow)',
              }}
            >
              <p
                className="min-w-0 flex-1 truncate"
                style={{ color: 'var(--panel-subtext)' }}
                title={t('cookiesBanner.message')}
              >
                <span
                  className="font-medium"
                  style={{ color: 'var(--panel-text)' }}
                >
                  {t('cookiesBanner.label')}:
                </span>{' '}
                {t('cookiesBanner.message')}
              </p>
              <Button
                size="sm"
                variant="secondary"
                onClick={acceptCookies}
                className="h-6 shrink-0 rounded-lg px-2.5 text-[10px]"
                style={{
                  background: 'var(--header-logo-bg)',
                  color: 'var(--header-logo-text)',
                }}
              >
                {t('cookiesBanner.accept')}
              </Button>
            </div>
          )}

          <footer
            className="pointer-events-auto mr-auto flex max-w-[calc(100vw-1rem)] items-center gap-1.5 overflow-hidden px-0 py-0 text-[9px] leading-4 sm:max-w-[calc(100vw-2rem)] sm:text-[10px]"
            style={{
              background: 'transparent',
              border: 'none',
              boxShadow: 'none',
            }}
          >
            <p
              className="min-w-0 flex-1 truncate"
              style={{ color: footerMutedColor, textShadow: footerTextShadow }}
              title={`${t('footer.mapSummaryLabel')}: ${mapSourceSummary} · ${t('footer.leafletSummary')}`}
            >
              <span
                className="font-medium"
                style={{ color: footerTextColor, textShadow: footerTextShadow }}
              >
                {t('footer.mapSummaryLabel')}:
              </span>{' '}
              {mapSourceSummary} · {t('footer.leafletSummary')}
            </p>
            <div className="flex shrink-0 items-center gap-1.5 whitespace-nowrap">
              <Link
                href="/privacy-policy"
                className="transition-opacity hover:opacity-80"
                style={{ color: footerTextColor, textShadow: footerTextShadow }}
              >
                {t('footer.privacyPolicy')}
              </Link>
              <span
                aria-hidden="true"
                style={{
                  color: footerMutedColor,
                  textShadow: footerTextShadow,
                }}
              >
                |
              </span>
              <Link
                href="/terms-of-service"
                className="transition-opacity hover:opacity-80"
                style={{ color: footerTextColor, textShadow: footerTextShadow }}
              >
                {t('footer.termsOfService')}
              </Link>
            </div>
          </footer>
        </div>
      </div>

      <TrainInfoSheet />
      <StationInfoSheet />
      <SearchPanel open={searchOpen} onClose={() => setSearchOpen(false)} />
    </div>
  );
}
