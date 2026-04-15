/**
 * Train list panel component with selected‑train detail card.
 */

'use client';

import { useState, useMemo } from 'react';
import { Train as TrainIcon, Search, Circle, Clock, X, ChevronRight } from 'lucide-react';

import { useTrainPositions, useInitialPositions } from '@/lib/hooks';
import { formatSpeed, formatDelay, getTrainTypeName, cn } from '@/lib/utils';
import { Card, CardContent, CardHeader, CardTitle, Input, Badge } from '@/components/ui';
import type { TrainPositionUpdate } from '@/types';

// Mirrors getDelayColor in TrainMarker (delay colour pattern from mobility-toolbox-js)
function getDelayColor(delayMinutes: number): string {
  if (delayMinutes <= 0) return '#43A047';
  if (delayMinutes <= 5) return '#FDD835';
  if (delayMinutes <= 15) return '#FB8C00';
  return '#E53935';
}

interface TrainInfoPanelProps {
  onTrainSelect?: (trainId: number | null) => void;
  selectedTrainId?: number | null;
  bbox?: string | null;
}

export default function TrainInfoPanel({
  onTrainSelect,
  selectedTrainId,
  bbox,
}: TrainInfoPanelProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const { positions: wsPositions, isConnected } = useTrainPositions(bbox);
  const { data: apiPositions } = useInitialPositions(bbox);

  const positions = useMemo(() => {
    if (isConnected) {
      return wsPositions;
    }
    return apiPositions || [];
  }, [isConnected, wsPositions, apiPositions]);

  const selectedPosition = useMemo(
    () => positions.find((p) => p.train_id === selectedTrainId),
    [positions, selectedTrainId],
  );

  const filteredPositions = useMemo(() => {
    if (!searchQuery) return positions;
    const query = searchQuery.toLowerCase();
    return positions.filter(
      (p) =>
        p.train_number.toLowerCase().includes(query) ||
        (p.next_station?.toLowerCase().includes(query) ?? false),
    );
  }, [positions, searchQuery]);

  return (
    <Card className="h-full flex flex-col rounded-none border-0 bg-transparent shadow-none">
      <CardHeader className="border-b border-zinc-200/80 pb-3 pt-4">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base flex items-center gap-2 text-zinc-950">
            <TrainIcon className="h-4 w-4" />
            Active Trains
          </CardTitle>
          <Badge variant={isConnected ? 'success' : 'secondary'} className="text-xs">
            <Circle
              className={cn('h-2 w-2 mr-1', isConnected ? 'fill-current' : 'fill-none')}
            />
            {isConnected ? 'Live' : 'Polling'}
          </Badge>
        </div>
        <div className="relative mt-2">
          <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search trains…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="h-10 rounded-2xl border-zinc-200 bg-white/80 pl-8 text-sm"
          />
        </div>
      </CardHeader>

      <CardContent className="flex-1 overflow-auto p-0">
        {/* ── Selected train detail card ── */}
        {selectedPosition && (
          <SelectedTrainCard
            position={selectedPosition}
            onDeselect={() => onTrainSelect?.(null)}
          />
        )}

        {/* ── Train list ── */}
        <div className="space-y-1 p-3">
          {filteredPositions.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              No active trains found
            </div>
          ) : (
            filteredPositions.map((position) => (
              <TrainListItem
                key={position.train_id}
                position={position}
                isSelected={selectedTrainId === position.train_id}
                onClick={() =>
                  onTrainSelect?.(
                    selectedTrainId === position.train_id ? null : position.train_id,
                  )
                }
              />
            ))
          )}
        </div>
      </CardContent>
    </Card>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Selected Train Detail Card
// ─────────────────────────────────────────────────────────────────────────────

interface SelectedTrainCardProps {
  position: TrainPositionUpdate;
  onDeselect: () => void;
}

function SelectedTrainCard({ position, onDeselect }: SelectedTrainCardProps) {
  const statusBg =
    position.status === 'moving'
      ? 'bg-green-500'
      : position.status === 'delayed'
        ? 'bg-red-500'
        : position.status === 'at_station'
          ? 'bg-blue-500'
          : 'bg-gray-400';

  const delayColor = getDelayColor(position.delay_minutes);

  return (
    <div className="mx-2 mt-2 mb-1 rounded-lg border bg-accent/30 p-3 text-sm shadow-sm">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-1.5">
            <div className={cn('h-2.5 w-2.5 rounded-full shrink-0', statusBg)} />
            <span className="font-bold text-base">Train {position.train_number}</span>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            {getTrainTypeName(position.train_type)} ·{' '}
            <span className="capitalize">{position.status.replace('_', ' ')}</span>
          </p>
        </div>
        <button
          onClick={onDeselect}
          aria-label="Deselect train"
          className="rounded p-0.5 hover:bg-muted"
        >
          <X className="h-3.5 w-3.5 text-muted-foreground" />
        </button>
      </div>

      {/* Speed + Delay row */}
      <div className="mt-2.5 grid grid-cols-2 gap-2 rounded-md bg-background/70 px-2 py-1.5 text-xs">
        <div>
          <p className="text-muted-foreground text-[10px] uppercase tracking-wide">Speed</p>
          <p className="font-semibold">{formatSpeed(position.speed)}</p>
        </div>
        <div>
          <p className="text-muted-foreground text-[10px] uppercase tracking-wide">Delay</p>
          <p className="font-semibold" style={{ color: delayColor }}>
            {formatDelay(position.delay_minutes)}
          </p>
        </div>
      </div>

      {/* Next station + ETA */}
      {position.next_station && (
        <div className="mt-2">
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground flex items-center gap-1">
              <ChevronRight className="h-3 w-3" />
              Next station
            </span>
            {position.eta_next_station && (
              <span className="font-semibold tabular-nums">ETA {position.eta_next_station}</span>
            )}
          </div>
          <p className="mt-0.5 font-medium text-sm truncate">{position.next_station}</p>
        </div>
      )}

      {/* Progress bar */}
      {position.progress !== undefined && (
        <div className="mt-2">
          <div className="flex justify-between text-[10px] text-muted-foreground mb-1">
            <span>Progress to next station</span>
            <span>{position.progress}%</span>
          </div>
          <div className="h-1.5 bg-muted rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                width: `${position.progress}%`,
                backgroundColor: delayColor,
              }}
            />
          </div>
        </div>
      )}

      {position.route_progress !== undefined && (
        <div className="mt-2 text-[10px] text-muted-foreground">
          Route progress {Math.round(position.route_progress * 100)}%
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Train list item
// ─────────────────────────────────────────────────────────────────────────────

interface TrainListItemProps {
  position: TrainPositionUpdate;
  isSelected: boolean;
  onClick: () => void;
}

function TrainListItem({ position, isSelected, onClick }: TrainListItemProps) {
  const statusColor =
    position.status === 'moving'
      ? 'bg-green-500'
      : position.status === 'delayed'
        ? 'bg-red-500'
        : position.status === 'at_station'
          ? 'bg-blue-500'
          : 'bg-gray-400';

  return (
    <button
      onClick={onClick}
      className={cn(
        'w-full text-left px-3 py-2 rounded-md transition-colors text-sm',
        'hover:bg-accent',
        isSelected && 'bg-accent ring-2 ring-primary',
      )}
    >
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          <div className={cn('h-2.5 w-2.5 rounded-full shrink-0 mt-0.5', statusColor)} />
          <span className="font-semibold">Train {position.train_number}</span>
        </div>
        <Badge variant="outline" className="text-[10px] px-1.5 py-0">
          {getTrainTypeName(position.train_type)}
        </Badge>
      </div>

      <div className="mt-1 grid grid-cols-2 gap-1 text-xs text-muted-foreground pl-4">
        <div className="flex items-center gap-1">
          <Clock className="h-3 w-3" />
          {formatSpeed(position.speed)}
        </div>
        <div
          className="text-right"
          style={{ color: getDelayColor(position.delay_minutes) }}
        >
          {formatDelay(position.delay_minutes)}
        </div>
      </div>

      {position.next_station && (
        <p className="mt-0.5 pl-4 text-xs truncate">
          <span className="text-muted-foreground">Next: </span>
          <span className="font-medium">{position.next_station}</span>
          {position.eta_next_station && (
            <span className="text-muted-foreground ml-1">({position.eta_next_station})</span>
          )}
        </p>
      )}
    </button>
  );
}
