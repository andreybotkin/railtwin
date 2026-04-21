/**
 * Unified search panel for stations and train numbers.
 *
 * Opens from the header; shows a single input that matches against both the
 * topology's station list (by name, city, code) and the live trajectory map
 * (by train_number, name, operator). Selecting a result flies the map to the
 * target and opens the corresponding info sheet — exactly as if the user had
 * clicked the feature on the map.
 */

'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Building2, Search, Train, X } from 'lucide-react';

import { useRailwayStore } from '@/lib/stores/railway-store';
import { getTrainTypeColor, getTrainTypeName } from '@/lib/utils';
import type { Station, Trajectory } from '@/types';

interface StationResult {
  kind: 'station';
  id: number;
  name: string;
  subtitle: string;
  code: string | null;
  lon: number;
  lat: number;
}

interface TrainResult {
  kind: 'train';
  id: number;
  name: string;
  subtitle: string;
  number: string;
  type: string;
  lon: number;
  lat: number;
}

type Result = StationResult | TrainResult;

const MAX_RESULTS = 20;

function norm(v: string): string {
  return v.toLowerCase().trim();
}

function matchStation(station: Station, query: string): number {
  const q = norm(query);
  if (!q) return 1;
  const name = norm(station.name ?? '');
  const nameTh = norm(station.name_th ?? '');
  const code = norm(station.code ?? '');
  const city = norm(station.city ?? '');
  if (code === q) return 100;
  if (name === q || nameTh === q) return 95;
  if (name.startsWith(q) || nameTh.startsWith(q)) return 80;
  if (code.startsWith(q)) return 75;
  if (city.startsWith(q)) return 55;
  if (name.includes(q) || nameTh.includes(q)) return 40;
  if (city.includes(q) || code.includes(q)) return 25;
  return 0;
}

function matchTrain(trajectory: Trajectory, query: string): number {
  const q = norm(query);
  if (!q) return 1;
  const number = norm(trajectory.meta.train_number ?? '');
  const name = norm(trajectory.meta.train_name ?? '');
  if (number === q) return 100;
  if (number.startsWith(q)) return 85;
  if (name.startsWith(q)) return 60;
  if (number.includes(q)) return 50;
  if (name.includes(q)) return 35;
  return 0;
}

function stationToResult(station: Station): StationResult {
  const [lon, lat] = station.location?.coordinates ?? [0, 0];
  const subtitleParts = [station.city, station.province].filter(Boolean);
  return {
    kind: 'station',
    id: station.id,
    name: station.name,
    subtitle: subtitleParts.join(' · ') || 'Station',
    code: station.code ?? null,
    lon,
    lat,
  };
}

function trainToResult(t: Trajectory): TrainResult | null {
  const head = t.frames?.[0];
  const routeHead = t.route_coords?.[0];
  const lon = head?.lon ?? routeHead?.[0];
  const lat = head?.lat ?? routeHead?.[1];
  if (lon == null || lat == null) return null;
  const subtitle = [
    getTrainTypeName(t.meta.train_type ?? ''),
    t.meta.origin_station && t.meta.destination_station
      ? `${t.meta.origin_station} → ${t.meta.destination_station}`
      : null,
  ]
    .filter(Boolean)
    .join(' · ');
  return {
    kind: 'train',
    id: t.train_id,
    name: t.meta.train_name ?? `Train #${t.meta.train_number}`,
    subtitle: subtitle || 'Train',
    number: t.meta.train_number ?? String(t.train_id),
    type: t.meta.train_type ?? '',
    lon,
    lat,
  };
}

interface SearchPanelProps {
  open: boolean;
  onClose: () => void;
}

export default function SearchPanel({ open, onClose }: SearchPanelProps) {
  if (!open) return null;
  return <SearchPanelImpl onClose={onClose} />;
}

