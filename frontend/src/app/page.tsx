/**
 * Main application page.
 */

'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { Train, Sun, Moon, Globe, Info, X } from 'lucide-react';
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

  return (
    <div className="flex h-dvh min-h-0 flex-col overflow-hidden bg-background">
      {/* Header */}
      <header className="flex h-14 items-center justify-between border-b border-zinc-800 bg-black px-3 sm:px-4">
        <div className="flex items-center gap-2 sm:gap-3">
          <Train className="h-6 w-6 text-white" />
          <h1 className="max-w-[220px] truncate text-sm font-bold text-white sm:max-w-none sm:text-lg">
            {t('appTitle')}
          </h1>
        </div>

        <div className="flex items-center gap-1 sm:gap-2">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setShowLeftPanel(!showLeftPanel)}
            title={t('header.toggleTrainPanel')}
            aria-label={t('header.toggleTrainPanel')}
            className="text-white hover:bg-zinc-800 hover:text-white"
          >
            <Train className="h-5 w-5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setShowRightPanel(!showRightPanel)}
            title={t('header.toggleSchedulePanel')}
            aria-label={t('header.toggleSchedulePanel')}
            className="text-white hover:bg-zinc-800 hover:text-white"
          >
            <Info className="h-5 w-5" />
          </Button>

          {/* Map theme switcher */}
          <div ref={themeRef} className="relative">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setThemeOpen((o) => !o)}
              title="Map theme"
              aria-label="Map theme"
              className="text-white hover:bg-zinc-800 hover:text-white"
            >
              <ActiveThemeIcon className="h-5 w-5" />
            </Button>
            {themeOpen && (
              <div className="absolute right-0 top-full z-[2000] mt-1 min-w-[160px] rounded-lg border border-zinc-700 bg-zinc-900 py-1 shadow-xl">
                {THEME_OPTIONS.map(({ key, Icon }) => (
                  <button
                    key={key}
                    onClick={() => handleThemeSelect(key)}
                    className={cn(
                      'flex w-full items-center gap-2.5 px-3 py-2 text-sm transition-colors',
                      activeTopicKey === key
                        ? 'bg-zinc-700 font-medium text-white'
                        : 'text-zinc-300 hover:bg-zinc-800 hover:text-white',
                    )}
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    {THEME_LABELS[key]}
                  </button>
                ))}
              </div>
            )}
          </div>

          <LanguageSwitcher className="text-white hover:bg-zinc-800 hover:text-white" />
        </div>
      </header>

      {/* Main content */}
      <div className="relative flex min-h-0 flex-1 overflow-hidden">
        {/* Desktop left panel */}
        <aside
          className={cn(
            'hidden border-r bg-background transition-all duration-300 overflow-hidden lg:block',
            showLeftPanel ? 'w-80' : 'w-0'
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

        {/* Map */}
        <main className="relative flex-1 min-w-0">
          <MapContainer
            className="absolute inset-0"
            selectedTrainId={selectedTrainId}
            onTrainSelect={handleTrainSelect}
            onViewportChange={setTrainViewportBbox}
          />

          {/* Map overlay info */}
          <div className="absolute bottom-2 left-2 right-2 rounded-lg bg-background/90 p-2 text-xs shadow-lg backdrop-blur sm:bottom-4 sm:left-4 sm:right-auto sm:p-3 sm:text-sm">
            <div className="grid grid-cols-2 gap-x-3 gap-y-1 sm:flex sm:items-center sm:gap-4">
              <div className="flex items-center gap-1">
                <div className="h-3 w-3 rounded-full bg-northern" />
                <span>{t('map.northern')}</span>
              </div>
              <div className="flex items-center gap-1">
                <div className="h-3 w-3 rounded-full bg-northeastern" />
                <span>{t('map.northeastern')}</span>
              </div>
              <div className="flex items-center gap-1">
                <div className="h-3 w-3 rounded-full bg-southern" />
                <span>{t('map.southern')}</span>
              </div>
              <div className="flex items-center gap-1">
                <div className="h-3 w-3 rounded-full bg-eastern" />
                <span>{t('map.eastern')}</span>
              </div>
            </div>
          </div>
        </main>

        {/* Desktop right panel */}
        <aside
          className={cn(
            'hidden border-l bg-background transition-all duration-300 overflow-hidden lg:block',
            showRightPanel ? 'w-80' : 'w-0'
          )}
        >
          {showRightPanel && <SchedulePanel />}
        </aside>

        {/* Mobile overlays */}
        <div
          role="button"
          tabIndex={0}
          aria-label="Close panel"
          className={cn(
            'absolute inset-0 z-[1000] bg-black/30 transition-opacity duration-300 lg:hidden',
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
            'absolute left-0 top-0 z-[1001] h-full w-[88vw] max-w-sm border-r bg-background shadow-xl transition-transform duration-300 lg:hidden',
            showLeftPanel ? 'translate-x-0' : '-translate-x-full'
          )}
        >
          <div className="flex h-12 items-center justify-between border-b px-3">
            <span className="text-sm font-semibold">{t('trains.title')}</span>
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
            'absolute right-0 top-0 z-[1001] h-full w-[88vw] max-w-sm border-l bg-background shadow-xl transition-transform duration-300 lg:hidden',
            showRightPanel ? 'translate-x-0' : 'translate-x-full'
          )}
        >
          <div className="flex h-12 items-center justify-between border-b px-3">
            <span className="text-sm font-semibold">{t('schedule.title')}</span>
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
