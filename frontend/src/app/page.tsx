/**
 * Main application page.
 */

'use client';

import { useState } from 'react';
import { Train, Moon, Sun, Info, X } from 'lucide-react';

import MapContainer from '@/components/Map/MapContainer';
import { TrainInfoPanel } from '@/components/TrainInfo';
import { SchedulePanel } from '@/components/Schedule';
import { Button } from '@/components/ui';
import { useDarkMode } from '@/lib/hooks';
import { cn } from '@/lib/utils';

export default function HomePage() {
  const [selectedTrainId, setSelectedTrainId] = useState<number | null>(null);
  const [showLeftPanel, setShowLeftPanel] = useState(false);
  const [showRightPanel, setShowRightPanel] = useState(false);
  const { isDark, toggle: toggleDarkMode } = useDarkMode();

  return (
    <div className="flex h-dvh min-h-0 flex-col overflow-hidden bg-background">
      {/* Header */}
      <header className="flex h-14 items-center justify-between border-b bg-background px-3 sm:px-4">
        <div className="flex items-center gap-2 sm:gap-3">
          <Train className="h-6 w-6 text-primary" />
          <h1 className="max-w-[220px] truncate text-sm font-bold sm:max-w-none sm:text-lg">
            Thailand Railway Digital Twin
          </h1>
        </div>

        <div className="flex items-center gap-1 sm:gap-2">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setShowLeftPanel(!showLeftPanel)}
            title="Toggle train panel"
            aria-label="Toggle train panel"
          >
            <Train className="h-5 w-5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setShowRightPanel(!showRightPanel)}
            title="Toggle schedule panel"
            aria-label="Toggle schedule panel"
          >
            <Info className="h-5 w-5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={toggleDarkMode}
            title="Toggle dark mode"
          >
            {isDark ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
          </Button>
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
              selectedTrainId={selectedTrainId}
              onTrainSelect={setSelectedTrainId}
            />
          )}
        </aside>

        {/* Map */}
        <main className="relative flex-1 min-w-0">
          <MapContainer className="absolute inset-0" />

          {/* Map overlay info */}
          <div className="absolute bottom-2 left-2 right-2 rounded-lg bg-background/90 p-2 text-xs shadow-lg backdrop-blur sm:bottom-4 sm:left-4 sm:right-auto sm:p-3 sm:text-sm">
            <div className="grid grid-cols-2 gap-x-3 gap-y-1 sm:flex sm:items-center sm:gap-4">
              <div className="flex items-center gap-1">
                <div className="h-3 w-3 rounded-full bg-northern" />
                <span>Northern</span>
              </div>
              <div className="flex items-center gap-1">
                <div className="h-3 w-3 rounded-full bg-northeastern" />
                <span>Northeastern</span>
              </div>
              <div className="flex items-center gap-1">
                <div className="h-3 w-3 rounded-full bg-southern" />
                <span>Southern</span>
              </div>
              <div className="flex items-center gap-1">
                <div className="h-3 w-3 rounded-full bg-eastern" />
                <span>Eastern</span>
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
          className={cn(
            'absolute inset-0 z-[1000] bg-black/30 transition-opacity duration-300 lg:hidden',
            showLeftPanel || showRightPanel ? 'opacity-100' : 'pointer-events-none opacity-0'
          )}
          onClick={() => {
            setShowLeftPanel(false);
            setShowRightPanel(false);
          }}
        />

        <aside
          className={cn(
            'absolute left-0 top-0 z-[1001] h-full w-[88vw] max-w-sm border-r bg-background shadow-xl transition-transform duration-300 lg:hidden',
            showLeftPanel ? 'translate-x-0' : '-translate-x-full'
          )}
        >
          <div className="flex h-12 items-center justify-between border-b px-3">
            <span className="text-sm font-semibold">Trains</span>
            <Button variant="ghost" size="icon" onClick={() => setShowLeftPanel(false)}>
              <X className="h-4 w-4" />
            </Button>
          </div>
          <div className="h-[calc(100%-3rem)]">
            <TrainInfoPanel
              selectedTrainId={selectedTrainId}
              onTrainSelect={setSelectedTrainId}
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
            <span className="text-sm font-semibold">Schedule</span>
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
      <footer className="hidden h-8 items-center justify-between border-t bg-background px-4 text-xs text-muted-foreground md:flex">
        <span>© 2026 Thailand Railway Digital Twin</span>
        <span>Data source: State Railway of Thailand (SRT)</span>
      </footer>
    </div>
  );
}
