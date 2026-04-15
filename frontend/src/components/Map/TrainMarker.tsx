/**
 * Train marker component for the map with smooth position animation.
 *
 * Best practices from geops/mobility-toolbox-js:
 * - Delay color coding (realtimeDelayStyle / realtimeByDelayStyle pattern)
 * - Selected train highlighting
 * - Click to select/deselect
 */

'use client';

import { useEffect, useMemo, useRef, useCallback, useState } from 'react';
import { Marker, Popup } from 'react-leaflet';
import L from 'leaflet';
import { Clock3, Gauge, MapPin, Route } from 'lucide-react';
import { useMap } from 'react-leaflet';

import type { TrainPositionUpdate, TrainTrajectory } from '@/types';
import {
  getVehiclePosition,
  getVehicleTrajectoryState,
} from '@/lib/trajectory-interpolation';
import { buildConsistScreenPoints } from '@/lib/train-consist';
import {
  formatSpeed,
  formatDelay,
  getTrainTypeName,
} from '@/lib/utils';
import { Badge } from '@/components/ui';

// Animation duration should match the WebSocket update interval (2s)
const ANIM_DURATION_MS = 1900;
const TRAIN_CAR_COUNT = 10;
const DETAIL_LOCOMOTIVE_WIDTH = 30;
const DETAIL_LOCOMOTIVE_HEIGHT = 16;
const DETAIL_LOCOMOTIVE_WIDTH_SELECTED = 34;
const DETAIL_LOCOMOTIVE_HEIGHT_SELECTED = 18;
const DETAIL_WAGON_WIDTH = 16;
const DETAIL_WAGON_HEIGHT = 9;
const DETAIL_LEAD_SPACING_PX = 22;
const DETAIL_CAR_SPACING_PX = 15;
const FALLBACK_CAR_SPACING_PX = DETAIL_CAR_SPACING_PX;
const DISPLAY_ROTATION_OFFSET_DEG = -90;

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

interface WagonOffset {
  x: number;
  y: number;
  rotation: number;
}

function buildWagonOffsetsFromTrajectory(
  map: L.Map,
  trajectory: TrainTrajectory,
  nowMs: number,
  leadSpacingPx: number,
  carSpacingPx: number,
): WagonOffset[] {
  const locomotive = getVehicleTrajectoryState(nowMs, trajectory);
  if (!locomotive) return [];
  const polyline = (trajectory.geometry.coordinates as [number, number][])
    .map(([lon, lat]) => map.latLngToContainerPoint([lat, lon]))
    .map((point) => ({ x: point.x, y: point.y }));
  const distancesBehindHead = Array.from({ length: TRAIN_CAR_COUNT }, (_, index) =>
    leadSpacingPx + index * carSpacingPx,
  );
  const anchor = map.latLngToContainerPoint([locomotive.lat, locomotive.lon]);

  return buildConsistScreenPoints(
    polyline,
    locomotive.geomFraction,
    locomotive.rotation,
    distancesBehindHead,
  ).map((point) => ({
    x: +(point.x - anchor.x).toFixed(1),
    y: +(point.y - anchor.y).toFixed(1),
    rotation: point.rotation,
  }));
}

function buildLinearWagonOffsets(
  heading: number | null | undefined,
  leadSpacingPx: number,
  carSpacingPx: number,
): WagonOffset[] {
  const radians = (((heading ?? 0) - 90) * Math.PI) / 180;
  const offsets: WagonOffset[] = [];

  for (let index = 0; index < TRAIN_CAR_COUNT; index += 1) {
    const distance = leadSpacingPx + index * carSpacingPx;
    offsets.push({
      x: Math.cos(radians + Math.PI) * distance,
      y: Math.sin(radians + Math.PI) * distance,
      rotation: heading ?? 0,
    });
  }

  return offsets;
}