function SearchPanelImpl({ onClose }: { onClose: () => void }) {
  const t = useTranslations();
  const topology = useRailwayStore((s) => s.topology);
  const trajectories = useRailwayStore((s) => s.trajectories);
  const selectTrain = useRailwayStore((s) => s.selectTrain);
  const selectStation = useRailwayStore((s) => s.selectStation);
  const requestFlyTo = useRailwayStore((s) => s.requestFlyTo);

  const [query, setQuery] = useState('');
  const [focusIndex, setFocusIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const t = window.setTimeout(() => inputRef.current?.focus(), 20);
    return () => window.clearTimeout(t);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const results = useMemo<Result[]>(() => {
    const q = query.trim();
    const stations = topology?.stations ?? [];
    const trajList = Array.from(trajectories.values());

    const scoredStations = stations
      .map((s) => ({ score: matchStation(s, q), item: s }))
      .filter((r) => r.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, MAX_RESULTS)
      .map((r) => stationToResult(r.item));

    const scoredTrains = trajList
      .map((t) => ({ score: matchTrain(t, q), item: t }))
      .filter((r) => r.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, MAX_RESULTS)
      .map((r) => trainToResult(r.item))
      .filter((r): r is TrainResult => r !== null);

    if (!q) {
      return [...scoredTrains.slice(0, 6), ...scoredStations.slice(0, 12)];
    }
    return [...scoredTrains, ...scoredStations].slice(0, MAX_RESULTS);
  }, [query, topology, trajectories]);

  const handleSelect = (result: Result) => {
    requestFlyTo({ lon: result.lon, lat: result.lat, zoom: 12 });
    if (result.kind === 'station') {
      selectStation(result.id);
    } else {
      selectTrain(result.id);
    }
    onClose();
    setQuery('');
  };

  return (
    <div
      className="pointer-events-auto fixed inset-0 z-[1100] flex items-start justify-center p-3 pt-[max(4rem,env(safe-area-inset-top))] backdrop-blur-sm sm:pt-24"
      style={{ background: 'rgba(0,0,0,0.3)' }}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-label={t('search.ariaLabel')}
    >
      <div
        className="w-full max-w-lg overflow-hidden rounded-3xl"
        style={{
          background: 'var(--panel-bg-strong)',
          border: '1px solid var(--panel-border)',
          boxShadow: 'var(--panel-shadow)',
          color: 'var(--panel-text)',
        }}
      >
        <div
          className="flex items-center gap-2 px-3"
          style={{ borderBottom: '1px solid var(--panel-border)' }}
        >
          <Search className="h-4 w-4" style={{ color: 'var(--panel-subtext)' }} />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setFocusIndex(0);
            }}
            onKeyDown={(e) => {
              if (e.key === 'ArrowDown') {
                e.preventDefault();
                setFocusIndex((i) => Math.min(i + 1, results.length - 1));
              } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                setFocusIndex((i) => Math.max(i - 1, 0));
              } else if (e.key === 'Enter') {
                e.preventDefault();
                const target = results[focusIndex];
                if (target) handleSelect(target);
              }
            }}
            placeholder={t('search.placeholder')}
            className="h-12 flex-1 bg-transparent text-sm focus:outline-none"
            style={{ color: 'var(--panel-text)' }}
          />
          <button
            onClick={onClose}
            aria-label={t('search.close')}
            className="rounded-full p-1.5 transition"
            style={{ color: 'var(--panel-subtext)' }}
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <ul className="max-h-[min(28rem,70dvh)] overflow-y-auto py-1">
          {results.length === 0 ? (
            <li className="px-4 py-6 text-center text-xs" style={{ color: 'var(--panel-subtext)' }}>
              {query.trim()
                ? 'No matches. Try a station code or train number.'
                : 'Start typing to search.'}
            </li>
          ) : (
            results.map((r, idx) => {
              const focused = idx === focusIndex;
              return (
                <li key={`${r.kind}-${r.id}`}>
                  <button
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => handleSelect(r)}
                    onMouseEnter={() => setFocusIndex(idx)}
                    className="flex w-full items-center gap-3 px-3 py-2.5 text-left transition"
                    style={{
                      background: focused ? 'var(--header-logo-bg)' : 'transparent',
                      color: focused ? '#ffffff' : 'var(--panel-text)',
                    }}
                  >
                    {r.kind === 'train' ? (
                      <span
                        className="flex h-8 min-w-[2.5rem] items-center justify-center rounded-full px-2 text-[11px] font-semibold text-white shadow-sm"
                        style={{ backgroundColor: getTrainTypeColor(r.type) }}
                      >
                        #{r.number}
                      </span>
                    ) : (
                      <span
                        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
                        style={{
                          background: focused ? 'rgba(255,255,255,0.15)' : 'var(--panel-inner)',
                          color: focused ? '#ffffff' : 'var(--panel-subtext)',
                        }}
                      >
                        <Building2 className="h-4 w-4" />
                      </span>
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-semibold">{r.name}</div>
                      <div
                        className="truncate text-[11px]"
                        style={{ color: focused ? 'rgba(255,255,255,0.7)' : 'var(--panel-subtext)' }}
                      >
                        {r.subtitle}
                      </div>
                    </div>
                    {r.kind === 'station' && r.code ? (
                      <span
                        className="rounded px-1.5 py-0.5 font-mono text-[10px] tracking-wide"
                        style={{
                          background: focused ? 'rgba(255,255,255,0.15)' : 'var(--panel-inner)',
                          color: focused ? '#ffffff' : 'var(--panel-subtext)',
                        }}
                      >
                        {r.code}
                      </span>
                    ) : r.kind === 'train' ? (
                      <Train
                        className="h-3.5 w-3.5"
                        style={{ color: focused ? 'rgba(255,255,255,0.7)' : 'var(--panel-subtext)' }}
                      />
                    ) : null}
                  </button>
                </li>
              );
            })
          )}
        </ul>

        <div
          className="flex items-center justify-between px-3 py-2 text-[10px]"
          style={{
            borderTop: '1px solid var(--panel-border)',
            color: 'var(--panel-subtext)',
          }}
        >
          <span>
            {results.length} result{results.length === 1 ? '' : 's'}
          </span>
          <span className="hidden sm:inline">↑↓ navigate · ↵ select · esc close</span>
        </div>
      </div>
    </div>
  );
}
