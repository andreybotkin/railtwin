/**
 * Gateway payload debug page for route and train diagnostics.
 */

'use client';

import Link from 'next/link';
import dynamic from 'next/dynamic';
import { useDeferredValue, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  ArrowLeft,
  CircleAlert,
  MapPinned,
  Network,
  Route as RouteIcon,
  TrainFront,
} from 'lucide-react';

import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input } from '@/components/ui';
import { useRoutes, useStaticMapData, useTrainTrajectories } from '@/lib/hooks';
import { gatewayApi } from '@/lib/api/client';
import { getTrajectoryClient } from '@/lib/websocket';
import { buildPositionFromTrajectory } from '@/lib/trajectory-interpolation';
import { cn, formatDelay, formatSpeed, getRouteColor, getRouteTypeName, getTrainTypeName } from '@/lib/utils';
import type { Route, Station, TrainPositionUpdate, TrainStopSequence, TrainTrajectory } from '@/types';

const GatewayDebugMap = dynamic(
  () => import('@/components/Debug/GatewayDebugMap'),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full min-h-[420px] items-center justify-center rounded-2xl border border-slate-200 bg-white">
        <div className="text-sm text-slate-500">Loading debug map…</div>
      </div>
    ),
  },
);

const FULL_THAILAND_BBOX = '97.3000,5.3000,105.9000,20.8000';

interface TrainTableRow {
  trajectory: TrainTrajectory;
  position: TrainPositionUpdate;
}

function percentage(value: number | null | undefined): string {
  if (typeof value !== 'number') return '—';
  return `${(value * 100).toFixed(1)}%`;
}

function compactJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

