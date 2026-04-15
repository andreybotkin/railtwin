/**
 * Dedicated debug map for inspecting a single train's trajectory and schedule points.
 */

'use client';

import { useEffect } from 'react';
import { CircleMarker, MapContainer, Polyline, Popup, TileLayer, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

import type { Route, Station, TrainTrajectory } from '@/types';

const THAILAND_CENTER: [number, number] = [15.87, 100.9925];
const INITIAL_ZOOM = 6;

delete (L.Icon.Default.prototype as { _getIconUrl?: unknown })._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
});

export interface TrajectoryDebugPoint {
  index: number;
  timestampMs: number;
  isoTime: string;
  lon: number;
  lat: number;
  rotation: number;
  source: 'coordinate_timestamps' | 'time_intervals';
  routeFraction: number | null;
}

export interface ScheduleMapPoint {
  scheduleId: number;
  sequence: number;
  stationId: number | null;
  stationName: string;
  stationCode: string | null;
  arrivalTime: string | null;
  departureTime: string | null;
  dayOfWeek: number[] | null;
  routeProgress: number | null;
  lon: number;
  lat: number;
}

interface TrainPointsDebugMapProps {
  trajectory: TrainTrajectory | null;
  trajectoryPoints: TrajectoryDebugPoint[];
  schedulePoints: ScheduleMapPoint[];
  route: Route | null;
  routeStations: Station[];
}

function FitToData({
  trajectory,
  trajectoryPoints,
  schedulePoints,
  route,
  routeStations,
}: TrainPointsDebugMapProps) {
  const map = useMap();

  useEffect(() => {
    const bounds = new L.LatLngBounds([]);

    trajectory?.geometry.coordinates.forEach(([lon, lat]) => {
      bounds.extend([lat, lon]);
    });

    route?.line_geometry?.coordinates.forEach(([lon, lat]) => {
      bounds.extend([lat, lon]);
    });

    trajectoryPoints.forEach((point) => {
      bounds.extend([point.lat, point.lon]);
    });

    schedulePoints.forEach((point) => {
      bounds.extend([point.lat, point.lon]);
    });

    routeStations.forEach((station) => {
      bounds.extend([station.location.coordinates[1], station.location.coordinates[0]]);
    });

    if (bounds.isValid()) {
      map.fitBounds(bounds.pad(0.12), { animate: false, maxZoom: 12 });
    }
  }, [map, trajectory, trajectoryPoints, schedulePoints, route, routeStations]);

  return null;
}

export default function TrainPointsDebugMap({
  trajectory,
  trajectoryPoints,
  schedulePoints,
  route,
  routeStations,
}: TrainPointsDebugMapProps) {
  const trajectoryLine =
    trajectory?.geometry.coordinates.map(([lon, lat]) => [lat, lon] as [number, number]) ?? [];
  const routeLine =
    route?.line_geometry?.coordinates.map(([lon, lat]) => [lat, lon] as [number, number]) ?? [];

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

      <FitToData
        trajectory={trajectory}
        trajectoryPoints={trajectoryPoints}
        schedulePoints={schedulePoints}
        route={route}
        routeStations={routeStations}
      />

      {routeLine.length >= 2 && (
        <Polyline
          positions={routeLine}
          pathOptions={{
            color: route?.color || '#0f172a',
            weight: 6,
            opacity: 0.25,
            dashArray: '10 8',
          }}
        />
      )}

      {trajectoryLine.length >= 2 && (
        <Polyline
          positions={trajectoryLine}
          pathOptions={{
            color: trajectory?.properties.line.stroke || trajectory?.properties.line.color || '#b45309',
            weight: 4,
            opacity: 0.8,
          }}
        />
      )}

      {routeStations.map((station) => (
        <CircleMarker
          key={`route-station-${station.id}`}
          center={[station.location.coordinates[1], station.location.coordinates[0]]}
          radius={4}
          pathOptions={{
            color: '#334155',
            weight: 1,
            fillColor: '#f8fafc',
            fillOpacity: 0.9,
          }}
        >
          <Popup>
            <div className="space-y-1 text-sm">
              <div className="font-semibold">{station.name}</div>
              <div>Code: {station.code}</div>
              <div>Reference route station</div>
            </div>
          </Popup>
        </CircleMarker>
      ))}

      {trajectoryPoints.map((point) => (
        <CircleMarker
          key={`trajectory-point-${point.index}-${point.timestampMs}`}
          center={[point.lat, point.lon]}
          radius={point.index === 0 ? 6 : 4}
          pathOptions={{
            color: '#7c2d12',
            weight: 1,
            fillColor: '#fb923c',
            fillOpacity: 0.85,
          }}
        >
          <Popup>
            <div className="space-y-1 text-sm">
              <div className="font-semibold">Trajectory point #{point.index + 1}</div>
              <div>Time: {point.isoTime}</div>
              <div>Coordinates: {point.lat.toFixed(6)}, {point.lon.toFixed(6)}</div>
              <div>Rotation: {point.rotation.toFixed(1)}°</div>
              <div>Source: {point.source}</div>
              <div>
                Route fraction:{' '}
                {typeof point.routeFraction === 'number' ? `${(point.routeFraction * 100).toFixed(2)}%` : '—'}
              </div>
            </div>
          </Popup>
        </CircleMarker>
      ))}

      {schedulePoints.map((point) => (
        <CircleMarker
          key={`schedule-point-${point.scheduleId}`}
          center={[point.lat, point.lon]}
          radius={6}
          pathOptions={{
            color: '#0f172a',
            weight: 2,
            fillColor: '#38bdf8',
            fillOpacity: 0.9,
          }}
        >
          <Popup>
            <div className="space-y-1 text-sm">
              <div className="font-semibold">
                Stop {point.sequence}: {point.stationName}
              </div>
              <div>Code: {point.stationCode || '—'}</div>
              <div>Arrival: {point.arrivalTime || '—'}</div>
              <div>Departure: {point.departureTime || '—'}</div>
              <div>
                Route progress:{' '}
                {typeof point.routeProgress === 'number' ? `${(point.routeProgress * 100).toFixed(1)}%` : '—'}
              </div>
            </div>
          </Popup>
        </CircleMarker>
      ))}
    </MapContainer>
  );
}
