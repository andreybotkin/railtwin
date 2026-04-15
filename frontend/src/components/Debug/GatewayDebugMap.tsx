/**
 * Dedicated debug map for inspecting gateway route and train payloads.
 */

'use client';

import { useEffect, useMemo } from 'react';
import { MapContainer, TileLayer, Polyline, CircleMarker, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

import type { Route, Station, TrainPositionUpdate, TrainTrajectory } from '@/types';
import { formatDelay, formatSpeed, getRouteColor, getTrainTypeName } from '@/lib/utils';
import { Badge } from '@/components/ui';

const THAILAND_CENTER: [number, number] = [15.87, 100.9925];
const INITIAL_ZOOM = 6;

delete (L.Icon.Default.prototype as { _getIconUrl?: unknown })._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
});

interface TrainMapEntry {
  trajectory: TrainTrajectory;
  position: TrainPositionUpdate;
}

interface GatewayDebugMapProps {
  route: Route | null;
  routeStations: Station[];
  trainEntries: TrainMapEntry[];
  selectedTrainId: number | null;
  onTrainSelect: (trainId: number | null) => void;
}

function FitToSelection({
  route,
  trainEntries,
}: {
  route: Route | null;
  trainEntries: TrainMapEntry[];
}) {
  const map = useMap();

  useEffect(() => {
    const bounds = new L.LatLngBounds([]);

    if (route?.line_geometry?.coordinates.length) {
      route.line_geometry.coordinates.forEach(([lon, lat]) => {
        bounds.extend([lat, lon]);
      });
    }

    trainEntries.forEach(({ position }) => {
      bounds.extend([
        position.location.coordinates[1],
        position.location.coordinates[0],
      ]);
    });

    if (bounds.isValid()) {
      map.fitBounds(bounds.pad(0.15), { animate: false, maxZoom: 11 });
    }
  }, [map, route, trainEntries]);

  return null;
}

function trainMarkerColor(delayMinutes: number): string {
  if (delayMinutes <= 0) return '#2f855a';
  if (delayMinutes <= 5) return '#d69e2e';
  if (delayMinutes <= 15) return '#dd6b20';
  return '#c53030';
}

export default function GatewayDebugMap({
  route,
  routeStations,
  trainEntries,
  selectedTrainId,
  onTrainSelect,
}: GatewayDebugMapProps) {
  const polylinePositions = useMemo(
    () =>
      route?.line_geometry?.coordinates.map(([lon, lat]) => [lat, lon] as [number, number]) ?? [],
    [route],
  );

  const stationPositions = useMemo(
    () =>
      routeStations.map((station) => ({
        ...station,
        lat: station.location.coordinates[1],
        lon: station.location.coordinates[0],
      })),
    [routeStations],
  );

  return (
    <MapContainer
      center={THAILAND_CENTER}
      zoom={INITIAL_ZOOM}
      className="h-full w-full"
      attributionControl={false}
      zoomControl
      scrollWheelZoom
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
      />

      <FitToSelection route={route} trainEntries={trainEntries} />

      {polylinePositions.length >= 2 && (
        <Polyline
          positions={polylinePositions}
          pathOptions={{
            color: route?.color || getRouteColor(route?.route_type || ''),
            weight: 5,
            opacity: 0.85,
          }}
        />
      )}

      {stationPositions.map((station) => (
        <CircleMarker
          key={`station-${station.id}`}
          center={[station.lat, station.lon]}
          radius={5}
          pathOptions={{
            color: '#111827',
            weight: 1,
            fillColor: '#f8fafc',
            fillOpacity: 1,
          }}
        >
          <Popup>
            <div className="space-y-1">
              <div className="text-sm font-semibold">{station.name}</div>
              <div className="text-xs text-muted-foreground">{station.code}</div>
              <div className="text-xs text-muted-foreground">
                {station.city || station.province || 'Unknown location'}
              </div>
            </div>
          </Popup>
        </CircleMarker>
      ))}

      {trainEntries.map(({ trajectory, position }) => {
        const isSelected = selectedTrainId === position.train_id;
        return (
          <CircleMarker
            key={`train-${position.train_id}`}
            center={[
              position.location.coordinates[1],
              position.location.coordinates[0],
            ]}
            radius={isSelected ? 9 : 6}
            pathOptions={{
              color: isSelected ? '#111827' : '#ffffff',
              weight: isSelected ? 3 : 2,
              fillColor: trainMarkerColor(position.delay_minutes),
              fillOpacity: 0.95,
            }}
            eventHandlers={{
              click: () => onTrainSelect(isSelected ? null : position.train_id),
            }}
          >
            <Popup>
              <div className="min-w-[260px] space-y-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-base font-semibold">
                      Train {position.train_number}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {getTrainTypeName(position.train_type)}
                    </div>
                  </div>
                  <Badge variant={position.delay_minutes > 0 ? 'warning' : 'success'}>
                    {formatDelay(position.delay_minutes)}
                  </Badge>
                </div>
                <dl className="grid grid-cols-2 gap-x-3 gap-y-2 text-xs">
                  <div>
                    <dt className="text-muted-foreground">Status</dt>
                    <dd className="font-medium">{position.status}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Speed</dt>
                    <dd className="font-medium">{formatSpeed(position.speed)}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Prev</dt>
                    <dd className="font-medium">{position.prev_station || '—'}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Next</dt>
                    <dd className="font-medium">{position.next_station || '—'}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Edge</dt>
                    <dd className="font-medium">{position.current_edge_id ?? '—'}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Route progress</dt>
                    <dd className="font-medium">
                      {typeof position.route_progress === 'number'
                        ? `${(position.route_progress * 100).toFixed(1)}%`
                        : '—'}
                    </dd>
                  </div>
                </dl>
                <div className="rounded-md bg-slate-950 p-2 text-[11px] text-slate-100">
                  <div>Graph: {trajectory.properties.graph}</div>
                  <div>Topology: {trajectory.properties.topology_version || '—'}</div>
                  <div>Samples: {trajectory.properties.time_intervals.length}</div>
                </div>
              </div>
            </Popup>
          </CircleMarker>
        );
      })}
    </MapContainer>
  );
}
