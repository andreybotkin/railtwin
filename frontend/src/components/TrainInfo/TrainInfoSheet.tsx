/**
 * Compact, glass-morphic info sheet for the currently selected train.
 *
 * Subscribes to the live `Trajectory` directly from the Zustand store, so the
 * displayed position / speed tick at the same 60 fps cadence as the map
 * vehicles themselves. On desktop it floats in the bottom-right corner; on
 * mobile (<640 px) it docks as a slim bottom bar.
 */

'use client';

import { useEffect, useMemo, useState } from 'react';

import { ChevronRight, Gauge, Target, X } from 'lucide-react';

import { useStopSequence } from '@/lib/hooks';
import { useRailwayStore } from '@/lib/stores/railway-store';
import { getTrajectoryFrameAt } from '@/lib/trajectory-interpolation';
import { cn, formatDelay, formatSpeed, getTrainTypeName } from '@/lib/utils';

function delayColor(minutes: number): string {
  if (minutes <= 0) return '#2E7D32';
  if (minutes <= 5) return '#F9A825';
  if (minutes <= 15) return '#EF6C00';
  return '#C62828';
}

export default function TrainInfoSheet() {
  const selectedTrainId = useRailwayStore((s) => s.selectedTrainId);
  const trajectory = useRailwayStore((s) =>
    selectedTrainId !== null ? s.trajectories.get(selectedTrainId) ?? null : null,
  );
  const selectTrain = useRailwayStore((s) => s.selectTrain);
  const { data: stopSequence } = useStopSequence(selectedTrainId);

  const nextStop = useMemo(
    () => stopSequence?.find((stop) => stop.state === 'PENDING') ?? null,
    [stopSequence],
  );

  // Re-derive the live frame twice per second so speed + progress track the
  // simulation without forcing TrainInfoSheet into the rAF loop.
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!trajectory) return;
    const id = window.setInterval(() => setTick((t) => t + 1), 500);
    return () => window.clearInterval(id);
  }, [trajectory]);

  const liveFrame = useMemo(
    () => (trajectory ? getTrajectoryFrameAt(Date.now(), trajectory) : null),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [trajectory, tick],
  );

  if (!trajectory) return null;

  const meta = trajectory.meta;
  const speed = liveFrame?.speedKmh ?? 0;
  const status = liveFrame?.status ?? 'moving';
  const liveGeomFraction = liveFrame?.geomFraction ?? meta.route_progress_pct / 100;
  const progressPct = Math.round(Math.max(0, Math.min(100, liveGeomFraction * 100)));
  const segmentPct = Math.round(Math.max(0, Math.min(100, meta.segment_progress_pct)));

  return (
    <div
      className={cn(
        'pointer-events-auto fixed z-[1000] rounded-3xl border border-white/55',
        'bg-[rgba(252,249,242,0.88)] p-4 text-zinc-900 shadow-[0_22px_60px_-28px_rgba(15,23,42,0.55)] backdrop-blur-xl',
        'bottom-4 right-4 w-[min(22rem,calc(100vw-2rem))]',
      )}
    >
      <header className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <span
            className="inline-flex h-8 items-center rounded-full px-3 text-xs font-semibold uppercase tracking-wide text-white"
            style={{ backgroundColor: meta.color }}
          >
            #{meta.train_number}
          </span>
          <div className="leading-tight">
            <div className="text-sm font-semibold">{meta.train_name || getTrainTypeName(meta.train_type as string)}</div>
            <div className="text-xs capitalize text-zinc-500">{status.replace('_', ' ')}</div>
          </div>
        </div>
        <button
          aria-label="Close"
          onClick={() => selectTrain(null)}
          className="rounded-full p-1.5 text-zinc-500 transition hover:bg-zinc-950 hover:text-white"
        >
          <X className="h-4 w-4" />
        </button>
      </header>

      <div className="mt-3 grid grid-cols-2 gap-2">
        <div className="rounded-2xl bg-white/70 px-3 py-2">
          <div className="flex items-center gap-1 text-[10px] uppercase tracking-[0.14em] text-zinc-500">
            <Gauge className="h-3 w-3" /> Speed
          </div>
          <div className="mt-1 text-lg font-semibold tabular-nums">{formatSpeed(speed)}</div>
        </div>
        <div className="rounded-2xl bg-white/70 px-3 py-2">
          <div className="text-[10px] uppercase tracking-[0.14em] text-zinc-500">Delay</div>
          <div
            className="mt-1 text-lg font-semibold tabular-nums"
            style={{ color: delayColor(meta.delay_minutes) }}
          >
            {formatDelay(meta.delay_minutes)}
          </div>
        </div>
      </div>

      <div className="mt-3 rounded-2xl bg-white/70 px-3 py-2 text-xs">
        <div className="flex items-center justify-between text-zinc-500">
          <span>Route progress</span>
          <span className="tabular-nums">{progressPct}%</span>
        </div>
        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-zinc-200">
          <div
            className="h-full rounded-full bg-zinc-900 transition-[width] duration-500"
            style={{ width: `${progressPct}%` }}
          />
        </div>
      </div>

      <div className="mt-3 space-y-1.5 text-xs text-zinc-700">
        <div className="flex items-center gap-2 truncate">
          <span className="text-zinc-400">from</span>
          <span className="truncate font-medium">{meta.origin_station ?? meta.prev_station ?? '—'}</span>
        </div>
        <div className="flex items-center gap-2 truncate">
          <span className="text-zinc-400">to</span>
          <span className="truncate font-medium">{meta.destination_station ?? '—'}</span>
        </div>
        {nextStop && (
          <div className="mt-2 flex items-center gap-2 rounded-2xl bg-white/70 px-3 py-2">
            <ChevronRight className="h-3.5 w-3.5 text-zinc-500" />
            <div className="min-w-0 flex-1 truncate">
              <div className="text-[10px] uppercase tracking-[0.14em] text-zinc-500">
                Next stop
              </div>
              <div className="truncate font-semibold">{nextStop.station_name}</div>
            </div>
            <span className="rounded-full bg-zinc-900 px-2 py-0.5 text-[10px] font-semibold text-white tabular-nums">
              {segmentPct}%
            </span>
          </div>
        )}
      </div>

      {meta.current_edge_id !== null && (
        <div className="mt-3 flex items-center gap-2 text-[10px] uppercase tracking-[0.16em] text-zinc-500">
          <Target className="h-3 w-3" /> edge #{meta.current_edge_id}
        </div>
      )}
    </div>
  );
}
