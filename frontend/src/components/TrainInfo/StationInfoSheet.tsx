/**
 * Live info panel for the currently selected station.
 *
 * Shares the mobile-first bottom-sheet / desktop floating-card layout with
 * `TrainInfoSheet` — only one is ever mounted because `selectTrain` and
 * `selectStation` clear each other in the store.
 *
 * Content:
 *   1. Header — station icon, name, city, platform code.
 *   2. "Next departure" card — big-font countdown to the next train.
 *   3. Timetable list — up to eight upcoming arrivals/departures grouped by
 *      train, with a coloured pill for the train type.
 */

'use client';

import { useEffect, useMemo, useState } from 'react';
import { Building2, Clock, MapPin, Timer, X } from 'lucide-react';

import { useStationSchedule } from '@/lib/hooks';
import { useRailwayStore } from '@/lib/stores/railway-store';
import { cn, getTrainTypeColor, getTrainTypeName } from '@/lib/utils';
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

function timeToMinutes(value: string): number {
  const [h, m] = value.split(':').map(Number);
  if (Number.isNaN(h) || Number.isNaN(m)) return 0;
  return h * 60 + m;
}

function compareStops(a: Schedule, b: Schedule): number {
  const av = a.departure_time ?? a.arrival_time ?? '99:99';
  const bv = b.departure_time ?? b.arrival_time ?? '99:99';
  return av.localeCompare(bv);
}

