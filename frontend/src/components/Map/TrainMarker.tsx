/**
 * Train marker component for the map with smooth position animation.
 *
 * Best practices from geops/mobility-toolbox-js:
 * - Delay color coding (realtimeDelayStyle / realtimeByDelayStyle pattern)
 * - Selected train highlighting
 * - Click to select/deselect
 */

'use client';

import { useEffect, useMemo, useRef, useCallback } from 'react';
import { Marker, Popup } from 'react-leaflet';
import L from 'leaflet';

import type { TrainPositionUpdate, TrainTrajectory } from '@/types';
import { getVehiclePosition } from '@/lib/trajectory-interpolation';
import {
  formatSpeed,
  formatDelay,
  getTrainTypeName,
} from '@/lib/utils';
import { Badge } from '@/components/ui';

// Animation duration should match the WebSocket update interval (2s)
const ANIM_DURATION_MS = 1900;

/**
 * Get delay color following mobility-toolbox-js realtimeByDelayStyle pattern:
 * green = on time or early, yellow = 1-5 min late, orange = 5-15 min, red = 15+ min.
 */
function getDelayColor(delayMinutes: number): string {
  if (delayMinutes <= 0) return '#43A047'; // green — on time
  if (delayMinutes <= 5) return '#FDD835'; // yellow — slight delay
  if (delayMinutes <= 15) return '#FB8C00'; // orange — moderate delay
  return '#E53935'; // red — severe delay
}

/**
 * Get delay border ring size for visual emphasis.
 */
function getDelayRingSize(delayMinutes: number): number {
  if (delayMinutes <= 0) return 0;
  if (delayMinutes <= 5) return 2;
  if (delayMinutes <= 15) return 3;
  return 4;
}

interface TrainMarkerProps {
  position: TrainPositionUpdate;
  trajectory?: TrainTrajectory;
  isSelected?: boolean;
  onSelect?: (id: number | null) => void;
}

export default function TrainMarker({ position, trajectory, isSelected, onSelect }: TrainMarkerProps) {
  const markerRef = useRef<L.Marker>(null);
  // Current displayed position (lat, lon) — updated by rAF, not React state
  const displayPosRef = useRef<[number, number]>([
    position.location.coordinates[1],
    position.location.coordinates[0],
  ]);
  const animRef = useRef<number>(0);

  // Smoothly animate marker from current displayed position to new target via rAF + setLatLng.
  useEffect(() => {
    if (trajectory) {
      cancelAnimationFrame(animRef.current);

      const step = () => {
        const vehiclePosition = getVehiclePosition(Date.now(), trajectory);
        if (vehiclePosition) {
          const nextPos: [number, number] = [vehiclePosition.lat, vehiclePosition.lon];
          displayPosRef.current = nextPos;
          markerRef.current?.setLatLng(nextPos);
        }
        animRef.current = requestAnimationFrame(step);
      };

      animRef.current = requestAnimationFrame(step);
      return () => cancelAnimationFrame(animRef.current);
    }

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
  }, [
    position.location.coordinates[0],
    position.location.coordinates[1],
    trajectory,
  ]);

  const handleClick = useCallback(() => {
    onSelect?.(isSelected ? null : position.train_id);
  }, [onSelect, isSelected, position.train_id]);

  // Auto-open the Leaflet popup whenever this marker becomes the selected train.
  // This ensures clicking a canvas train (which becomes a DOM marker) immediately
  // shows info without requiring a second click.
  useEffect(() => {
    if (isSelected && markerRef.current) {
      // Small delay so the marker is fully mounted in the DOM first.
      const timer = setTimeout(() => markerRef.current?.openPopup(), 80);
      return () => clearTimeout(timer);
    }
    return undefined;
  }, [isSelected]);

  // Create custom icon with delay color coding (pattern from mobility-toolbox-js realtimeDelayStyle)
  const icon = useMemo(() => {
    const baseColor = position.train_type === 'special_express'
      ? '#E53935'
      : position.train_type === 'rapid'
      ? '#1E88E5'
      : '#43A047';

    const delayColor = getDelayColor(position.delay_minutes);
    const ringSize = getDelayRingSize(position.delay_minutes);
    const selectedBorder = isSelected ? 'border: 3px solid #FFD600;' : '';
    const delayBorder = ringSize > 0 && !isSelected ? `box-shadow: 0 0 0 ${ringSize}px ${delayColor};` : '';
    const size = isSelected ? 36 : 28;

    const delayBadge = position.delay_minutes > 0
      ? `<span style="position:absolute;top:-8px;right:-12px;background:${delayColor};color:#fff;font-size:9px;padding:1px 3px;border-radius:6px;font-weight:bold;white-space:nowrap">+${position.delay_minutes}</span>`
      : '';

    const iconHtml = `
      <div style="position:relative">
        <div class="train-icon ${position.status === 'moving' ? 'moving' : ''}"
             style="background-color: ${baseColor}; transform: rotate(${position.heading || 0}deg); ${selectedBorder} ${delayBorder} width:${size}px;height:${size}px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:${isSelected ? 18 : 14}px;cursor:pointer">
          🚂
        </div>
        ${delayBadge}
      </div>
    `;

    return L.divIcon({
      html: iconHtml,
      className: 'train-marker',
      iconSize: [size + 8, size + 8],
      iconAnchor: [(size + 8) / 2, (size + 8) / 2],
      popupAnchor: [0, -(size / 2)],
    });
  }, [position.train_type, position.status, position.heading, position.delay_minutes, isSelected]);

  const statusBadgeVariant =
    position.status === 'moving' ? 'success' :
    position.status === 'delayed' ? 'destructive' :
    position.status === 'at_station' ? 'info' : 'secondary';

  return (
    <Marker
      ref={markerRef}
      position={displayPosRef.current}
      icon={icon}
      eventHandlers={{
        click: (e) => {
          // Stop the click from bubbling to the map so the canvas click
          // handler does NOT re-fire and accidentally switch selection.
          L.DomEvent.stopPropagation(e.originalEvent);
          handleClick();
        },
      }}
    >
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
                <span
                  className="ml-1 font-medium"
                  style={{ color: getDelayColor(position.delay_minutes) }}
                >
                  {formatDelay(position.delay_minutes)}
                </span>
              </div>
            </div>

            {position.next_station && (
              <div className="pt-2 border-t">
                <div className="flex justify-between items-baseline">
                  <span className="text-muted-foreground">Next station:</span>
                  {position.eta_next_station && (
                    <span className="text-xs font-semibold tabular-nums">
                      {position.eta_next_station}
                    </span>
                  )}
                </div>
                <p className="font-medium">{position.next_station}</p>
              </div>
            )}

            {position.progress !== undefined && (
              <div className="pt-1">
                <div className="flex justify-between text-xs">
                  <span>Progress to next station</span>
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
