/**
 * Map content component with Leaflet integration.
 */

'use client';

import { useEffect, useMemo, useRef } from 'react';
import {
  MapContainer,
  TileLayer,
  Polyline,
  Marker,
  Popup,
  useMap,
} from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

import { useRoutes, useStations, useTrainPositions, useInitialPositions } from '@/lib/hooks';
import { getRouteColor, formatSpeed, formatDelay, getTrainTypeName } from '@/lib/utils';
import { cn } from '@/lib/utils';
import TrainMarker from './TrainMarker';
import StationMarker from './StationMarker';

// Fix Leaflet default icon issue in Next.js
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
});

// Thailand center coordinates
const THAILAND_CENTER: [number, number] = [15.87, 100.9925];
const INITIAL_ZOOM = 6;

interface MapContentProps {
  className?: string;
}

// Component to handle map events
function MapController() {
  const map = useMap();
  
  useEffect(() => {
    // Invalidate size after mount to fix container issues
    setTimeout(() => {
      map.invalidateSize();
    }, 100);
  }, [map]);

  return null;
}

export default function MapContent({ className }: MapContentProps) {
  const { data: routesData } = useRoutes();
  const { data: stationsData } = useStations();
  const { positions: wsPositions, isConnected } = useTrainPositions();
  const { data: apiPositions } = useInitialPositions();

  // Use WebSocket positions if connected, otherwise fall back to API
  const trainPositions = useMemo(() => {
    if (isConnected && wsPositions.length > 0) {
      return wsPositions;
    }
    return apiPositions || [];
  }, [isConnected, wsPositions, apiPositions]);

  const routes = routesData?.items || [];
  const stations = stationsData?.items || [];

  return (
    <div className={cn('h-full w-full', className)}>
      <MapContainer
        center={THAILAND_CENTER}
        zoom={INITIAL_ZOOM}
        className="h-full w-full"
        attributionControl={false}
        zoomControl={true}
        scrollWheelZoom={true}
      >
        <MapController />
        
        {/* Base map tile layer */}
        <TileLayer
          attribution=""
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {/* Railway routes */}
        {routes.map((route) => {
          if (!route.line_geometry?.coordinates) return null;
          
          // Convert [lon, lat] to [lat, lon] for Leaflet
          const positions = route.line_geometry.coordinates.map(
            (coord) => [coord[1], coord[0]] as [number, number]
          );

          return (
            <Polyline
              key={route.id}
              positions={positions}
              color={route.color || getRouteColor(route.route_type)}
              weight={4}
              opacity={0.8}
            >
              <Popup>
                <div className="min-w-[150px]">
                  <h3 className="font-semibold">{route.name}</h3>
                  {route.name_th && (
                    <p className="text-sm text-muted-foreground">{route.name_th}</p>
                  )}
                  <p className="text-sm">
                    Distance: {route.distance_km} km
                  </p>
                </div>
              </Popup>
            </Polyline>
          );
        })}

        {/* Stations */}
        {stations.map((station) => (
          <StationMarker key={station.id} station={station} />
        ))}

        {/* Train positions */}
        {trainPositions.map((position) => (
          <TrainMarker key={position.train_id} position={position} />
        ))}
      </MapContainer>
    </div>
  );
}