function formatCountdown(nowMin: number, targetMin: number): string {
  let delta = targetMin - nowMin;
  if (delta <= -30) delta += 24 * 60; // Already-past stops that happened > 30 min ago rolled over.
  if (delta <= 0) return 'now';
  if (delta < 60) return `in ${delta}m`;
  const hours = Math.floor(delta / 60);
  const mins = delta % 60;
  return `in ${hours}h ${mins.toString().padStart(2, '0')}m`;
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

  const [nowMinutes, setNowMinutes] = useState(() => {
    const d = new Date();
    return d.getHours() * 60 + d.getMinutes();
  });

  useEffect(() => {
    if (selectedStationId === null) return;
    const id = window.setInterval(() => {
      const d = new Date();
      setNowMinutes(d.getHours() * 60 + d.getMinutes());
    }, 15_000);
    return () => window.clearInterval(id);
  }, [selectedStationId]);

  const upcoming = useMemo(() => {
    if (!schedule?.schedules) return [];
    return [...schedule.schedules].sort(compareStops);
  }, [schedule]);

  const nextStop = useMemo(() => {
    const ref = upcoming.find((s) => {
      const t = s.departure_time ?? s.arrival_time;
      if (!t) return false;
      return timeToMinutes(t) >= nowMinutes - 1;
    });
    return ref ?? upcoming[0] ?? null;
  }, [upcoming, nowMinutes]);

  if (selectedStationId === null) return null;

  const displayName =
    station?.name ?? schedule?.station?.name ?? `Station #${selectedStationId}`;
  const city = station?.city ?? null;
  const province = station?.province ?? null;
  const code = station?.code ?? schedule?.station?.code ?? null;
  const serviceCount = upcoming.length;

  return (
    <div
      className={cn(
        'pointer-events-auto fixed z-[1000] text-zinc-900',
        'inset-x-0 bottom-0 rounded-t-3xl',
        'sm:inset-x-auto sm:bottom-4 sm:right-4 sm:w-[22rem] sm:rounded-3xl',
        'border border-white/60 bg-[rgba(252,249,242,0.94)] shadow-[0_-18px_48px_-22px_rgba(15,23,42,0.45)] backdrop-blur-xl',
        'sm:shadow-[0_22px_60px_-28px_rgba(15,23,42,0.55)]',
        'max-h-[80dvh] overflow-y-auto',
      )}
    >
      <div className="mx-auto mt-2 h-1.5 w-10 rounded-full bg-zinc-300 sm:hidden" aria-hidden />

      <div className="p-4 sm:p-5">
        <header className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-zinc-950 text-white shadow-sm">
              <Building2 className="h-5 w-5" />
            </div>
            <div className="min-w-0 leading-tight">
              <div className="truncate text-sm font-semibold text-zinc-900">{displayName}</div>
              <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-zinc-500">
                {code ? (
                  <span className="rounded bg-zinc-200/70 px-1.5 py-0.5 font-mono tracking-wide">
                    {code}
                  </span>
                ) : null}
                {city ? (
                  <span className="flex items-center gap-1">
                    <MapPin className="h-3 w-3" /> {city}
                    {province ? <span className="text-zinc-400">· {province}</span> : null}
                  </span>
                ) : null}
              </div>
            </div>
          </div>
          <button
            aria-label="Close"
            onClick={() => selectStation(null)}
            className="rounded-full p-2 text-zinc-500 transition hover:bg-zinc-950 hover:text-white"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        {nextStop && (
          <section className="mt-4 rounded-2xl bg-zinc-950 p-4 text-white">
            <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.18em] text-zinc-400">
              <Timer className="h-3 w-3" /> Next service
            </div>
            <div className="mt-2 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  {nextStop.train?.train_type && (
                    <span
                      className="inline-flex h-5 items-center rounded-full px-2 text-[10px] font-semibold uppercase text-white"
                      style={{ backgroundColor: getTrainTypeColor(nextStop.train.train_type) }}
                    >
                      #{nextStop.train.train_number ?? nextStop.train_id}
                    </span>
                  )}
                  <span className="truncate text-sm font-semibold">
                    {nextStop.train?.name ?? getTrainTypeName(nextStop.train?.train_type ?? '')}
                  </span>
                </div>
                <div className="mt-1 text-[11px] text-zinc-400">
                  Arr {formatTime(nextStop.arrival_time)} · Dep {formatTime(nextStop.departure_time)}
                </div>
              </div>
              <div className="shrink-0 text-right tabular-nums">
                <div className="text-xs text-zinc-400">ETA</div>
                <div className="text-xl font-bold leading-tight">
                  {nextStop.departure_time
                    ? formatCountdown(nowMinutes, timeToMinutes(nextStop.departure_time))
                    : nextStop.arrival_time
                      ? formatCountdown(nowMinutes, timeToMinutes(nextStop.arrival_time))
                      : '—'}
                </div>
              </div>
            </div>
          </section>
        )}

        <section className="mt-4">
          <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.14em] text-zinc-500">
            <span className="flex items-center gap-1.5">
              <Clock className="h-3 w-3" /> Timetable
            </span>
            {serviceCount > 0 ? <span>{serviceCount} services</span> : null}
          </div>

          {isLoading ? (
            <div className="mt-3 rounded-2xl bg-white/70 p-3 text-xs text-zinc-500 ring-1 ring-black/5">
              Loading timetable…
            </div>
          ) : upcoming.length === 0 ? (
            <div className="mt-3 rounded-2xl bg-white/70 p-3 text-xs text-zinc-500 ring-1 ring-black/5">
              No scheduled services.
            </div>
          ) : (
            <ul className="mt-2 space-y-1.5">
              {upcoming.slice(0, 8).map((stop) => {
                const typeColor = stop.train?.train_type
                  ? getTrainTypeColor(stop.train.train_type)
                  : '#2196F3';
                return (
                  <li
                    key={stop.id}
                    className="flex items-center gap-3 rounded-2xl bg-white/70 px-3 py-2 ring-1 ring-black/5"
                  >
                    <span
                      className="inline-flex h-7 w-auto min-w-[2.5rem] items-center justify-center rounded-full px-2 text-[11px] font-semibold text-white"
                      style={{ backgroundColor: typeColor }}
                    >
                      #{stop.train?.train_number ?? stop.train_id}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-xs font-medium text-zinc-900">
                        {stop.train?.name ?? getTrainTypeName(stop.train?.train_type ?? '')}
                      </div>
                      <div className="text-[11px] text-zinc-500">
                        {stop.platform ? `Platform ${stop.platform} · ` : null}
                        {getTrainTypeName(stop.train?.train_type ?? '')}
                      </div>
                    </div>
                    <div className="flex flex-col items-end text-[11px] leading-tight tabular-nums text-zinc-700">
                      <span className="font-semibold">{formatTime(stop.departure_time)}</span>
                      {stop.arrival_time &&
                        stop.arrival_time !== stop.departure_time && (
                          <span className="text-zinc-400">
                            arr {formatTime(stop.arrival_time)}
                          </span>
                        )}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
