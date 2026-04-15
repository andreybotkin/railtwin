/**
 * Train-focused debug page for validating gateway trajectory, route and schedule payloads.
 */

'use client';

import Link from 'next/link';
import dynamic from 'next/dynamic';
import { useDeferredValue, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  AlertTriangle,
  ArrowLeft,
  Bug,
  Clock3,
  MapPinned,
  Route as RouteIcon,
  TrainFront,
} from 'lucide-react';

import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input } from '@/components/ui';
import { gatewayApi, routeApi, scheduleApi, trainApi } from '@/lib/api/client';
import { useStaticMapData } from '@/lib/hooks';
import { buildPositionFromTrajectory, interpolateLineString } from '@/lib/trajectory-interpolation';
import { formatDelay, formatSpeed, getTrainTypeName } from '@/lib/utils';
import type { Route, Station, Train, TrainSchedule, TrainStopSequence, TrainTrajectory } from '@/types';
import type { ScheduleMapPoint, TrajectoryDebugPoint } from '@/components/Debug/TrainPointsDebugMap';

const TrainPointsDebugMap = dynamic(
  () => import('@/components/Debug/TrainPointsDebugMap'),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full min-h-[480px] items-center justify-center rounded-2xl border border-slate-200 bg-white">
        <div className="text-sm text-slate-500">Loading train debug map…</div>
      </div>
    ),
  },
);

const FULL_THAILAND_BBOX = '97.3000,5.3000,105.9000,20.8000';

interface TrainDebugListItem {
  id: number;
  trainNumber: string;
  trainType: string;
  name: string | null;
  operator: string | null;
  routeId: number | null;
  routeName: string | null;
  source: 'catalog' | 'trajectory' | 'merged';
  hasTrajectory: boolean;
}

function formatPointTime(timestampMs: number): string {
  return new Intl.DateTimeFormat('en-GB', {
    dateStyle: 'medium',
    timeStyle: 'medium',
    timeZone: 'Asia/Bangkok',
  }).format(timestampMs);
}

function percentage(value: number | null | undefined): string {
  if (typeof value !== 'number') return '—';
  return `${(value * 100).toFixed(1)}%`;
}

function compactDays(dayOfWeek: number[] | null | undefined): string {
  if (!dayOfWeek || dayOfWeek.length === 0) return '—';
  return dayOfWeek.join(', ');
}

function formatScheduleTime(time: string | null | undefined, dayOffset?: number): string {
  if (!time) return '—';
  if (!dayOffset) return time;
  return `${time} (+${dayOffset}d)`;
}

function buildTrajectoryPoints(trajectory: TrainTrajectory | null): TrajectoryDebugPoint[] {
  if (!trajectory) return [];

  const coordinateTimestamps = trajectory.properties.coordinate_timestamps;
  if (coordinateTimestamps && coordinateTimestamps.length > 0) {
    return coordinateTimestamps.map(([timestampMs, coordinate, rotation], index) => ({
      index,
      timestampMs,
      isoTime: formatPointTime(timestampMs),
      lon: coordinate[0],
      lat: coordinate[1],
      rotation,
      source: 'coordinate_timestamps',
      routeFraction: null,
    }));
  }

  const coordinates = trajectory.geometry.coordinates as [number, number][];
  return trajectory.properties.time_intervals.map(([timestampMs, routeFraction, rotation], index) => {
    const [lon, lat] = interpolateLineString(coordinates, routeFraction);
    return {
      index,
      timestampMs,
      isoTime: formatPointTime(timestampMs),
      lon,
      lat,
      rotation,
      source: 'time_intervals',
      routeFraction,
    };
  });
}

