/**
 * Train marker component for the map with smooth position animation.
 */

'use client';

import { useEffect, useMemo, useRef } from 'react';
import { Marker, Popup } from 'react-leaflet';
import L from 'leaflet';

import type { TrainPositionUpdate } from '@/types';
import {
  formatSpeed,
  formatDelay,
  getTrainTypeName,
} from '@/lib/utils';
import { Badge } from '@/components/ui';

// Animation duration should match the WebSocket update interval (2s)
const ANIM_DURATION_MS = 1900;

interface TrainMarkerProps {
  position: TrainPositionUpdate;
}

export default function TrainMarker({ position }: TrainMarkerProps) {
  const markerRef = useRef<L.Marker>(null);
  // Current displayed position (lat, lon) — updated by rAF, not React state
  const displayPosRef = useRef<[number, number]>([
    position.location.coordinates[1],
    position.location.coordinates[0],
  ]);
  const animRef = useRef<number>(0);

  // Smoothly animate marker from current displayed position to new target via rAF + setLatLng.
  // Using setLatLng (not CSS transforms) keeps Leaflet's internal state correct so that
  // map panning, popups, and hit-testing always work at the right coordinates.
  useEffect(() => {
    const targetLat = position.location.coordinates[1];
    const targetLon = position.location.coordinates[0];
    const [startLat, startLon] = displayPosRef.current;
    const startTime = performance.now();

    cancelAnimationFrame(animRef.current);

    function step(now: number) {
      const t = Math.min((now - startTime) / ANIM_DURATION_MS, 1);
      const lat = startLat + (targetLat - startLat) * t;
      const lon = startLon + (targetLon - startLon) * t;
      displayPosRef.current = [lat, lon];
      markerRef.current?.setLatLng([lat, lon]);
      if (t < 1) {
        animRef.current = requestAnimationFrame(step);
      }
    }

    animRef.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(animRef.current);
  }, [position.location.coordinates[0], position.location.coordinates[1]]);

  // Create custom icon (only re-created when type/status/heading changes)
  const icon = useMemo(() => {
    const color = position.train_type === 'special_express'
      ? '#E53935'
      : position.train_type === 'rapid'
      ? '#1E88E5'
      : '#43A047';

    const iconHtml = `
      <div class="train-icon ${position.status === 'moving' ? 'moving' : ''}"
           style="background-color: ${color}; transform: rotate(${position.heading || 0}deg)">
        🚂
      </div>
    `;

    return L.divIcon({
      html: iconHtml,
      className: 'train-marker',
      iconSize: [28, 28],
      iconAnchor: [14, 14],
      popupAnchor: [0, -14],
    });
  }, [position.train_type, position.status, position.heading]);

  const statusBadgeVariant =
    position.status === 'moving' ? 'success' :
    position.status === 'delayed' ? 'destructive' :
    position.status === 'at_station' ? 'info' : 'secondary';

  return (
    // position is set once on mount; all updates go through setLatLng in the effect above
    <Marker ref={markerRef} position={displayPosRef.current} icon={icon}>
      <Popup>
        <div className="min-w-[200px] space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-bold">Train {position.train_number}</h3>
            <Badge variant={statusBadgeVariant} className="capitalize">
              {position.status.replace('_', ' ')}
            </Badge>
          </div>

          <div className="text-sm space-y-1">
            <p className="text-muted-foreground">
              {getTrainTypeName(position.train_type)}
            </p>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <span className="text-muted-foreground">Speed:</span>
                <span className="ml-1 font-medium">{formatSpeed(position.speed)}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Delay:</span>
                <span className={`ml-1 font-medium ${position.delay_minutes > 0 ? 'text-red-500' : 'text-green-500'}`}>
                  {formatDelay(position.delay_minutes)}
                </span>
              </div>
            </div>

            {position.next_station && (
              <div className="pt-2 border-t">
                <span className="text-muted-foreground">Next station:</span>
                <p className="font-medium">{position.next_station}</p>
              </div>
            )}

            {position.progress !== undefined && (
              <div className="pt-1">
                <div className="flex justify-between text-xs">
                  <span>Journey progress</span>
                  <span>{position.progress}%</span>
                </div>
                <div className="h-2 bg-muted rounded-full overflow-hidden mt-1">
                  <div
                    className="h-full bg-primary transition-all"
                    style={{ width: `${position.progress}%` }}
                  />
                </div>
              </div>
            )}
          </div>
        </div>
      </Popup>
    </Marker>
  );
}