export default function TrainMarker({ position, trajectory, isSelected, onSelect }: TrainMarkerProps) {
  const map = useMap();
  const markerRef = useRef<L.Marker>(null);
  // Current displayed position (lat, lon) — updated by rAF, not React state
  const displayPosRef = useRef<[number, number]>([
    position.location.coordinates[1],
    position.location.coordinates[0],
  ]);
  const animRef = useRef<number>(0);
  const [zoom, setZoom] = useState(() => map.getZoom());
  const [wagonOffsets, setWagonOffsets] = useState<WagonOffset[]>([]);

  const closePopupIfTouchingViewport = useCallback(() => {
    if (!isSelected) return;

    const popup = markerRef.current?.getPopup();
    const popupElement = popup?.getElement();
    if (!popup || !popupElement || !markerRef.current?.isPopupOpen()) return;

    const mapRect = map.getContainer().getBoundingClientRect();
    const popupRect = popupElement.getBoundingClientRect();

    const touchesViewport = (
      popupRect.left <= mapRect.left ||
      popupRect.right >= mapRect.right ||
      popupRect.top <= mapRect.top ||
      popupRect.bottom >= mapRect.bottom
    );

    if (touchesViewport) {
      markerRef.current?.closePopup();
      onSelect?.(null);
    }
  }, [isSelected, map, onSelect]);

  useEffect(() => {
    const handleZoom = () => setZoom(map.getZoom());
    map.on('zoomend', handleZoom);
    return () => {
      map.off('zoomend', handleZoom);
    };
  }, [map]);

  // Smoothly animate marker from current displayed position to new target via rAF + setLatLng.
  useEffect(() => {
    if (trajectory) {
      cancelAnimationFrame(animRef.current);

      const step = () => {
        const nowMs = Date.now();
        const vehiclePosition = getVehiclePosition(nowMs, trajectory);
        if (vehiclePosition) {
          const nextPos: [number, number] = [vehiclePosition.lat, vehiclePosition.lon];
          displayPosRef.current = nextPos;
          markerRef.current?.setLatLng(nextPos);
          closePopupIfTouchingViewport();
          if (zoom >= 12) {
            setWagonOffsets(buildWagonOffsetsFromTrajectory(
              map,
              trajectory,
              nowMs,
              DETAIL_LEAD_SPACING_PX,
              DETAIL_CAR_SPACING_PX,
            ));
          } else {
            setWagonOffsets([]);
          }
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
      closePopupIfTouchingViewport();
      if (zoom >= 12) {
        setWagonOffsets(buildLinearWagonOffsets(
          position.heading,
          DETAIL_LEAD_SPACING_PX,
          FALLBACK_CAR_SPACING_PX,
        ));
      } else {
        setWagonOffsets([]);
      }
      if (t < 1) {
        animRef.current = requestAnimationFrame(step);
      }
    }

    animRef.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(animRef.current);
  }, [
    map,
    position.location.coordinates[0],
    position.location.coordinates[1],
    position.heading,
    trajectory,
    zoom,
    closePopupIfTouchingViewport,
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
      const timer = setTimeout(() => {
        markerRef.current?.openPopup();
        requestAnimationFrame(closePopupIfTouchingViewport);
      }, 80);
      return () => clearTimeout(timer);
    }
    markerRef.current?.closePopup();
    return undefined;
  }, [
    isSelected,
    zoom,
    position.train_id,
    position.location.coordinates[0],
    position.location.coordinates[1],
    closePopupIfTouchingViewport,
  ]);

  useEffect(() => {
    if (!isSelected) return undefined;

    const handleViewportChange = () => {
      requestAnimationFrame(closePopupIfTouchingViewport);
    };

    map.on('move zoom resize', handleViewportChange);
    return () => {
      map.off('move zoom resize', handleViewportChange);
    };
  }, [isSelected, map, closePopupIfTouchingViewport]);

  // Create custom icon with delay color coding (pattern from mobility-toolbox-js realtimeDelayStyle)
  const icon = useMemo(() => {
    const baseColor = position.train_type === 'special_express'
      ? '#E53935'
      : position.train_type === 'rapid'
      ? '#1E88E5'
      : '#43A047';

    const delayColor = getDelayColor(position.delay_minutes);
    const ringSize = getDelayRingSize(position.delay_minutes);
    const detailedComposition = zoom >= 12;
    const locomotiveWidth = detailedComposition ? (isSelected ? DETAIL_LOCOMOTIVE_WIDTH_SELECTED : DETAIL_LOCOMOTIVE_WIDTH) : (isSelected ? 24 : 20);
    const locomotiveHeight = detailedComposition ? (isSelected ? DETAIL_LOCOMOTIVE_HEIGHT_SELECTED : DETAIL_LOCOMOTIVE_HEIGHT) : (isSelected ? 15 : 13);
    const wagonWidth = detailedComposition ? DETAIL_WAGON_WIDTH : 0;
    const wagonHeight = detailedComposition ? DETAIL_WAGON_HEIGHT : 0;
    const iconWidth = detailedComposition ? 200 : locomotiveWidth + 24;
    const iconHeight = detailedComposition ? 200 : Math.max(locomotiveHeight + 22, 34);
    const centerX = iconWidth / 2;
    const centerY = iconHeight / 2;
    const halo = isSelected
      ? '0 0 0 3px rgba(250,204,21,0.9), 0 14px 28px rgba(15,23,42,0.28)'
      : ringSize > 0
        ? `0 0 0 ${ringSize}px ${delayColor}, 0 10px 20px rgba(15,23,42,0.2)`
        : '0 10px 20px rgba(15,23,42,0.18)';

    const wagons = detailedComposition
      ? wagonOffsets
          .map((offset, index) => {
            const alpha = Math.max(0.42, 0.95 - index * 0.045);
            return `<span style="position:absolute;left:${centerX + offset.x - wagonWidth / 2}px;top:${centerY + offset.y - wagonHeight / 2}px;width:${wagonWidth}px;height:${wagonHeight}px;border-radius:4px;background:${baseColor};opacity:${alpha};border:1px solid rgba(255,255,255,0.72);box-shadow:0 4px 10px rgba(15,23,42,0.18);transform:rotate(${offset.rotation + DISPLAY_ROTATION_OFFSET_DEG}deg);transform-origin:center center;"></span>`;
          })
          .join('')
      : '';

    const delayBadge = position.delay_minutes > 0
      ? `<span style="position:absolute;left:${centerX + 12}px;top:${centerY - 30}px;background:${delayColor};color:#fff;font-size:9px;padding:2px 5px;border-radius:999px;font-weight:700;white-space:nowrap;box-shadow:0 6px 16px rgba(15,23,42,0.2)">+${position.delay_minutes}</span>`
      : '';

    const iconHtml = `
      <div style="position:relative;width:${iconWidth}px;height:${iconHeight}px;display:flex;align-items:center;justify-content:center;">
        ${wagons}
        <div
          style="position:absolute;left:${centerX - locomotiveWidth / 2}px;top:${centerY - locomotiveHeight / 2}px;transform:rotate(${(position.heading ?? 0) + DISPLAY_ROTATION_OFFSET_DEG}deg);transform-origin:center center;filter:drop-shadow(0 6px 14px rgba(15,23,42,0.18));"
        >
          <span
            style="position:relative;width:${locomotiveWidth}px;height:${locomotiveHeight}px;border-radius:999px;background:${baseColor};display:flex;align-items:center;justify-content:flex-end;padding-right:5px;box-shadow:${halo};border:1px solid rgba(255,255,255,0.8);"
          >
            <span style="position:absolute;left:5px;top:3px;width:${Math.max(locomotiveWidth - 16, 8)}px;height:5px;border-radius:999px;background:rgba(255,255,255,0.55);"></span>
            <span style="width:7px;height:7px;border-radius:999px;background:#fff7cc;box-shadow:0 0 10px rgba(255,244,180,0.9);"></span>
          </span>
        </div>
        ${delayBadge}
      </div>
    `;

    return L.divIcon({
      html: iconHtml,
      className: 'train-marker',
      iconSize: [iconWidth, iconHeight],
      iconAnchor: [centerX, centerY],
      popupAnchor: [0, -18],
    });
  }, [position.train_type, position.heading, position.delay_minutes, isSelected, wagonOffsets, zoom]);

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
      <Popup autoPan={false} closeButton={false}>
        <div className="min-w-[240px] space-y-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-lg font-semibold tracking-tight">Train {position.train_number}</h3>
              <p className="text-sm text-muted-foreground">
                {getTrainTypeName(position.train_type)}
              </p>
            </div>
            <Badge variant={statusBadgeVariant} className="capitalize">
              {position.status.replace('_', ' ')}
            </Badge>
          </div>

          <div className="grid grid-cols-3 gap-2 rounded-2xl bg-zinc-50 p-2.5 text-xs">
            <div>
              <div className="flex items-center gap-1 text-zinc-500">
                <Gauge className="h-3.5 w-3.5" />
                Speed
              </div>
              <p className="mt-1 font-semibold text-zinc-900">{formatSpeed(position.speed)}</p>
            </div>
            <div>
              <div className="flex items-center gap-1 text-zinc-500">
                <Clock3 className="h-3.5 w-3.5" />
                Delay
              </div>
              <p className="mt-1 font-semibold" style={{ color: getDelayColor(position.delay_minutes) }}>
                {formatDelay(position.delay_minutes)}
              </p>
            </div>
            <div>
              <div className="flex items-center gap-1 text-zinc-500">
                <Route className="h-3.5 w-3.5" />
                Route
              </div>
              <p className="mt-1 font-semibold text-zinc-900">
                {position.route_progress !== undefined ? `${Math.round(position.route_progress * 100)}%` : '—'}
              </p>
            </div>
          </div>

          <div className="space-y-2 text-sm">
            {position.prev_station && (
              <div className="flex items-start gap-2">
                <MapPin className="mt-0.5 h-4 w-4 text-zinc-400" />
                <div>
                  <p className="text-xs uppercase tracking-wide text-zinc-500">Previous</p>
                  <p className="font-medium text-zinc-900">{position.prev_station}</p>
                </div>
              </div>
            )}

            {position.next_station && (
              <div className="flex items-start gap-2">
                <MapPin className="mt-0.5 h-4 w-4 text-zinc-400" />
                <div>
                  <div className="flex items-center gap-2">
                    <p className="text-xs uppercase tracking-wide text-zinc-500">Next</p>
                    {position.eta_next_station && (
                      <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] font-semibold text-zinc-700">
                        {position.eta_next_station}
                      </span>
                    )}
                  </div>
                  <p className="font-medium text-zinc-900">{position.next_station}</p>
                </div>
              </div>
            )}
          </div>

          {position.progress !== undefined && (
            <div className="pt-1">
              <div className="mb-1 flex justify-between text-xs text-zinc-500">
                <span>Progress to next station</span>
                <span>{position.progress}%</span>
              </div>
              <div className="h-2 rounded-full bg-zinc-100 overflow-hidden">
                <div
                  className="h-full rounded-full transition-all"
                  style={{
                    width: `${position.progress}%`,
                    background: `linear-gradient(90deg, ${getDelayColor(position.delay_minutes)}, ${position.train_type === 'rapid' ? '#60a5fa' : '#34d399'})`,
                  }}
                />
              </div>
            </div>
          )}
        </div>
      </Popup>
    </Marker>
  );
}