function buildSchedulePoints(
  schedule: TrainSchedule | undefined,
  stationsById: Map<number, Station>,
): ScheduleMapPoint[] {
  if (!schedule) return [];

  const points = schedule.stops
    .map<ScheduleMapPoint | null>((stop) => {
      const station = stop.station_id ? stationsById.get(stop.station_id) : undefined;
      if (!station) return null;
      return {
        scheduleId: stop.id,
        sequence: stop.sequence,
        stationId: stop.station_id,
        stationName: stop.station_name || stop.station?.name || station.name,
        stationCode: stop.station?.code || station.code || null,
        arrivalTime: stop.arrival_time,
        departureTime: stop.departure_time,
        dayOfWeek: stop.day_of_week,
        routeProgress: stop.route_progress ?? null,
        lon: station.location.coordinates[0],
        lat: station.location.coordinates[1],
      };
    })
    .filter((value): value is ScheduleMapPoint => value !== null);

  return points.sort((left, right) => left.sequence - right.sequence);
}

function mergeTrains(
  trains: Train[],
  trajectories: TrainTrajectory[],
): TrainDebugListItem[] {
  const byId = new Map<number, TrainDebugListItem>();

  trains.forEach((train) => {
    byId.set(train.id, {
      id: train.id,
      trainNumber: train.train_number,
      trainType: train.train_type,
      name: train.name,
      operator: train.operator,
      routeId: train.current_route_id,
      routeName: train.current_route?.name ?? null,
      source: 'catalog',
      hasTrajectory: false,
    });
  });

  trajectories.forEach((trajectory) => {
    const props = trajectory.properties;
    const existing = byId.get(props.train_id);
    if (existing) {
      byId.set(props.train_id, {
        ...existing,
        trainNumber: existing.trainNumber || props.train_number,
        trainType: existing.trainType || props.train_type,
        routeId: existing.routeId ?? props.route_id,
        routeName: existing.routeName ?? props.route_identifier,
        source: 'merged',
        hasTrajectory: true,
      });
      return;
    }

    byId.set(props.train_id, {
      id: props.train_id,
      trainNumber: props.train_number,
      trainType: props.train_type,
      name: null,
      operator: null,
      routeId: props.route_id,
      routeName: props.route_identifier || null,
      source: 'trajectory',
      hasTrajectory: true,
    });
  });

  return Array.from(byId.values()).sort((left, right) =>
    left.trainNumber.localeCompare(right.trainNumber, undefined, { numeric: true }),
  );
}

function MetricCard({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <Card className="rounded-[24px] border-slate-200 bg-white/95">
      <CardContent className="flex items-center gap-3 p-4">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-slate-700">
          {icon}
        </div>
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-slate-500">{label}</p>
          <p className="mt-1 text-2xl font-semibold text-slate-950">{value}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function TrainInfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[132px_minmax(0,1fr)] gap-3 border-b border-slate-200 py-2 text-sm last:border-b-0">
      <dt className="text-slate-500">{label}</dt>
      <dd className="font-medium text-slate-950">{value}</dd>
    </div>
  );
}