export default function GatewayDebugPage() {
  const [routeQuery, setRouteQuery] = useState('');
  const [selectedRouteId, setSelectedRouteId] = useState<number | null>(null);
  const [selectedTrainId, setSelectedTrainId] = useState<number | null>(null);
  const deferredRouteQuery = useDeferredValue(routeQuery);

  const { data: routesResponse, isLoading: routesLoading } = useRoutes();
  const { data: staticMapData, isLoading: staticMapLoading } = useStaticMapData();
  const { trajectories, isConnected } = useTrainTrajectories();

  const { data: topology } = useQuery({
    queryKey: ['gateway-topology'],
    queryFn: gatewayApi.getTopology,
    staleTime: 60_000,
  });

  const { data: initialTrajectories = [] } = useQuery({
    queryKey: ['gateway-trajectories', FULL_THAILAND_BBOX],
    queryFn: () => gatewayApi.getTrajectories(FULL_THAILAND_BBOX),
    staleTime: 15_000,
  });

  useEffect(() => {
    getTrajectoryClient().sendBBox(FULL_THAILAND_BBOX);
  }, []);

  const routes = routesResponse?.items ?? [];
  const routeSearch = deferredRouteQuery.trim().toLowerCase();

  const filteredRoutes = useMemo(() => {
    if (!routeSearch) return routes;
    return routes.filter((route) => {
      const haystack = [
        route.name,
        route.name_th ?? '',
        route.route_type,
        ...route.stations.map((station) => `${station.name} ${station.code}`),
      ]
        .join(' ')
        .toLowerCase();
      return haystack.includes(routeSearch);
    });
  }, [routeSearch, routes]);

  useEffect(() => {
    if (!filteredRoutes.length) {
      setSelectedRouteId(null);
      return;
    }
    if (selectedRouteId === null || !filteredRoutes.some((route) => route.id === selectedRouteId)) {
      setSelectedRouteId(filteredRoutes[0].id);
    }
  }, [filteredRoutes, selectedRouteId]);

  const selectedRoute = useMemo(
    () => routes.find((route) => route.id === selectedRouteId) ?? null,
    [routes, selectedRouteId],
  );

  const stationsById = useMemo(() => {
    const next = new Map<number, Station>();
    (staticMapData?.stations ?? []).forEach((station) => {
      next.set(station.id, station);
    });
    return next;
  }, [staticMapData?.stations]);

  const routeStations = useMemo(
    () =>
      selectedRoute?.stations
        .map((station) => stationsById.get(station.id))
        .filter((station): station is Station => station !== undefined) ?? [],
    [selectedRoute, stationsById],
  );

  const trajectoryList = useMemo(
    () => (trajectories.size > 0 ? Array.from(trajectories.values()) : initialTrajectories),
    [initialTrajectories, trajectories],
  );

  const trainRows = useMemo(() => {
    const nowMs = Date.now();
    return trajectoryList
      .filter((trajectory) => {
        if (selectedRouteId === null) return true;
        return trajectory.properties.route_id === selectedRouteId;
      })
      .map((trajectory) => ({
        trajectory,
        position: buildPositionFromTrajectory(trajectory, nowMs),
      }))
      .filter((row): row is TrainTableRow => row.position !== null)
      .sort((left, right) => {
        const leftProgress = left.position.route_progress ?? -1;
        const rightProgress = right.position.route_progress ?? -1;
        if (leftProgress !== rightProgress) return rightProgress - leftProgress;
        return left.position.train_number.localeCompare(right.position.train_number, undefined, {
          numeric: true,
        });
      });
  }, [selectedRouteId, trajectoryList]);

  useEffect(() => {
    if (!trainRows.length) {
      setSelectedTrainId(null);
      return;
    }
    if (selectedTrainId === null || !trainRows.some((row) => row.position.train_id === selectedTrainId)) {
      setSelectedTrainId(trainRows[0].position.train_id);
    }
  }, [selectedTrainId, trainRows]);

  const selectedTrain = useMemo(
    () => trainRows.find((row) => row.position.train_id === selectedTrainId) ?? null,
    [selectedTrainId, trainRows],
  );

  const { data: stopSequence } = useQuery<TrainStopSequence>({
    queryKey: ['gateway-stop-sequence', selectedTrainId],
    queryFn: () => gatewayApi.getStopSequence(selectedTrainId as number),
    enabled: selectedTrainId !== null,
    staleTime: 10_000,
  });

  return (
    <main className="min-h-dvh bg-[linear-gradient(180deg,#f6f6f2_0%,#ebe9df_100%)] text-slate-950">
      <div className="mx-auto flex max-w-[1800px] flex-col gap-4 px-4 py-4 md:px-6">
        <section className="grid gap-4 rounded-[28px] border border-slate-200 bg-white/90 p-4 shadow-[0_24px_60px_-32px_rgba(15,23,42,0.45)] backdrop-blur md:grid-cols-[1.4fr_0.9fr]">
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-3">
              <Button asChild variant="outline" className="border-slate-300 bg-white">
                <Link href="/">
                  <ArrowLeft className="mr-2 h-4 w-4" />
                  Back to map
                </Link>
              </Button>
              <Button asChild variant="outline" className="border-slate-300 bg-white">
                <Link href="/debug/gateway/trains">
                  <TrainFront className="mr-2 h-4 w-4" />
                  Train point debug
                </Link>
              </Button>
              <Badge variant={isConnected ? 'success' : 'warning'}>
                Gateway WS {isConnected ? 'connected' : 'connecting'}
              </Badge>
              {topology && (
                <Badge variant="outline" className="border-slate-300 text-slate-700">
                  Topology {topology.topology_version}
                </Badge>
              )}
            </div>
            <div>
              <p className="text-xs font-medium uppercase tracking-[0.28em] text-slate-500">
                Gateway debug
              </p>
              <h1 className="mt-2 text-3xl font-semibold tracking-tight md:text-4xl">
                Route diagnostics for gateway payloads
              </h1>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
                Separate screen to inspect what the frontend receives from gateway:
                route geometry, current train trajectories, stop sequence, topology version
                and graph edge references. Useful when train movement on the main map looks wrong.
              </p>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <MetricCard icon={<RouteIcon className="h-5 w-5" />} label="Routes" value={String(routes.length)} />
            <MetricCard icon={<TrainFront className="h-5 w-5" />} label="Live trains" value={String(trajectoryList.length)} />
            <MetricCard
              icon={<MapPinned className="h-5 w-5" />}
              label="Route stations"
              value={String(selectedRoute?.stations.length ?? 0)}
              accent={selectedRoute?.route_type ? getRouteColor(selectedRoute.route_type) : undefined}
            />
            <MetricCard
              icon={<Network className="h-5 w-5" />}
              label="Physical edges"
              value={topology ? String(topology.physical_edges_count) : '—'}
            />
          </div>
        </section>

        <section className="grid min-h-0 gap-4 xl:grid-cols-[320px_minmax(0,1fr)_420px]">
          <Card className="min-h-0 overflow-hidden rounded-[24px] border-slate-200 bg-white/95">
            <CardHeader className="border-b border-slate-200 pb-4">
              <CardTitle className="text-xl">Routes</CardTitle>
              <CardDescription>
                Filter routes and inspect the route selected for debug map and train table.
              </CardDescription>
              <Input
                value={routeQuery}
                onChange={(event) => setRouteQuery(event.target.value)}
                placeholder="Search route, station, type"
                className="border-slate-300 bg-slate-50"
              />
            </CardHeader>
            <CardContent className="max-h-[calc(100dvh-280px)] overflow-y-auto p-0">
              {routesLoading ? (
                <div className="p-6 text-sm text-slate-500">Loading routes…</div>
              ) : filteredRoutes.length === 0 ? (
                <div className="p-6 text-sm text-slate-500">No routes match the current filter.</div>
              ) : (
                <ul className="divide-y divide-slate-200">
                  {filteredRoutes.map((route) => {
                    const active = route.id === selectedRouteId;
                    return (
                      <li key={route.id}>
                        <button
                          type="button"
                          onClick={() => setSelectedRouteId(route.id)}
                          className={cn(
                            'w-full px-4 py-4 text-left transition-colors',
                            active ? 'bg-slate-950 text-white' : 'bg-white hover:bg-slate-50',
                          )}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <div className="font-medium">{route.name}</div>
                              <div className={cn('text-xs', active ? 'text-slate-300' : 'text-slate-500')}>
                                {getRouteTypeName(route.route_type)}
                              </div>
                            </div>
                            <span
                              className="mt-1 h-3 w-3 rounded-full"
                              style={{ backgroundColor: route.color || getRouteColor(route.route_type) }}
                            />
                          </div>
                          <div className={cn('mt-3 flex items-center gap-2 text-xs', active ? 'text-slate-300' : 'text-slate-500')}>
                            <span>{route.stations.length} stations</span>
                            <span>•</span>
                            <span>{route.distance_km ? `${route.distance_km.toFixed(1)} km` : 'distance n/a'}</span>
                          </div>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </CardContent>
          </Card>

          <div className="grid min-h-0 gap-4">
            <Card className="overflow-hidden rounded-[24px] border-slate-200 bg-white/95">
              <CardHeader className="border-b border-slate-200 pb-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <CardTitle className="text-xl">
                      {selectedRoute ? selectedRoute.name : 'Route map'}
                    </CardTitle>
                    <CardDescription>
                      Geometry from route API and live train payload from gateway trajectories.
                    </CardDescription>
                  </div>
                  {selectedRoute && (
                    <Badge
                      variant="outline"
                      className="border-slate-300 text-slate-700"
                    >
                      {getRouteTypeName(selectedRoute.route_type)}
                    </Badge>
                  )}
                </div>
              </CardHeader>
              <CardContent className="p-0">
                <div className="h-[440px]">
                  <GatewayDebugMap
                    route={selectedRoute}
                    routeStations={routeStations}
                    trainEntries={trainRows.map((row) => ({
                      trajectory: row.trajectory,
                      position: row.position,
                    }))}
                    selectedTrainId={selectedTrainId}
                    onTrainSelect={setSelectedTrainId}
                  />
                </div>
              </CardContent>
            </Card>

            <Card className="overflow-hidden rounded-[24px] border-slate-200 bg-white/95">
              <CardHeader className="border-b border-slate-200 pb-4">
                <CardTitle className="text-xl">Gateway train table</CardTitle>
                <CardDescription>
                  Live rows built from gateway trajectory properties and interpolated current position.
                </CardDescription>
              </CardHeader>
              <CardContent className="max-h-[380px] overflow-auto p-0">
                <table className="min-w-full text-sm">
                  <thead className="sticky top-0 bg-slate-100 text-left text-xs uppercase tracking-[0.18em] text-slate-500">
                    <tr>
                      <th className="px-4 py-3">Train</th>
                      <th className="px-4 py-3">Status</th>
                      <th className="px-4 py-3">Prev → Next</th>
                      <th className="px-4 py-3">Delay</th>
                      <th className="px-4 py-3">Speed</th>
                      <th className="px-4 py-3">Route %</th>
                      <th className="px-4 py-3">Edge</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trainRows.map(({ trajectory, position }) => {
                      const active = position.train_id === selectedTrainId;
                      return (
                        <tr
                          key={position.train_id}
                          className={cn(
                            'cursor-pointer border-t border-slate-200 transition-colors',
                            active ? 'bg-amber-50' : 'hover:bg-slate-50',
                          )}
                          onClick={() => setSelectedTrainId(position.train_id)}
                        >
                          <td className="px-4 py-3 align-top">
                            <div className="font-medium">{position.train_number}</div>
                            <div className="text-xs text-slate-500">
                              {getTrainTypeName(position.train_type)}
                            </div>
                          </td>
                          <td className="px-4 py-3 align-top">
                            <Badge variant={position.delay_minutes > 0 ? 'warning' : 'secondary'}>
                              {position.status}
                            </Badge>
                          </td>
                          <td className="px-4 py-3 align-top text-slate-600">
                            <div>{position.prev_station || '—'}</div>
                            <div className="text-xs text-slate-400">to {position.next_station || '—'}</div>
                          </td>
                          <td className="px-4 py-3 align-top">{formatDelay(position.delay_minutes)}</td>
                          <td className="px-4 py-3 align-top">{formatSpeed(position.speed)}</td>
                          <td className="px-4 py-3 align-top">{percentage(position.route_progress)}</td>
                          <td className="px-4 py-3 align-top">
                            {trajectory.properties.current_edge_id ?? '—'}
                          </td>
                        </tr>
                      );
                    })}
                    {trainRows.length === 0 && (
                      <tr>
                        <td className="px-4 py-6 text-slate-500" colSpan={7}>
                          No live gateway trains for the selected route.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          </div>

          <div className="grid min-h-0 gap-4">
            <Card className="overflow-hidden rounded-[24px] border-slate-200 bg-white/95">
              <CardHeader className="border-b border-slate-200 pb-4">
                <CardTitle className="text-xl">Selected train</CardTitle>
                <CardDescription>
                  Gateway payload fields for the train currently highlighted in the table/map.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {selectedTrain ? (
                  <>
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-2xl font-semibold">
                          Train {selectedTrain.position.train_number}
                        </div>
                        <div className="text-sm text-slate-500">
                          {getTrainTypeName(selectedTrain.position.train_type)}
                        </div>
                      </div>
                      <Badge variant={selectedTrain.position.delay_minutes > 0 ? 'warning' : 'success'}>
                        {formatDelay(selectedTrain.position.delay_minutes)}
                      </Badge>
                    </div>

                    <dl className="grid grid-cols-2 gap-3 text-sm">
                      <DebugStat label="Previous station" value={selectedTrain.position.prev_station || '—'} />
                      <DebugStat label="Next station" value={selectedTrain.position.next_station || '—'} />
                      <DebugStat label="ETA next" value={selectedTrain.position.eta_next_station || '—'} />
                      <DebugStat label="Speed" value={formatSpeed(selectedTrain.position.speed)} />
                      <DebugStat label="Route progress" value={percentage(selectedTrain.position.route_progress)} />
                      <DebugStat label="Segment progress" value={percentage(selectedTrain.position.segment_progress)} />
                      <DebugStat label="Current edge" value={String(selectedTrain.trajectory.properties.current_edge_id ?? '—')} />
                      <DebugStat label="Topology" value={selectedTrain.trajectory.properties.topology_version || '—'} />
                    </dl>

                    <div>
                      <div className="mb-2 flex items-center gap-2 text-sm font-medium">
                        <CircleAlert className="h-4 w-4 text-amber-600" />
                        Stop sequence from gateway
                      </div>
                      <div className="max-h-[220px] overflow-auto rounded-xl border border-slate-200">
                        <table className="min-w-full text-xs">
                          <thead className="sticky top-0 bg-slate-100 text-left uppercase tracking-[0.18em] text-slate-500">
                            <tr>
                              <th className="px-3 py-2">#</th>
                              <th className="px-3 py-2">Station</th>
                              <th className="px-3 py-2">State</th>
                              <th className="px-3 py-2">Delay</th>
                            </tr>
                          </thead>
                          <tbody>
                            {(stopSequence ?? []).map((stop) => (
                              <tr key={`${stop.sequence}-${stop.station_name}`} className="border-t border-slate-200">
                                <td className="px-3 py-2">{stop.sequence}</td>
                                <td className="px-3 py-2">{stop.station_name}</td>
                                <td className="px-3 py-2">{stop.state}</td>
                                <td className="px-3 py-2">{formatDelay(stop.delay_minutes)}</td>
                              </tr>
                            ))}
                            {!stopSequence?.length && (
                              <tr>
                                <td className="px-3 py-3 text-slate-500" colSpan={4}>
                                  No stop sequence available.
                                </td>
                              </tr>
                            )}
                          </tbody>
                        </table>
                      </div>
                    </div>

                    <div>
                      <div className="mb-2 text-sm font-medium">Raw gateway trajectory properties</div>
                      <pre className="max-h-[320px] overflow-auto rounded-xl bg-slate-950 p-4 text-[11px] leading-5 text-slate-100">
                        {compactJson(selectedTrain.trajectory.properties)}
                      </pre>
                    </div>
                  </>
                ) : (
                  <div className="text-sm text-slate-500">
                    Select a train from the route table or click a marker on the map.
                  </div>
                )}
              </CardContent>
            </Card>

            <Card className="overflow-hidden rounded-[24px] border-slate-200 bg-white/95">
              <CardHeader className="border-b border-slate-200 pb-4">
                <CardTitle className="text-xl">Selected route stations</CardTitle>
                <CardDescription>
                  Ordered station list for the route shown on the debug map.
                </CardDescription>
              </CardHeader>
              <CardContent className="max-h-[320px] overflow-auto p-0">
                <table className="min-w-full text-sm">
                  <thead className="sticky top-0 bg-slate-100 text-left text-xs uppercase tracking-[0.18em] text-slate-500">
                    <tr>
                      <th className="px-4 py-3">Seq</th>
                      <th className="px-4 py-3">Station</th>
                      <th className="px-4 py-3">Code</th>
                      <th className="px-4 py-3">Distance</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedRoute?.stations.map((station) => (
                      <tr key={`${selectedRoute.id}-${station.id}`} className="border-t border-slate-200">
                        <td className="px-4 py-3">{station.sequence}</td>
                        <td className="px-4 py-3">{station.name}</td>
                        <td className="px-4 py-3 text-slate-500">{station.code}</td>
                        <td className="px-4 py-3">
                          {typeof station.distance_from_start === 'number'
                            ? `${station.distance_from_start.toFixed(1)} km`
                            : '—'}
                        </td>
                      </tr>
                    ))}
                    {!selectedRoute && (
                      <tr>
                        <td className="px-4 py-6 text-slate-500" colSpan={4}>
                          Select a route to inspect its stations.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          </div>
        </section>

        {(routesLoading || staticMapLoading) && (
          <div className="text-sm text-slate-500">
            Loading route and map data…
          </div>
        )}
      </div>
    </main>
  );
}

function MetricCard({
  icon,
  label,
  value,
  accent,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  accent?: string;
}) {
  return (
    <div className="rounded-[20px] border border-slate-200 bg-slate-50 p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="rounded-full bg-white p-2 text-slate-700 shadow-sm" style={accent ? { color: accent } : undefined}>
          {icon}
        </div>
        <div className="text-2xl font-semibold">{value}</div>
      </div>
      <div className="mt-3 text-xs font-medium uppercase tracking-[0.18em] text-slate-500">
        {label}
      </div>
    </div>
  );
}

function DebugStat({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
      <dt className="text-xs uppercase tracking-[0.16em] text-slate-500">{label}</dt>
      <dd className="mt-1 break-words font-medium text-slate-900">{value}</dd>
    </div>
  );
}
