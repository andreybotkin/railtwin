'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { Building2, Clock, MapPin, Timer, X } from 'lucide-react';

import { useStationSchedule } from '@/lib/hooks';
import { useBottomSheetDrag } from '@/lib/hooks/useBottomSheetDrag';
import { useRailwayStore } from '@/lib/stores/railway-store';
import { cn, getTrainTypeColor } from '@/lib/utils';
import type { Schedule, Station } from '@/types';

function findStation(
  topology: ReturnType<typeof useRailwayStore.getState>['topology'],
  id: number | null
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

export default function StationInfoSheet() {
  const t = useTranslations();
  const locale = useLocale();

  function formatCountdown(nowMin: number, targetMin: number): string {
    let delta = targetMin - nowMin;
    if (delta <= -30) delta += 24 * 60;
    if (delta <= 0) return t('schedule.now');
    if (delta < 60) return t('schedule.inMin', { m: delta });
    const hours = Math.floor(delta / 60);
    const mins = delta % 60;
    return t('schedule.inHourMin', {
      h: hours,
      m: mins.toString().padStart(2, '0'),
    });
  }

  const localTypeName = (type: string | null | undefined) => {
    if (!type) return '';
    const key = `trains.${type}` as Parameters<typeof t>[0];
    try {
      return t(key);
    } catch {
      return type;
    }
  };

  const trainDisplay = (
    type: string | null | undefined,
    number: string | null | undefined
  ) => {
    const typePart = localTypeName(type);
    if (!number) return typePart;
    return `${typePart} ${t('trains.trainNo')} ${number}`;
  };
  const selectedStationId = useRailwayStore((s) => s.selectedStationId);
  const topology = useRailwayStore((s) => s.topology);
  const selectStation = useRailwayStore((s) => s.selectStation);
  const { data: schedule, isLoading } = useStationSchedule(selectedStationId);

  const station = useMemo(
    () => findStation(topology, selectedStationId),
    [topology, selectedStationId]
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
      const tt = s.departure_time ?? s.arrival_time;
      if (!tt) return false;
      return timeToMinutes(tt) >= nowMinutes - 1;
    });
    return ref ?? upcoming[0] ?? null;
  }, [upcoming, nowMinutes]);

  const innerRef = useRef<HTMLDivElement>(null);
  const snap1Ref = useRef<HTMLDivElement>(null);
  const snap2Ref = useRef<HTMLDivElement>(null);
  const { sheetStyle, handleBarProps } = useBottomSheetDrag('station', {
    innerRef,
    snap1Ref,
    snap2Ref,
  });

  if (selectedStationId === null) return null;

  const displayName =
    (locale === 'th' ? station?.name_th || station?.name : station?.name) ??
    schedule?.station?.name ??
    `${t('common.station')} #${selectedStationId}`;
  const city = station?.city ?? null;
  const province = station?.province ?? null;
  const code = station?.code ?? schedule?.station?.code ?? null;
  const serviceCount = upcoming.length;

  return (
    <div
      className={cn(
        'info-sheet pointer-events-auto fixed z-[1000] text-zinc-900',
        'inset-x-2 bottom-[max(0.5rem,env(safe-area-inset-bottom))] rounded-3xl',
        'sm:inset-x-auto sm:right-4 sm:bottom-4 sm:w-[22rem] sm:rounded-3xl',
        'backdrop-blur-xl',
        'flex flex-col overflow-hidden',
        'sm:max-h-[80dvh]'
      )}
      style={{
        background: 'var(--panel-bg-strong)',
        border: '1px solid var(--panel-border)',
        boxShadow: 'var(--panel-shadow-up)',
        color: 'var(--panel-text)',
        ...sheetStyle,
      }}
    >
      {/* Drag handle — mobile only. Always visible above scrollable content. */}
      <div
        {...handleBarProps}
        className="mx-auto mt-2 h-1.5 w-10 flex-shrink-0 rounded-full sm:hidden"
        style={{
          background: 'var(--panel-inner-ring)',
          ...handleBarProps.style,
        }}
        aria-label="Resize panel"
      />

      <div
        ref={innerRef}
        className="relative flex-1 overflow-y-auto overscroll-contain p-3 pb-4 sm:p-5"
      >
        <header className="flex items-start justify-between gap-2 sm:gap-3">
          <div className="flex min-w-0 items-center gap-2.5 sm:gap-3">
            <div
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-white shadow-sm sm:h-11 sm:w-11 sm:rounded-2xl"
              style={{ background: 'var(--station-icon-bg)' }}
            >
              <Building2 className="h-5 w-5" />
            </div>
            <div className="min-w-0 leading-tight">
              <div
                className="truncate text-sm font-semibold"
                style={{ color: 'var(--panel-text)' }}
              >
                {displayName}
              </div>
              <div
                className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px]"
                style={{ color: 'var(--panel-subtext)' }}
              >
                {code ? (
                  <span
                    className="rounded px-1.5 py-0.5 font-mono tracking-wide"
                    style={{ background: 'var(--panel-inner)' }}
                  >
                    {code}
                  </span>
                ) : null}
                {city ? (
                  <span className="flex items-center gap-1">
                    <MapPin className="h-3 w-3" /> {city}
                    {province ? (
                      <span style={{ opacity: 0.6 }}>· {province}</span>
                    ) : null}
                  </span>
                ) : null}
              </div>
            </div>
          </div>
          <button
            aria-label={t('common.close')}
            onClick={() => selectStation(null)}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full transition"
            style={{ color: 'var(--panel-subtext)' }}
          >
            <X className="h-4 w-4" />
          </button>
        </header>
        {/* Snap-1 sentinel: sheet stops here showing only the station header */}
        <div ref={snap1Ref} />

        {nextStop && (
          <section
            className="mt-3 rounded-2xl p-3 sm:mt-4 sm:p-4"
            style={{
              background: 'var(--station-next-bg)',
              color: 'var(--station-next-text)',
            }}
          >
            <div
              className="flex items-center gap-1.5 text-[10px] tracking-[0.18em] uppercase"
              style={{ opacity: 0.6 }}
            >
              <Timer className="h-3 w-3" /> {t('schedule.nextService')}
            </div>
            <div className="mt-2 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  {nextStop.train?.train_type && (
                    <span
                      className="inline-flex h-5 items-center rounded-full px-2 text-[10px] font-semibold text-white uppercase"
                      style={{
                        backgroundColor: getTrainTypeColor(
                          nextStop.train.train_type
                        ),
                      }}
                    >
                      #{nextStop.train.train_number ?? nextStop.train_id}
                    </span>
                  )}
                  <span className="truncate text-sm font-semibold">
                    {trainDisplay(
                      nextStop.train?.train_type,
                      nextStop.train?.train_number
                    )}
                  </span>
                </div>
                <div className="mt-1 text-[11px]" style={{ opacity: 0.6 }}>
                  {t('schedule.arrAbbr')} {formatTime(nextStop.arrival_time)} ·{' '}
                  {t('schedule.depAbbr')} {formatTime(nextStop.departure_time)}
                </div>
              </div>
              <div className="shrink-0 text-right tabular-nums">
                <div className="text-xs" style={{ opacity: 0.6 }}>
                  {t('trains.eta')}
                </div>
                <div className="text-xl leading-tight font-bold">
                  {nextStop.departure_time
                    ? formatCountdown(
                        nowMinutes,
                        timeToMinutes(nextStop.departure_time)
                      )
                    : nextStop.arrival_time
                      ? formatCountdown(
                          nowMinutes,
                          timeToMinutes(nextStop.arrival_time)
                        )
                      : '—'}
                </div>
              </div>
            </div>
          </section>
        )}
        {/* Snap-2 sentinel: sheet stops here showing header + next service card */}
        <div ref={snap2Ref} />

        <section className="mt-4">
          <div
            className="flex items-center justify-between text-[10px] tracking-[0.14em] uppercase"
            style={{ color: 'var(--panel-subtext)' }}
          >
            <span className="flex items-center gap-1.5">
              <Clock className="h-3 w-3" /> {t('schedule.timetable')}
            </span>
            {serviceCount > 0 ? (
              <span>{t('schedule.services', { count: serviceCount })}</span>
            ) : null}
          </div>

          {isLoading ? (
            <div
              className="mt-3 rounded-2xl p-3 text-xs"
              style={{
                background: 'var(--panel-inner)',
                color: 'var(--panel-subtext)',
                boxShadow: '0 0 0 1px var(--panel-inner-ring)',
              }}
            >
              {t('schedule.loading')}
            </div>
          ) : upcoming.length === 0 ? (
            <div
              className="mt-3 rounded-2xl p-3 text-xs"
              style={{
                background: 'var(--panel-inner)',
                color: 'var(--panel-subtext)',
                boxShadow: '0 0 0 1px var(--panel-inner-ring)',
              }}
            >
              {t('schedule.noServices')}
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
                    className="flex items-center gap-3 rounded-2xl px-3 py-2"
                    style={{
                      background: 'var(--panel-inner)',
                      boxShadow: '0 0 0 1px var(--panel-inner-ring)',
                    }}
                  >
                    <span
                      className="inline-flex h-7 w-auto min-w-[2.5rem] items-center justify-center rounded-full px-2 text-[11px] font-semibold text-white"
                      style={{ backgroundColor: typeColor }}
                    >
                      #{stop.train?.train_number ?? stop.train_id}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div
                        className="truncate text-xs font-medium"
                        style={{ color: 'var(--panel-text)' }}
                      >
                        {trainDisplay(
                          stop.train?.train_type,
                          stop.train?.train_number
                        )}
                      </div>
                      <div
                        className="text-[11px]"
                        style={{ color: 'var(--panel-subtext)' }}
                      >
                        {stop.platform
                          ? `${t('schedule.platform')} ${stop.platform}`
                          : null}
                      </div>
                    </div>
                    <div
                      className="flex flex-col items-end text-[11px] leading-tight tabular-nums"
                      style={{ color: 'var(--panel-text)' }}
                    >
                      <span className="font-semibold">
                        {formatTime(stop.departure_time)}
                      </span>
                      {stop.arrival_time &&
                        stop.arrival_time !== stop.departure_time && (
                          <span style={{ color: 'var(--panel-subtext)' }}>
                            {t('schedule.arrAbbr')}{' '}
                            {formatTime(stop.arrival_time)}
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
