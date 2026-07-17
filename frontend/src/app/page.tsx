/**
 * Main application page — a full-viewport MapLibre canvas with floating
 * glass-morphic controls. The train info sheet pops up in the bottom-right
 * whenever a train is selected.
 */

'use client';

import { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import Script from 'next/script';
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

const GA_MEASUREMENT_ID = 'G-M6ZWFRZ4BG';
const COOKIE_CONSENT_KEY = 'rt-cookie-consent';

export default function HomePage() {
  const t = useTranslations();
  const { theme, cycleTheme } = useTheme();
  const [searchOpen, setSearchOpen] = useState(false);
  const [locateMap, setLocateMap] = useState<(() => void) | null>(null);
  const [cookiesConsentOpen, setCookiesConsentOpen] = useState(false);
  const [analyticsEnabled, setAnalyticsEnabled] = useState(false);

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
      const consent = localStorage.getItem(COOKIE_CONSENT_KEY);
      frameId = window.requestAnimationFrame(() => {
        setAnalyticsEnabled(consent === 'accepted');
        setCookiesConsentOpen(consent !== 'accepted' && consent !== 'declined');
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
      localStorage.setItem(COOKIE_CONSENT_KEY, 'accepted');
    } catch {
      // Ignore storage failures; hide the banner for this session anyway.
    }
    setAnalyticsEnabled(true);
    setCookiesConsentOpen(false);
  };

  const declineCookies = () => {
    try {
      localStorage.setItem(COOKIE_CONSENT_KEY, 'declined');
    } catch {
      // Keep the choice for this session when storage is unavailable.
    }
    const flags = window as unknown as Record<string, unknown>;
    flags[`ga-disable-${GA_MEASUREMENT_ID}`] = true;
    setAnalyticsEnabled(false);
    setCookiesConsentOpen(false);
  };

  return (
    <div
      className="relative h-dvh overflow-hidden"
      style={{ background: 'var(--page-bg)', color: 'var(--panel-text)' }}
    >
      {analyticsEnabled && (
        <>
          <Script
            src={`https://www.googletagmanager.com/gtag/js?id=${GA_MEASUREMENT_ID}`}
            strategy="afterInteractive"
          />
          <Script id="ga-init" strategy="afterInteractive">
            {`
              window['ga-disable-${GA_MEASUREMENT_ID}'] = false;
              window.dataLayer = window.dataLayer || [];
              function gtag(){dataLayer.push(arguments);}
              gtag('js', new Date());
              gtag('config', '${GA_MEASUREMENT_ID}');
            `}
          </Script>
        </>
      )}

      <div className="absolute inset-0">
        <RailMap onLocateReady={(fn) => setLocateMap(() => fn)} />
      </div>

      <header className="pointer-events-none absolute inset-x-0 top-0 z-[900] px-2 pt-[max(0.5rem,env(safe-area-inset-top))] sm:p-4">
        <div
          className="pointer-events-auto mx-auto flex w-full max-w-5xl items-center justify-between gap-1.5 rounded-2xl px-2 py-1.5 backdrop-blur-xl sm:gap-3 sm:rounded-3xl sm:px-3 sm:py-2"
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
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl sm:h-9 sm:w-9 sm:rounded-2xl"
              style={{
                background: 'var(--header-logo-bg)',
                color: 'var(--header-logo-text)',
              }}
            >
              <Train className="h-4 w-4" />
            </div>
            <div className="hidden min-w-0 min-[390px]:block">
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
          <div className="flex shrink-0 items-center gap-0.5 sm:gap-1">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setSearchOpen(true)}
              title="Search (⌘K)"
              aria-label="Open search"
              className="h-9 w-9 rounded-xl transition-colors sm:h-10 sm:w-10 sm:rounded-2xl"
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
              className="h-9 w-9 rounded-xl transition-colors sm:h-10 sm:w-10 sm:rounded-2xl"
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
              className="h-9 w-9 rounded-xl transition-colors sm:h-10 sm:w-10 sm:rounded-2xl"
              style={{ color: 'var(--panel-subtext)' }}
            >
              <ThemeIcon className="h-4 w-4" />
            </Button>
            <LanguageSwitcher className="h-9 w-9 rounded-xl sm:h-10 sm:w-10 sm:rounded-2xl" />
            <Button
              variant="ghost"
              size="icon"
              onClick={() => locateMap?.()}
              disabled={!locateMap}
              title="Go to current location"
              aria-label="Go to current location"
              className="h-9 w-9 rounded-xl transition-colors sm:h-10 sm:w-10 sm:rounded-2xl"
              style={{ color: 'var(--panel-subtext)' }}
            >
              <LocateFixed className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </header>

      <div className="pointer-events-none absolute inset-x-0 bottom-0 z-[880] px-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] sm:p-3">
        <div className="flex w-full flex-col items-start gap-1.5">
          {cookiesConsentOpen && (
            <div
              className="pointer-events-auto flex w-full flex-col items-stretch gap-2 rounded-2xl border px-3 py-2.5 text-xs leading-5 backdrop-blur-xl sm:w-auto sm:max-w-[30rem] sm:flex-row sm:items-center sm:rounded-xl sm:px-2.5 sm:py-1.5 sm:text-[10px] sm:leading-4"
              style={{
                background: 'var(--panel-bg-strong)',
                borderColor: 'var(--panel-border)',
                boxShadow: 'var(--panel-shadow)',
              }}
            >
              <p
                className="min-w-0 flex-1 sm:truncate"
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
              <div className="flex gap-1.5 self-end">
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={declineCookies}
                  className="h-8 rounded-xl px-3 text-xs sm:h-6 sm:rounded-lg sm:px-2.5 sm:text-[10px]"
                  style={{ color: 'var(--panel-subtext)' }}
                >
                  {t('cookiesBanner.decline')}
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={acceptCookies}
                  className="h-8 rounded-xl px-3 text-xs sm:h-6 sm:rounded-lg sm:px-2.5 sm:text-[10px]"
                  style={{
                    background: 'var(--header-logo-bg)',
                    color: 'var(--header-logo-text)',
                  }}
                >
                  {t('cookiesBanner.accept')}
                </Button>
              </div>
            </div>
          )}

          <footer
            className="pointer-events-auto mr-auto flex w-full max-w-[calc(100vw-1rem)] flex-col items-start gap-0.5 overflow-hidden px-0 py-0 text-[9px] leading-4 sm:max-w-[calc(100vw-2rem)] sm:flex-row sm:items-center sm:gap-1.5 sm:text-[10px]"
            style={{
              background: 'transparent',
              border: 'none',
              boxShadow: 'none',
            }}
          >
            <p
              className="min-w-0 flex-1 truncate"
              style={{ color: footerMutedColor, textShadow: footerTextShadow }}
              title={`${t('footer.copyright')} · ${t('footer.dataSource')} · ${t('footer.mapSummaryLabel')}: ${mapSourceSummary} · ${t('footer.leafletSummary')}`}
            >
              <span
                className="font-medium"
                style={{ color: footerTextColor, textShadow: footerTextShadow }}
              >
                {t('footer.copyright')}
              </span>{' '}
              · {t('footer.dataSource')} · {t('footer.mapSummaryLabel')}:{' '}
              {mapSourceSummary} · {t('footer.leafletSummary')}
            </p>
            <div className="flex shrink-0 items-center gap-1.5 whitespace-nowrap">
              <button
                type="button"
                onClick={() => setCookiesConsentOpen(true)}
                className="transition-opacity hover:opacity-80"
                style={{ color: footerTextColor, textShadow: footerTextShadow }}
              >
                {t('cookiesBanner.settings')}
              </button>
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
