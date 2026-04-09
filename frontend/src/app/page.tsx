/**
 * Main application page.
 */

'use client';

import { useState } from 'react';
import { Train, Moon, Sun, Info } from 'lucide-react';

import MapContainer from '@/components/Map/MapContainer';
import { TrainInfoPanel } from '@/components/TrainInfo';
import { SchedulePanel } from '@/components/Schedule';
import { Button } from '@/components/ui';
import { useDarkMode } from '@/lib/hooks';
import { cn } from '@/lib/utils';

export default function HomePage() {
  const [selectedTrainId, setSelectedTrainId] = useState<number | null>(null);
  const [showLeftPanel, setShowLeftPanel] = useState(true);
  const [showRightPanel, setShowRightPanel] = useState(true);
  const { isDark, toggle: toggleDarkMode } = useDarkMode();

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background">
      {/* Header */}
      <header className="flex h-14 items-center justify-between border-b bg-background px-4">
        <div className="flex items-center gap-3">
          <Train className="h-6 w-6 text-primary" />
          <h1 className="text-lg font-bold">Thailand Railway Digital Twin</h1>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setShowLeftPanel(!showLeftPanel)}
            title="Toggle train panel"
          >
            <Train className="h-5 w-5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setShowRightPanel(!showRightPanel)}
            title="Toggle info panel"
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
      <div className="flex flex-1 overflow-hidden">
        {/* Left panel - Train list */}
        <aside
          className={cn(
            'w-80 border-r bg-background transition-all duration-300 overflow-hidden',
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
        <main className="flex-1 relative">
          <MapContainer className="absolute inset-0" />
          
          {/* Map overlay info */}
          <div className="absolute bottom-4 left-4 bg-background/90 backdrop-blur rounded-lg p-3 text-sm shadow-lg">
            <div className="flex items-center gap-4">
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

        {/* Right panel - Schedule/Info */}
        <aside
          className={cn(
            'w-80 border-l bg-background transition-all duration-300 overflow-hidden',
            showRightPanel ? 'w-80' : 'w-0'
          )}
        >
          {showRightPanel && <SchedulePanel />}
        </aside>
      </div>

      {/* Footer */}
      <footer className="h-8 border-t bg-background px-4 flex items-center justify-between text-xs text-muted-foreground">
        <span>© 2024 Thailand Railway Digital Twin</span>
        <span>Data source: State Railway of Thailand (SRT)</span>
      </footer>
    </div>
  );
}
