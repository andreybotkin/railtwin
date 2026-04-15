/**
 * Main application page.
 */

'use client';

import Link from 'next/link';
import { useState, useEffect, useCallback, useRef } from 'react';
import { Train, Sun, Moon, Globe, Info, X, Bug, Waypoints, Layers3 } from 'lucide-react';
import { useTranslations } from 'next-intl';

import MapContainer from '@/components/Map/MapContainer';
import { TrainInfoPanel } from '@/components/TrainInfo';
import { SchedulePanel } from '@/components/Schedule';
import LanguageSwitcher from '@/components/LanguageSwitcher';
import { Button } from '@/components/ui';
import { useMapTopicStore } from '@/lib/stores/map-topic-store';
import { cn } from '@/lib/utils';

const THEME_OPTIONS = [
  { key: 'railway', Icon: Sun },
  { key: 'dark', Icon: Moon },
  { key: 'satellite', Icon: Globe },
] as const;
type ThemeKey = (typeof THEME_OPTIONS)[number]['key'];

export default function HomePage() {
  const [selectedTrainId, setSelectedTrainId] = useState<number | null>(null);
  const [showLeftPanel, setShowLeftPanel] = useState(false);
  const [showRightPanel, setShowRightPanel] = useState(false);
  const [trainViewportBbox, setTrainViewportBbox] = useState<string | null>(null);

  // When a train is selected from the map, automatically open the info panel
  const handleTrainSelect = useCallback((id: number | null) => {
    setSelectedTrainId(id);
    if (id !== null) {
      setShowLeftPanel(true);
    } else {
      setShowLeftPanel(false);
    }
  }, []);
  const [themeOpen, setThemeOpen] = useState(false);
  const themeRef = useRef<HTMLDivElement>(null);
  const activeTopicKey = useMapTopicStore((s) => s.activeTopicKey);
  const setActiveTopic = useMapTopicStore((s) => s.setActiveTopic);
  const t = useTranslations();

  const THEME_LABELS: Record<ThemeKey, string> = {
    railway: t('topics.railway'),
    dark: t('topics.dark'),
    satellite: t('topics.satellite'),
  };

  // Restore saved theme on mount and apply dark class
  useEffect(() => {
    const saved = (localStorage.getItem('mapTheme') ?? 'railway') as ThemeKey;
    setActiveTopic(saved);
    document.documentElement.classList.toggle('dark', saved === 'dark');
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Close theme dropdown on outside click
  useEffect(() => {
    const handleOutside = (e: MouseEvent) => {
      if (themeRef.current && !themeRef.current.contains(e.target as Node)) {
        setThemeOpen(false);
      }
    };
    if (themeOpen) document.addEventListener('mousedown', handleOutside);
    return () => document.removeEventListener('mousedown', handleOutside);
  }, [themeOpen]);

  const handleThemeSelect = useCallback(
    (key: ThemeKey) => {
      setActiveTopic(key);
      document.documentElement.classList.toggle('dark', key === 'dark');
      localStorage.setItem('mapTheme', key);
      setThemeOpen(false);
    },
    [setActiveTopic],
  );

  const activeThemeEntry =
    THEME_OPTIONS.find((th) => th.key === activeTopicKey) ?? THEME_OPTIONS[0];
  const ActiveThemeIcon = activeThemeEntry.Icon;

  const toggleTrainPanel = useCallback(() => {
    setShowLeftPanel((current) => {
      const next = !current;
      if (next) setShowRightPanel(false);
      return next;
    });
  }, []);

  const toggleInfoPanel = useCallback(() => {
    setShowRightPanel((current) => {
      const next = !current;
      if (next) setShowLeftPanel(false);
      return next;
    });
  }, []);

  return (
    <div className="relative h-dvh overflow-hidden bg-[#e7e2d7] text-zinc-950">
      <main className="absolute inset-0">
        <MapContainer
          className="absolute inset-0"
          selectedTrainId={selectedTrainId}
          onTrainSelect={handleTrainSelect}
          onViewportChange={setTrainViewportBbox}
        />

        <div className="pointer-events-none absolute inset-x-0 top-0 z-[900] bg-[linear-gradient(180deg,rgba(20,20,18,0.45)_0%,rgba(20,20,18,0.0)_100%)] px-3 pb-10 pt-3 sm:px-4">
          <header className="pointer-events-auto mx-auto flex w-full max-w-7xl items-center justify-between gap-3 rounded-[24px] border border-white/55 bg-[rgba(246,243,236,0.86)] px-3 py-2 shadow-[0_20px_45px_-30px_rgba(15,23,42,0.55)] backdrop-blur-xl sm:px-4">
            <div className="flex min-w-0 items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-zinc-950 text-white shadow-sm">
                <Train className="h-5 w-5" />
              </div>
              <div className="min-w-0">
                <h1 className="truncate text-sm font-semibold tracking-tight text-zinc-950 sm:text-base">
                  {t('appTitle')}
                </h1>
                <p className="hidden text-xs text-zinc-500 sm:block">
                  Live trains, stations and routes in one mobile-friendly map
                </p>
              </div>
            </div>

            <div className="flex items-center gap-1 sm:gap-2">
              <Button
                variant="ghost"
                size="icon"
                onClick={toggleTrainPanel}
                title={t('header.toggleTrainPanel')}
                aria-label={t('header.toggleTrainPanel')}
                className="rounded-2xl text-zinc-700 hover:bg-zinc-950 hover:text-white"
              >
                <Train className="h-5 w-5" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                onClick={toggleInfoPanel}
                title={t('header.toggleSchedulePanel')}
                aria-label={t('header.toggleSchedulePanel')}
                className="rounded-2xl text-zinc-700 hover:bg-zinc-950 hover:text-white"
              >
                <Layers3 className="h-5 w-5" />
              </Button>

              <div ref={themeRef} className="relative">
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setThemeOpen((o) => !o)}
                  title="Map theme"
                  aria-label="Map theme"
                  className="rounded-2xl text-zinc-700 hover:bg-zinc-950 hover:text-white"
                >
                  <ActiveThemeIcon className="h-5 w-5" />
                </Button>
                {themeOpen && (
                  <div className="absolute right-0 top-full z-[2000] mt-2 min-w-[176px] rounded-2xl border border-zinc-200 bg-[rgba(252,250,246,0.96)] py-1.5 shadow-2xl backdrop-blur-xl">
                    {THEME_OPTIONS.map(({ key, Icon }) => (
                      <button
                        key={key}
                        onClick={() => handleThemeSelect(key)}
                        className={cn(
                          'flex w-full items-center gap-2.5 px-3 py-2 text-sm transition-colors',
                          activeTopicKey === key
                            ? 'bg-zinc-950 font-medium text-white'
                            : 'text-zinc-700 hover:bg-zinc-100 hover:text-zinc-950',
                        )}
                      >
                        <Icon className="h-4 w-4 shrink-0" />
                        {THEME_LABELS[key]}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <div className="hidden items-center gap-1 sm:flex">
                <Button
                  asChild
                  variant="ghost"
                  size="icon"
                  title="Gateway debug"
                  aria-label="Gateway debug"
                  className="rounded-2xl text-zinc-700 hover:bg-zinc-950 hover:text-white"
                >
                  <Link href="/debug/gateway">
                    <Bug className="h-5 w-5" />
                  </Link>
                </Button>

                <Button
                  asChild
                  variant="ghost"
                  size="icon"
                  title="Train point debug"
                  aria-label="Train point debug"
                  className="rounded-2xl text-zinc-700 hover:bg-zinc-950 hover:text-white"
                >
                  <Link href="/debug/gateway/trains">
                    <Waypoints className="h-5 w-5" />
                  </Link>
                </Button>
              </div>

              <LanguageSwitcher className="rounded-2xl text-zinc-700 hover:bg-zinc-950 hover:text-white" />
            </div>
          </header>
        </div>

        <div className="pointer-events-none absolute inset-x-0 bottom-0 z-[850] p-3 pb-4 sm:p-4">
          <div className="mx-auto flex max-w-7xl flex-col gap-3">
            <div className="pointer-events-auto flex items-center justify-between gap-3 rounded-[24px] border border-white/60 bg-[rgba(250,247,241,0.84)] px-4 py-3 shadow-[0_18px_40px_-28px_rgba(15,23,42,0.55)] backdrop-blur-xl sm:max-w-max">
              <div>
                <p className="text-[10px] uppercase tracking-[0.24em] text-zinc-500">Map legend</p>
                <div className="mt-1 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-zinc-700 sm:flex sm:items-center sm:gap-4 sm:text-sm">
                  <div className="flex items-center gap-1.5">
                    <div className="h-2.5 w-2.5 rounded-full bg-northern" />
                    <span>{t('map.northern')}</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <div className="h-2.5 w-2.5 rounded-full bg-northeastern" />
                    <span>{t('map.northeastern')}</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <div className="h-2.5 w-2.5 rounded-full bg-southern" />
                    <span>{t('map.southern')}</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <div className="h-2.5 w-2.5 rounded-full bg-eastern" />
                    <span>{t('map.eastern')}</span>
                  </div>
                </div>
              </div>
            </div>

            <div className="pointer-events-auto mx-auto flex w-full max-w-md items-center justify-center gap-2 rounded-[26px] border border-white/60 bg-[rgba(18,18,16,0.78)] p-2 text-white shadow-[0_18px_40px_-28px_rgba(15,23,42,0.75)] backdrop-blur-xl lg:hidden">
              <Button
                variant="ghost"
                onClick={toggleTrainPanel}
                className={cn(
                  'flex-1 rounded-2xl px-4 py-2 text-sm text-white hover:bg-white/10 hover:text-white',
                  showLeftPanel && 'bg-white/12'
                )}
              >
                <Train className="mr-2 h-4 w-4" />
                Trains
              </Button>
              <Button
                variant="ghost"
                onClick={toggleInfoPanel}
                className={cn(
                  'flex-1 rounded-2xl px-4 py-2 text-sm text-white hover:bg-white/10 hover:text-white',
                  showRightPanel && 'bg-white/12'
                )}
              >
                <Info className="mr-2 h-4 w-4" />
                Info
              </Button>
            </div>
          </div>
        </div>
      </main>

      <div className="pointer-events-none absolute inset-0 z-[920]">
        <aside
          className={cn(
            'pointer-events-auto absolute bottom-4 left-4 top-24 hidden overflow-hidden rounded-[28px] border border-white/70 bg-[rgba(252,249,242,0.92)] shadow-[0_22px_60px_-34px_rgba(15,23,42,0.55)] backdrop-blur-xl transition-all duration-300 lg:block',
            showLeftPanel ? 'w-[22rem] opacity-100' : 'w-0 border-transparent opacity-0'
          )}
        >
          {showLeftPanel && (
            <TrainInfoPanel
              bbox={trainViewportBbox}
              selectedTrainId={selectedTrainId}
              onTrainSelect={handleTrainSelect}
            />
          )}
        </aside>
        <aside
          className={cn(
            'pointer-events-auto absolute bottom-4 right-4 top-24 hidden overflow-hidden rounded-[28px] border border-white/70 bg-[rgba(252,249,242,0.92)] shadow-[0_22px_60px_-34px_rgba(15,23,42,0.55)] backdrop-blur-xl transition-all duration-300 lg:block',
            showRightPanel ? 'w-[22rem] opacity-100' : 'w-0 border-transparent opacity-0'
          )}
        >
          {showRightPanel && <SchedulePanel />}
        </aside>
      </div>

      <div className="pointer-events-none absolute inset-0 z-[910] lg:hidden">
        <div
          role="button"
          tabIndex={0}
          aria-label="Close panel"
          className={cn(
            'pointer-events-auto absolute inset-0 bg-black/30 transition-opacity duration-300',
            showLeftPanel || showRightPanel ? 'opacity-100' : 'pointer-events-none opacity-0'
          )}
          onClick={() => {
            setShowLeftPanel(false);
            setShowRightPanel(false);
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              setShowLeftPanel(false);
              setShowRightPanel(false);
            }
          }}
        />

        <aside
          className={cn(
            'pointer-events-auto absolute inset-x-0 bottom-0 z-[1001] h-[68dvh] rounded-t-[30px] border-t border-white/70 bg-[rgba(252,249,242,0.96)] shadow-[0_-20px_60px_-30px_rgba(15,23,42,0.65)] backdrop-blur-xl transition-transform duration-300',
            showLeftPanel ? 'translate-y-0' : 'translate-y-full'
          )}
        >
          <div className="mx-auto mt-2 h-1.5 w-14 rounded-full bg-zinc-300" />
          <div className="flex h-12 items-center justify-between border-b border-zinc-200 px-4">
            <span className="text-sm font-semibold text-zinc-950">{t('trains.title')}</span>
            <Button variant="ghost" size="icon" onClick={() => setShowLeftPanel(false)}>
              <X className="h-4 w-4" />
            </Button>
          </div>
          <div className="h-[calc(100%-3rem)]">
            <TrainInfoPanel
              bbox={trainViewportBbox}
              selectedTrainId={selectedTrainId}
              onTrainSelect={handleTrainSelect}
            />
          </div>
        </aside>

        <aside
          className={cn(
            'pointer-events-auto absolute inset-x-0 bottom-0 z-[1001] h-[68dvh] rounded-t-[30px] border-t border-white/70 bg-[rgba(252,249,242,0.96)] shadow-[0_-20px_60px_-30px_rgba(15,23,42,0.65)] backdrop-blur-xl transition-transform duration-300',
            showRightPanel ? 'translate-y-0' : 'translate-y-full'
          )}
        >
          <div className="mx-auto mt-2 h-1.5 w-14 rounded-full bg-zinc-300" />
          <div className="flex h-12 items-center justify-between border-b border-zinc-200 px-4">
            <span className="text-sm font-semibold text-zinc-950">{t('schedule.title')}</span>
            <Button variant="ghost" size="icon" onClick={() => setShowRightPanel(false)}>
              <X className="h-4 w-4" />
            </Button>
          </div>
          <div className="h-[calc(100%-3rem)]">
            <SchedulePanel />
          </div>
        </aside>
      </div>

      {/* Footer */}
      <footer className="hidden h-8 items-center justify-between border-t border-zinc-800 bg-black px-4 text-xs text-gray-400 md:flex">
        <span>{t('footer.copyright')}</span>
        <span>{t('footer.dataSource')}</span>
      </footer>
    </div>
  );
}
