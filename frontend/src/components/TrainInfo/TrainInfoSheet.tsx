/**
 * Live info panel for the currently selected train.
 *
 * Mobile-first layout:
 *   • On narrow screens (<640 px) the card docks to the bottom of the
 *     viewport as a full-width "bottom sheet" with a swipe handle, mirroring
 *     Google/Apple Maps conventions.
 *   • On larger screens it floats as a 22 rem card in the bottom-right.
 *
 * Three content blocks:
 *   1. Status header — train number badge, name, live status pill.
 *   2. Live stats — live-interpolated speed, ETA countdown, segment progress.
 *   3. Stop timeline — past/current/upcoming stops with live states.
 *
 * The live speed and countdown tick twice per second via an internal tick
 * counter that re-derives the interpolated frame; we deliberately *don't*
 * subscribe to the rAF loop here to keep the component cheap.
 */

'use client';

import { useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';

import { ChevronRight, Gauge, MapPin, Navigation, Train as TrainIcon, X } from 'lucide-react';

import { useStopSequence } from '@/lib/hooks';
import { useRailwayStore } from '@/lib/stores/railway-store';
import { getTrajectoryFrameAt } from '@/lib/trajectory-interpolation';
import { cn, formatDelay, formatSpeed, getTrainTypeName } from '@/lib/utils';
import type { StopSequenceItem } from '@/types';

function delayColor(minutes: number): string {
  if (minutes <= 0) return '#15803D';
  if (minutes <= 5) return '#B45309';
  if (minutes <= 15) return '#C2410C';
  return '#991B1B';
}

type StatusKey = 'atStation' | 'arrived' | 'boarding' | 'stopped' | 'enRoute';

function statusKey(status: string, speedKmh: number): StatusKey {
  if (status === 'dwelling') return 'atStation';
  if (status === 'arrived') return 'arrived';
  if (status === 'boarding') return 'boarding';
  if (speedKmh < 1) return 'stopped';
  return 'enRoute';
}

function statusTint(status: string, speedKmh: number): string {
  if (status === 'dwelling' || status === 'boarding') return 'bg-amber-100 text-amber-900 ring-amber-200';
  if (status === 'arrived') return 'bg-emerald-100 text-emerald-900 ring-emerald-200';
  if (speedKmh < 1) return 'bg-zinc-200 text-zinc-700 ring-zinc-300';
  return 'bg-emerald-100 text-emerald-900 ring-emerald-200';
}

function formatCountdown(targetMs: number | null, nowMs: number): string {
  if (targetMs === null) return '—';
  const deltaSec = Math.max(0, Math.round((targetMs - nowMs) / 1000));
  if (deltaSec <= 0) return 'now';
  const mins = Math.floor(deltaSec / 60);
  const secs = deltaSec % 60;
  if (mins >= 60) {
    const hours = Math.floor(mins / 60);
    const remMins = mins % 60;
    return `${hours}h ${remMins}m`;
  }
  if (mins === 0) return `${secs}s`;
  return `${mins}m ${secs.toString().padStart(2, '0')}s`;
}

function formatStopTime(minutes: number | null): string {
  if (minutes === null) return '—';
  const h = Math.floor(minutes / 60) % 24;
  const m = minutes % 60;
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`;
}

function StopRow({
  stop,
  isActive,
  isLast,
}: {
  stop: StopSequenceItem;
  isActive: boolean;
  isLast: boolean;
}) {
  const dot =
    stop.state === 'PASSED'
      ? 'bg-zinc-300'
      : isActive
        ? 'bg-amber-500 ring-4 ring-amber-200'
        : 'bg-zinc-950';

  return (
    <li className="relative flex items-center gap-3 py-1.5">
      <div className="relative flex h-5 w-5 shrink-0 items-center justify-center">
        <span className={cn('h-2 w-2 rounded-full', dot)} />
        {!isLast && (
          <span
            className="absolute left-1/2 top-full h-[22px] w-px -translate-x-1/2"
            style={{ background: 'var(--panel-inner-ring)' }}
          />
        )}
      </div>
      <div
        className="flex min-w-0 flex-1 items-center justify-between gap-2 text-sm"
        style={{
          color: stop.state === 'PASSED'
            ? 'var(--panel-subtext)'
            : isActive
              ? 'var(--panel-text)'
              : 'var(--panel-text)',
          fontWeight: isActive ? 600 : 400,
          opacity: stop.state === 'PASSED' ? 0.6 : 1,
        }}
      >
        <span className="truncate">{stop.station_name}</span>
        <span
          className="flex items-center gap-1.5 text-[11px] tabular-nums"
          style={{ color: 'var(--panel-subtext)' }}
        >
          {stop.aimed_arrival_minutes !== null ? (
            <>
              <span>{formatStopTime(stop.aimed_arrival_minutes)}</span>
              {stop.aimed_departure_minutes !== null &&
                stop.aimed_departure_minutes !== stop.aimed_arrival_minutes && (
                  <>
                    <span style={{ opacity: 0.4 }}>→</span>
                    <span>{formatStopTime(stop.aimed_departure_minutes)}</span>
                  </>
                )}
            </>
          ) : (
            <span>{formatStopTime(stop.aimed_departure_minutes)}</span>
          )}
        </span>
      </div>
    </li>
  );
}

export default function TrainInfoSheet() {
  const t = useTranslations();
  const selectedTrainId = useRailwayStore((s) => s.selectedTrainId);
  const trajectory = useRailwayStore((s) =>
    selectedTrainId !== null ? s.trajectories.get(selectedTrainId) ?? null : null,
  );
  const selectTrain = useRailwayStore((s) => s.selectTrain);
  const { data: stopSequence } = useStopSequence(selectedTrainId);

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

  const nowMs = useMemo(
    () => Date.now(),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [tick],
  );

  const timelineStops = useMemo(() => {
    if (!stopSequence) return [];
    const pivot = stopSequence.findIndex((s) => s.state !== 'PASSED');
    const start = pivot <= 1 ? 0 : pivot - 1;
    return stopSequence.slice(start, start + 6);
  }, [stopSequence]);

  const activeIndex = useMemo(() => {
    if (timelineStops.length === 0) return -1;
    return timelineStops.findIndex((s) => s.state !== 'PASSED');
  }, [timelineStops]);

  if (!trajectory) return null;

  const meta = trajectory.meta;
  const speed = liveFrame?.speedKmh ?? 0;
  const status = liveFrame?.status ?? 'moving';
  const liveGeomFraction = liveFrame?.geomFraction ?? meta.route_progress_pct / 100;
  const progressPct = Math.round(Math.max(0, Math.min(100, liveGeomFraction * 100)));
  const segmentPct = Math.round(Math.max(0, Math.min(100, meta.segment_progress_pct)));
  const statusClass = statusTint(status, speed);
  const statusText = t(`trains.${statusKey(status, speed)}`);
  const trainLabel = meta.train_name || getTrainTypeName(meta.train_type as string);
  const delayHex = delayColor(meta.delay_minutes);

  return (
    <div
      className={cn(
        'info-sheet pointer-events-auto fixed z-[1000] text-zinc-900',
        // Mobile: bottom sheet spanning the viewport.
        'inset-x-0 bottom-0 rounded-t-3xl',
        // Desktop: floating card.
        'sm:inset-x-auto sm:bottom-4 sm:right-4 sm:w-[22rem] sm:rounded-3xl',
        'backdrop-blur-xl',
        'max-h-[80dvh] overflow-y-auto',
      )}
      style={{
        background: 'var(--panel-bg-strong)',
        border: '1px solid var(--panel-border)',
        boxShadow: 'var(--panel-shadow-up)',
        color: 'var(--panel-text)',
        borderTop: `3px solid ${meta.color}`,
      }}
    >
      {/* Swipe handle — mobile only. */}
      <div
        className="mx-auto mt-2 h-1.5 w-10 rounded-full sm:hidden"
        style={{ background: 'var(--panel-inner-ring)' }}
        aria-hidden
      />

      <div className="p-4 sm:p-5">
        <header className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <div
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl text-white shadow-sm"
              style={{ backgroundColor: meta.color }}
            >
              <TrainIcon className="h-5 w-5" />
            </div>
            <div className="min-w-0 leading-tight">
              <div className="flex items-center gap-2">
                <span
                  className="inline-flex h-6 items-center rounded-full px-2.5 text-xs font-semibold text-white"
                  style={{ backgroundColor: meta.color }}
                >
                  #{meta.train_number}
                </span>
                <span
                  className={cn(
                    'inline-flex h-6 items-center rounded-full px-2.5 text-[11px] font-semibold ring-1',
                    statusClass,
                  )}
                >
                  {statusText}
                </span>
              </div>
              <div
                className="mt-1 truncate text-[13px] font-semibold"
                style={{ color: 'var(--panel-text)' }}
              >
                {trainLabel}
              </div>
              <div
                className="truncate text-xs"
                style={{ color: 'var(--panel-subtext)' }}
              >
                {meta.operator}
              </div>
            </div>
          </div>
          <button
            aria-label={t('common.close')}
            onClick={() => selectTrain(null)}
            className="rounded-full p-2 transition"
            style={{ color: 'var(--panel-subtext)' }}
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        <section className="mt-4 grid grid-cols-3 gap-2">
          {[
            {
              label: t('trains.speed'),
              icon: <Gauge className="h-3 w-3" />,
              value: formatSpeed(speed),
              color: undefined as string | undefined,
            },
            {
              label: t('trains.delay'),
              icon: null,
              value: formatDelay(meta.delay_minutes),
              color: delayHex,
            },
            {
              label: t('trains.eta'),
              icon: <Navigation className="h-3 w-3" />,
              value: formatCountdown(meta.eta_next_ms, nowMs),
              color: undefined,
            },
          ].map(({ label, icon, value, color }) => (
            <div
              key={label}
              className="rounded-2xl px-3 py-2"
              style={{ background: 'var(--panel-inner)', boxShadow: `0 0 0 1px var(--panel-inner-ring)` }}
            >
              <div
                className="flex items-center gap-1 text-[10px] uppercase tracking-[0.14em]"
                style={{ color: 'var(--panel-subtext)' }}
              >
                {icon} {label}
              </div>
              <div
                className="mt-0.5 text-lg font-semibold tabular-nums"
                style={{ color: color ?? 'var(--panel-text)' }}
              >
                {value}
              </div>
            </div>
          ))}
        </section>

        <section
          className="mt-3 rounded-2xl px-3 py-2.5"
          style={{ background: 'var(--panel-inner)', boxShadow: `0 0 0 1px var(--panel-inner-ring)` }}
        >
          <div
            className="flex items-center justify-between text-xs"
            style={{ color: 'var(--panel-subtext)' }}
          >
            <span className="truncate">
              <span style={{ opacity: 0.6 }}>{t('trains.next')}</span>{' '}
              <span className="font-semibold" style={{ color: 'var(--panel-text)' }}>
                {meta.next_station ?? '—'}
              </span>
            </span>
            <span
              className="tabular-nums text-[11px] font-semibold"
              style={{ color: 'var(--panel-text)' }}
            >
              {segmentPct}%
            </span>
          </div>
          <div
            className="mt-1.5 h-1.5 overflow-hidden rounded-full"
            style={{ background: 'var(--panel-inner-ring)' }}
          >
            <div
              className="h-full rounded-full transition-[width] duration-500"
              style={{ width: `${segmentPct}%`, backgroundColor: meta.color }}
            />
          </div>
          <div
            className="mt-2 flex items-center justify-between text-[11px]"
            style={{ color: 'var(--panel-subtext)' }}
          >
            <span>{t('trains.routeProgress')} {progressPct}%</span>
            <span className="truncate">
              <span style={{ opacity: 0.6 }}>{t('trains.to')}</span>{' '}
              <span className="font-medium" style={{ color: 'var(--panel-text)', opacity: 0.8 }}>
                {meta.destination_station ?? '—'}
              </span>
            </span>
          </div>
          <div
            className="mt-1.5 h-1 overflow-hidden rounded-full"
            style={{ background: 'var(--panel-inner-ring)' }}
          >
            <div
              className="h-full rounded-full transition-[width] duration-500"
              style={{ width: `${progressPct}%`, background: 'var(--panel-text)', opacity: 0.8 }}
            />
          </div>
        </section>

        {timelineStops.length > 0 && (
          <section className="mt-4">
            <div
              className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.14em]"
              style={{ color: 'var(--panel-subtext)' }}
            >
              <MapPin className="h-3 w-3" /> {t('trains.stopTimeline')}
            </div>
            <ol className="mt-1.5">
              {timelineStops.map((stop, idx) => (
                <StopRow
                  key={`${stop.sequence}-${stop.station_name}`}
                  stop={stop}
                  isActive={idx === activeIndex}
                  isLast={idx === timelineStops.length - 1}
                />
              ))}
            </ol>
          </section>
        )}

        {meta.origin_station && meta.destination_station && (
          <footer
            className="mt-3 flex items-center justify-between gap-2 rounded-2xl px-3 py-2 text-xs"
            style={{
              background: 'var(--panel-inner)',
              color: 'var(--panel-subtext)',
            }}
          >
            <span className="truncate">
              <span style={{ opacity: 0.6 }}>From</span>{' '}
              <span className="font-medium" style={{ color: 'var(--panel-text)' }}>
                {meta.origin_station}
              </span>
            </span>
            <ChevronRight className="h-3.5 w-3.5 shrink-0" style={{ opacity: 0.4 }} />
            <span className="truncate text-right">
              <span className="font-medium" style={{ color: 'var(--panel-text)' }}>
                {meta.destination_station}
              </span>
            </span>
          </footer>
        )}
      </div>
    </div>
  );
}