export default function GatewayTrainDebugPage() {
  const [query, setQuery] = useState('');
  const [selectedTrainId, setSelectedTrainId] = useState<number | null>(null);
  const deferredQuery = useDeferredValue(query);

  const {
    data: allTrains = [],
    isLoading: trainsLoading,
    error: trainsError,
  } = useQuery({
    queryKey: ['gateway-debug-trains-all'],
    queryFn: () => trainApi.getAllPages(),
    staleTime: 60_000,
  });

  const {
    data: activeTrajectories = [],
    isLoading: trajectoriesLoading,
    error: trajectoriesError,
  } = useQuery({
    queryKey: ['gateway-debug-active-trajectories', FULL_THAILAND_BBOX],
    queryFn: () => gatewayApi.getTrajectories(FULL_THAILAND_BBOX),
    staleTime: 15_000,
  });

  const { data: staticMapData, error: staticMapError } = useStaticMapData();

  const stationsById = useMemo(() => {
    const next = new Map<number, Station>();
    (staticMapData?.stations ?? []).forEach((station) => {
      next.set(station.id, station);
    });
    return next;
  }, [staticMapData?.stations]);

  const trains = useMemo(
    () => mergeTrains(allTrains, activeTrajectories),
    [activeTrajectories, allTrains],
  );

  const normalizedQuery = deferredQuery.trim().toLowerCase();
  const filteredTrains = useMemo(() => {
    if (!normalizedQuery) return trains;
    return trains.filter((train) => {
      const haystack = [
        train.trainNumber,
        train.name ?? '',
        train.trainType,
        train.operator ?? '',
        train.routeName ?? '',
        train.source,
      ]
        .join(' ')
        .toLowerCase();
      return haystack.includes(normalizedQuery);
    });
  }, [normalizedQuery, trains]);

  useEffect(() => {
    if (!filteredTrains.length) {
      setSelectedTrainId(null);
      return;
    }
    if (selectedTrainId === null || !filteredTrains.some((train) => train.id === selectedTrainId)) {
      const firstActive = filteredTrains.find((train) => train.hasTrajectory) ?? filteredTrains[0];
      setSelectedTrainId(firstActive.id);
    }
  }, [filteredTrains, selectedTrainId]);

  const selectedTrain = useMemo(
    () => filteredTrains.find((train) => train.id === selectedTrainId) ?? null,
    [filteredTrains, selectedTrainId],
  );

  const selectedActiveTrajectory = useMemo(
    () => activeTrajectories.find((item) => item.properties.train_id === selectedTrainId) ?? null,
    [activeTrajectories, selectedTrainId],
  );

  const {
    data: trajectory,
    isLoading: trajectoryLoading,
    error: trajectoryError,
  } = useQuery({
    queryKey: ['gateway-train-trajectory', selectedTrainId],
    queryFn: () => gatewayApi.getTrainTrajectory(selectedTrainId as number),
    enabled: selectedTrainId !== null && selectedTrain?.hasTrajectory === true,
    staleTime: 10_000,
    initialData: selectedActiveTrajectory ?? undefined,
  });

  const {
    data: schedule,
    isLoading: scheduleLoading,
    error: scheduleError,
  } = useQuery({
    queryKey: ['gateway-train-schedule', selectedTrainId],
    queryFn: () => scheduleApi.getTrainSchedule(selectedTrainId as number),
    enabled: selectedTrainId !== null,
    staleTime: 60_000,
  });

  const routeId = selectedTrain?.routeId ?? trajectory?.properties.route_id ?? null;
  const {
    data: route,
    isLoading: routeLoading,
    error: routeError,
  } = useQuery<Route>({
    queryKey: ['gateway-debug-route', routeId],
    queryFn: () => routeApi.getById(routeId as number),
    enabled: routeId !== null,
    staleTime: 60_000,
  });

  const {
    data: stopSequence,
    isLoading: stopSequenceLoading,
    error: stopSequenceError,
  } = useQuery<TrainStopSequence>({
    queryKey: ['gateway-stop-sequence-debug', selectedTrainId],
    queryFn: () => gatewayApi.getStopSequence(selectedTrainId as number),
    enabled: selectedTrainId !== null && selectedTrain?.hasTrajectory === true,
    staleTime: 10_000,
  });

  const routeStations = useMemo(
    () =>
      route?.stations
        .map((station) => stationsById.get(station.id))
        .filter((station): station is Station => station !== undefined) ?? [],
    [route, stationsById],
  );

  const trajectoryPoints = useMemo(() => buildTrajectoryPoints(trajectory ?? null), [trajectory]);
  const schedulePoints = useMemo(
    () => buildSchedulePoints(schedule, stationsById),
    [schedule, stationsById],
  );
  const currentPosition = useMemo(
    () => (trajectory ? buildPositionFromTrajectory(trajectory, Date.now()) : null),
    [trajectory],
  );

  const diagnostics = useMemo(() => {
    const findings: Array<{ severity: 'error' | 'warning' | 'ok'; message: string }> = [];

    if (!selectedTrain) return findings;

    if (!trajectory) {
      findings.push({ severity: 'error', message: 'Trajectory payload is missing for the selected train.' });
    } else {
      if (trajectoryPoints.length === 0) {
        findings.push({ severity: 'error', message: 'Trajectory exists but contains no interpolatable points.' });
      }
      if (!trajectory.geometry.coordinates.length) {
        findings.push({ severity: 'error', message: 'Trajectory geometry is empty.' });
      }
      if (routeId !== null && trajectory.properties.route_id !== null && routeId !== trajectory.properties.route_id) {
        findings.push({
          severity: 'warning',
          message: `Route mismatch: train.route_id=${routeId}, trajectory.route_id=${trajectory.properties.route_id}.`,
        });
      }
    }

    if (!schedule) {
      findings.push({ severity: 'error', message: 'Schedule payload is missing for the selected train.' });
    } else {
      if (schedule.stops.length === 0) {
        findings.push({ severity: 'error', message: 'Schedule exists but has no stops.' });
      }
      const stopsWithoutStation = schedule.stops.filter((stop) => stop.station_id === null).length;
      if (stopsWithoutStation > 0) {
        findings.push({
          severity: 'warning',
          message: `${stopsWithoutStation} schedule stops have no station_id and cannot be plotted on the map.`,
        });
      }
      const stopsWithoutCoordinates = schedule.stops.filter((stop) => {
        if (!stop.station_id) return false;
        return !stationsById.has(stop.station_id);
      }).length;
      if (stopsWithoutCoordinates > 0) {
        findings.push({
          severity: 'warning',
          message: `${stopsWithoutCoordinates} schedule stops reference stations missing from static map data.`,
        });
      }
    }

    if (!route) {
      findings.push({ severity: 'warning', message: 'Reference route payload is missing for this train.' });
    } else {
      if (!route.line_geometry || route.line_geometry.coordinates.length < 2) {
        findings.push({ severity: 'warning', message: 'Reference route has no usable line geometry.' });
      }
      if (schedule && route.stations.length > 0 && schedule.stops.length > 0) {
        if (Math.abs(route.stations.length - schedule.stops.length) > 2) {
          findings.push({
            severity: 'warning',
            message: `Route station count (${route.stations.length}) differs from schedule stop count (${schedule.stops.length}).`,
          });
        }
      }
    }

    if (stopSequence && schedule) {
      if (stopSequence.length > schedule.stops.length) {
        findings.push({
          severity: 'warning',
          message: `Stop sequence count (${stopSequence.length}) exceeds schedule stop count (${schedule.stops.length}).`,
        });
      }
    }

    if (findings.length === 0) {
      findings.push({ severity: 'ok', message: 'No obvious mismatches detected across route, schedule and trajectory.' });
    }

    return findings;
  }, [route, routeId, schedule, selectedTrain, stationsById, stopSequence, trajectory, trajectoryPoints.length]);

  const summaryError = trainsError || trajectoriesError || staticMapError || scheduleError || routeError || trajectoryError || stopSequenceError;

  return (
    <main className="min-h-dvh bg-[linear-gradient(180deg,#f6f6f2_0%,#ebe9df_100%)] text-slate-950">
      <div className="mx-auto flex max-w-[1920px] flex-col gap-4 px-4 py-4 md:px-6">
        <section className="grid gap-4 rounded-[28px] border border-slate-200 bg-white/90 p-4 shadow-[0_24px_60px_-32px_rgba(15,23,42,0.45)] backdrop-blur md:grid-cols-[1.4fr_0.9fr]">
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-3">
              <Button asChild variant="outline" className="border-slate-300 bg-white">
                <Link href="/debug/gateway">
                  <ArrowLeft className="mr-2 h-4 w-4" />
                  Back to gateway debug
                </Link>
              </Button>
              <Button asChild variant="outline" className="border-slate-300 bg-white">
                <Link href="/">
                  <Bug className="mr-2 h-4 w-4" />
                  Main map
                </Link>
              </Button>
              {selectedTrain && (
                <Badge variant="outline" className="border-slate-300 text-slate-700">
                  Train #{selectedTrain.trainNumber}
                </Badge>
              )}
              <Badge variant="outline" className="border-slate-300 text-slate-700">
                Active trajectories {activeTrajectories.length}
              </Badge>
            </div>
            <div>
              <p className="text-xs font-medium uppercase tracking-[0.28em] text-slate-500">
                Gateway debug
              </p>
              <h1 className="mt-2 text-3xl font-semibold tracking-tight md:text-4xl">
                Train route, schedule and trajectory diagnostics
              </h1>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
                This screen merges the train catalog, live trajectory payloads, reference route data
                and schedule stops. It is designed to surface exactly where the mismatch is:
                missing trajectory, wrong route, incomplete schedule or station mapping problems.
              </p>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <MetricCard icon={<TrainFront className="h-5 w-5" />} label="Train entries" value={String(trains.length)} />
            <MetricCard icon={<Clock3 className="h-5 w-5" />} label="Trajectory points" value={String(trajectoryPoints.length)} />
            <MetricCard icon={<MapPinned className="h-5 w-5" />} label="Schedule points" value={String(schedulePoints.length)} />
            <MetricCard icon={<RouteIcon className="h-5 w-5" />} label="Route stations" value={String(route?.stations.length ?? 0)} />
          </div>
        </section>

        <section className="grid min-h-0 gap-4 xl:grid-cols-[360px_minmax(0,1fr)_560px]">
          <Card className="min-h-0 overflow-hidden rounded-[24px] border-slate-200 bg-white/95">
            <CardHeader className="border-b border-slate-200 pb-4">
              <CardTitle className="text-xl">Trains</CardTitle>
              <CardDescription>
                Catalog trains are merged with live gateway trajectories, so active trains still appear
                even if the catalog request is incomplete.
              </CardDescription>
              <Input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search train number, route, source"
                className="border-slate-300 bg-slate-50"
              />
              {summaryError ? (
                <div className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
                  Some requests failed. Partial diagnostics are still shown where possible.
                </div>
              ) : null}
            </CardHeader>
            <CardContent className="max-h-[calc(100dvh-280px)] overflow-y-auto p-0">
              {trainsLoading && trajectoriesLoading ? (
                <div className="p-6 text-sm text-slate-500">Loading trains…</div>
              ) : filteredTrains.length === 0 ? (
                <div className="p-6 text-sm text-slate-500">
                  No trains available from either the catalog or gateway trajectories.
                </div>
              ) : (
                <ul className="divide-y divide-slate-200">
                  {filteredTrains.map((train) => {
                    const active = train.id === selectedTrainId;
                    return (
                      <li key={train.id}>
                        <button
                          type="button"
                          onClick={() => setSelectedTrainId(train.id)}
                          className={`flex w-full flex-col gap-2 px-4 py-4 text-left transition ${
                            active ? 'bg-slate-950 text-white' : 'bg-white hover:bg-slate-50'
                          }`}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <div className="text-base font-semibold">#{train.trainNumber}</div>
                              <div className={active ? 'text-slate-300' : 'text-slate-500'}>
                                {train.name || 'Unnamed train'}
                              </div>
                            </div>
                            <div className="flex flex-wrap justify-end gap-2">
                              <Badge variant={active ? 'secondary' : 'outline'}>
                                {getTrainTypeName(train.trainType)}
                              </Badge>
                              <Badge variant={train.hasTrajectory ? 'success' : 'outline'}>
                                {train.hasTrajectory ? 'trajectory' : 'catalog only'}
                              </Badge>
                            </div>
                          </div>
                          <div className={`text-xs ${active ? 'text-slate-300' : 'text-slate-500'}`}>
                            {train.routeName || 'No route'} • {train.operator || 'Unknown operator'} • {train.source}
                          </div>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card className="min-h-0 overflow-hidden rounded-[24px] border-slate-200 bg-white/95">
            <CardHeader className="border-b border-slate-200 pb-4">
              <CardTitle className="text-xl">Map</CardTitle>
              <CardDescription>
                Dashed line is the reference route. Solid line is the live trajectory. Gray points are route stations,
                blue points are schedule stops, orange points are trajectory samples.
              </CardDescription>
            </CardHeader>
            <CardContent className="h-[calc(100dvh-280px)] p-0">
              <TrainPointsDebugMap
                trajectory={trajectory ?? null}
                trajectoryPoints={trajectoryPoints}
                schedulePoints={schedulePoints}
                route={route ?? null}
                routeStations={routeStations}
              />
            </CardContent>
          </Card>

          <div className="grid min-h-0 gap-4">
            <Card className="rounded-[24px] border-slate-200 bg-white/95">
              <CardHeader className="border-b border-slate-200 pb-4">
                <CardTitle className="text-xl">Diagnostics</CardTitle>
                <CardDescription>
                  These findings point to the broken layer: schedule, route mapping or trajectory generation.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3 p-4">
                {diagnostics.map((finding) => (
                  <div
                    key={finding.message}
                    className={`rounded-xl border px-3 py-3 text-sm ${
                      finding.severity === 'error'
                        ? 'border-rose-300 bg-rose-50 text-rose-900'
                        : finding.severity === 'warning'
                          ? 'border-amber-300 bg-amber-50 text-amber-900'
                          : 'border-emerald-300 bg-emerald-50 text-emerald-900'
                    }`}
                  >
                    <div className="flex items-start gap-2">
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                      <span>{finding.message}</span>
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>

            <Card className="rounded-[24px] border-slate-200 bg-white/95">
              <CardHeader className="border-b border-slate-200 pb-4">
                <CardTitle className="text-xl">Selected train</CardTitle>
                <CardDescription>
                  Consolidated snapshot from train catalog, trajectory and reference route.
                </CardDescription>
              </CardHeader>
              <CardContent className="p-4">
                {!selectedTrain ? (
                  <div className="text-sm text-slate-500">Select a train to inspect.</div>
                ) : (
                  <dl>
                    <TrainInfoRow label="Train" value={`#${selectedTrain.trainNumber}`} />
                    <TrainInfoRow label="Type" value={getTrainTypeName(selectedTrain.trainType)} />
                    <TrainInfoRow label="Source" value={selectedTrain.source} />
                    <TrainInfoRow label="Name" value={selectedTrain.name || '—'} />
                    <TrainInfoRow label="Operator" value={selectedTrain.operator || '—'} />
                    <TrainInfoRow label="Route" value={route?.name || selectedTrain.routeName || '—'} />
                    <TrainInfoRow label="Route id" value={String(routeId ?? '—')} />
                    <TrainInfoRow label="Status" value={currentPosition?.status || '—'} />
                    <TrainInfoRow label="Delay" value={formatDelay(currentPosition?.delay_minutes ?? 0)} />
                    <TrainInfoRow label="Speed" value={formatSpeed(currentPosition?.speed ?? null)} />
                    <TrainInfoRow label="Prev station" value={currentPosition?.prev_station || '—'} />
                    <TrainInfoRow label="Next station" value={currentPosition?.next_station || '—'} />
                    <TrainInfoRow label="ETA next" value={currentPosition?.eta_next_station || '—'} />
                    <TrainInfoRow label="Route progress" value={percentage(currentPosition?.route_progress)} />
                    <TrainInfoRow label="Topology version" value={trajectory?.properties.topology_version || '—'} />
                  </dl>
                )}
              </CardContent>
            </Card>

            <Card className="min-h-0 overflow-hidden rounded-[24px] border-slate-200 bg-white/95">
              <CardHeader className="border-b border-slate-200 pb-4">
                <CardTitle className="text-xl">Trajectory points</CardTitle>
                <CardDescription>
                  Estimated points and timestamps from the gateway trajectory payload.
                </CardDescription>
              </CardHeader>
              <CardContent className="max-h-[300px] overflow-auto p-0">
                {trajectoryLoading ? (
                  <div className="p-4 text-sm text-slate-500">Loading trajectory…</div>
                ) : trajectoryPoints.length === 0 ? (
                  <div className="p-4 text-sm text-slate-500">No trajectory points returned for this train.</div>
                ) : (
                  <table className="min-w-full text-left text-sm">
                    <thead className="sticky top-0 bg-slate-100 text-slate-700">
                      <tr>
                        <th className="px-3 py-2 font-medium">#</th>
                        <th className="px-3 py-2 font-medium">Time</th>
                        <th className="px-3 py-2 font-medium">Point</th>
                        <th className="px-3 py-2 font-medium">Rotation</th>
                        <th className="px-3 py-2 font-medium">Source</th>
                      </tr>
                    </thead>
                    <tbody>
                      {trajectoryPoints.map((point) => (
                        <tr key={`${point.timestampMs}-${point.index}`} className="border-t border-slate-200">
                          <td className="px-3 py-2 text-slate-500">{point.index + 1}</td>
                          <td className="px-3 py-2 font-medium">{point.isoTime}</td>
                          <td className="px-3 py-2 text-slate-600">
                            {point.lat.toFixed(5)}, {point.lon.toFixed(5)}
                          </td>
                          <td className="px-3 py-2 text-slate-600">{point.rotation.toFixed(1)}°</td>
                          <td className="px-3 py-2 text-slate-600">
                            {point.source === 'time_intervals' && typeof point.routeFraction === 'number'
                              ? `${point.source} ${(point.routeFraction * 100).toFixed(2)}%`
                              : point.source}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </CardContent>
            </Card>

            <Card className="min-h-0 overflow-hidden rounded-[24px] border-slate-200 bg-white/95">
              <CardHeader className="border-b border-slate-200 pb-4">
                <CardTitle className="text-xl">Schedule and stop sequence</CardTitle>
                <CardDescription>
                  Compare planned stops from the train schedule with gateway stop sequence.
                </CardDescription>
              </CardHeader>
              <CardContent className="max-h-[340px] overflow-auto p-0">
                {scheduleLoading || stopSequenceLoading || routeLoading ? (
                  <div className="p-4 text-sm text-slate-500">Loading schedule diagnostics…</div>
                ) : !schedule ? (
                  <div className="p-4 text-sm text-slate-500">No schedule payload found for this train.</div>
                ) : (
                  <table className="min-w-full text-left text-sm">
                    <thead className="sticky top-0 bg-slate-100 text-slate-700">
                      <tr>
                        <th className="px-3 py-2 font-medium">Seq</th>
                        <th className="px-3 py-2 font-medium">Schedule stop</th>
                        <th className="px-3 py-2 font-medium">Route</th>
                        <th className="px-3 py-2 font-medium">Gateway stopsequence</th>
                      </tr>
                    </thead>
                    <tbody>
                      {schedule.stops.map((stop, index) => {
                        const routeStation = route?.stations.find((item) => item.sequence === stop.sequence) ?? null;
                        const gatewayStop = stopSequence?.find((item) => item.sequence === stop.sequence) ?? null;
                        return (
                          <tr key={stop.id} className="border-t border-slate-200 align-top">
                            <td className="px-3 py-2 text-slate-500">{stop.sequence}</td>
                            <td className="px-3 py-2">
                              <div className="font-medium">
                                {stop.station_name || stop.station?.name || 'Unnamed stop'}
                              </div>
                              <div className="text-xs text-slate-500">
                                Arr {formatScheduleTime(stop.arrival_time, stop.arrival_day_offset)} • Dep{' '}
                                {formatScheduleTime(stop.departure_time, stop.departure_day_offset)}
                              </div>
                              <div className="text-xs text-slate-500">
                                Days {compactDays(stop.day_of_week)} • map {stop.station_id ? 'yes' : 'no'}
                              </div>
                            </td>
                            <td className="px-3 py-2 text-slate-600">
                              {routeStation ? (
                                <div>
                                  <div className="font-medium">{routeStation.name}</div>
                                  <div className="text-xs text-slate-500">{routeStation.code}</div>
                                </div>
                              ) : (
                                '—'
                              )}
                            </td>
                            <td className="px-3 py-2 text-slate-600">
                              {gatewayStop ? (
                                <div>
                                  <div className="font-medium">{gatewayStop.station_name}</div>
                                  <div className="text-xs text-slate-500">
                                    {gatewayStop.state} • delay {gatewayStop.delay_minutes} min
                                  </div>
                                </div>
                              ) : (
                                index < (stopSequence?.length ?? 0) ? 'sequence mismatch' : '—'
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
              </CardContent>
            </Card>
          </div>
        </section>
      </div>
    </main>
  );
}
