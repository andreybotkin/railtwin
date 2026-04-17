/**
 * Compact glass-morphic info card for the currently selected station.
 *
 * Shows the station identity plus the next upcoming departures/arrivals
 * fetched through `useStationSchedule`. Floats in the same bottom-right slot
 * as `TrainInfoSheet` — only one of the two is ever visible at a time because
 * `selectTrain` and `selectStation` clear each other in the store.
 */

'use client';

import { useMemo } from 'react';
import { Building2, Clock, MapPin, X } from 'lucide-react';

import { useStationSchedule } from '@/lib/hooks';
import { useRailwayStore } from '@/lib/stores/railway-store';
import { cn } from '@/lib/utils';
import type { Schedule, Station } from '@/types';

function findStation(
  topology: ReturnType<typeof useRailwayStore.getState>['topology'],
  id: number | null,
): Station | null {
  if (topology == null || id == null) return null;
  return topology.stations.find((s) => s.id === id) ?? null;
}

function formatTime(value: string | null): string {
  if (!value) return '—';
  return value.slice(0, 5);
}

function compareStops(a: Schedule, b: Schedule): number {
  const av = a.departure_time ?? a.arrival_time ?? '99:99';
  const bv = b.departure_time ?? b.arrival_time ?? '99:99';
  return av.localeCompare(bv);
}

export default function StationInfoSheet() {
  const selectedStationId = useRailwayStore((s) => s.selectedStationId);
  const topology = useRailwayStore((s) => s.topology);
  const selectStation = useRailwayStore((s) => s.selectStation);
  const { data: schedule, isLoading } = useStationSchedule(selectedStationId);

  const station = useMemo(
    () => findStation(topology, selectedStationId),
    [topology, selectedStationId],
  );

  const upcoming = useMemo(() => {
    if (!schedule?.schedules) return [];
    return [...schedule.schedules].sort(compareStops).slice(0, 6);
  }, [schedule]);

  if (selectedStationId === null) return null;

  const displayName =
    station?.name ?? schedule?.station?.name ?? `Station #${selectedStationId}`;
  const city = station?.city ?? null;
  const code = station?.code ?? schedule?.station?.code ?? null;

  return (
    <div
      className={cn(
        'pointer-events-auto fixed z-[1000] rounded-3xl border border-white/55',
        'bg-[rgba(252,249,242,0.88)] p-4 text-zinc-900 shadow-[0_22px_60px_-28px_rgba(15,23,42,0.55)] backdrop-blur-xl',
        'bottom-4 right-4 w-[min(22rem,calc(100vw-2rem))]',
      )}
    >
      <header className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-zinc-900 text-white">
            <Building2 className="h-4 w-4" />
          </span>
          <div className="leading-tight min-w-0">
            <div className="truncate text-sm font-semibold">{displayName}</div>
            <div className="flex items-center gap-1.5 text-xs text-zinc-500">
              {code ? (
                <span className="rounded bg-zinc-200/70 px-1.5 font-mono text-[10px] tracking-wide">
                  {code}
                </span>
              ) : null}
              {city ? (
                <span className="flex items-center gap-1 truncate">
                  <MapPin className="h-3 w-3" /> {city}
                </span>
              ) : null}
            </div>
          </div>
        </div>
        <button
          aria-label="Close"
          onClick={() => selectStation(null)}
          className="rounded-full p-1.5 text-zinc-500 transition hover:bg-zinc-950 hover:text-white"
        >
          <X className="h-4 w-4" />
        </button>
      </header>

      <div className="mt-3 rounded-2xl bg-white/70 px-3 py-2 text-xs">
        <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.14em] text-zinc-500">
          <Clock className="h-3 w-3" /> Timetable
        </div>
        {isLoading ? (
          <div className="mt-2 text-zinc-500">Loading…</div>
        ) : upcoming.length === 0 ? (
          <div className="mt-2 text-zinc-500">No scheduled services.</div>
        ) : (
          <ul className="mt-1.5 space-y-1">
            {upcoming.map((stop) => (
              <li
                key={stop.id}
                className="flex items-center justify-between gap-2 tabular-nums"
              >
                <span className="truncate text-zinc-700">
                  {stop.train?.train_number
                    ? `#${stop.train.train_number}`
                    : `#${stop.train_id}`}
                  {stop.train?.name ? (
                    <span className="ml-1 text-zinc-400">{stop.train.name}</span>
                  ) : null}
                </span>
                <span className="flex items-center gap-2 font-mono text-[11px]">
                  <span>{formatTime(stop.arrival_time)}</span>
                  <span className="text-zinc-400">→</span>
                  <span>{formatTime(stop.departure_time)}</span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
