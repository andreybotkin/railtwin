'use client';

/**
 * Leaflet train marker with consist rendering.
 *
 * Rules:
 *  - Loco: fixed-size pill at ALL zoom levels; white dot (headlight) at the
 *    forward end — always points in the direction of travel.
 *  - Wagons: visible only at zoom ≥ 14 (≈ scale < 300 m). They are
 *    positioned in screen-pixel space every rAF tick so they stay strictly
 *    glued to the loco and snake along the rail geometry.
 *  - No popup on selection — info is shown in the side panel.
 */

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { Marker, useMap } from 'react-leaflet';
import L from 'leaflet';

import type { Trajectory } from '@/types';
import { getTrajectoryFrameAt } from '@/lib/trajectory-interpolation';
import { buildConsistScreenPoints } from '@/lib/train-consist';
import { getTrainTypeColor } from '@/lib/utils';

// ─── Constants ────────────────────────────────────────────────────────────────

/** CSS rotate() offset: pill faces east at 0°, so -90° aligns it with north. */
const ROT_OFFSET = -90;

// Loco pixel size — constant at every zoom level.
const LOCO_W = 30;
const LOCO_H = 16;
const LOCO_W_SEL = 34;
const LOCO_H_SEL = 18;

// Wagon pixel size.
const WAGON_W = 16;
const WAGON_H = 9;

// Spacing between consist bodies (pixels).
const LEAD_SPACING = 22; // loco tail → first wagon centre
const CAR_SPACING = 15; // wagon centre → next wagon centre

/**
 * DivIcon canvas size.
 * Max wagon distance = LEAD_SPACING + (MAX_CARS-1) * CAR_SPACING
 *                    = 22 + 9×15 = 157 px
 * Plus WAGON_W/2 = 8 px margin → need radius 165 px → SIZE = 360.
 */
const SIZE = 360;
const CENTER = 180;

/** Minimum zoom to render wagons (≈ scale ≤ 300 m in Thailand). */
const WAGONS_MIN_ZOOM = 14;

const MAX_CARS = 10;

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getDelayColor(delayMinutes: number): string {
  if (delayMinutes <= 0) return '#43A047';
  if (delayMinutes <= 5) return '#FDD835';
  if (delayMinutes <= 15) return '#FB8C00';
  return '#E53935';
}

function getViewportWidthMeters(map: L.Map): number {
  const bounds = map.getBounds();
  const centerLat = bounds.getCenter().lat;
  const west = bounds.getWest();
  const east = bounds.getEast();
  return L.latLng(centerLat, west).distanceTo(L.latLng(centerLat, east));
}

type WagonOffset = { x: number; y: number; rotation: number };

/**
 * Update loco rotation and wagon positions directly in the DOM.
 * Called every rAF tick and after icon regeneration (useLayoutEffect).
 */
function applyToDOM(
  el: HTMLElement,
  headingDeg: number,
  wagons: WagonOffset[],
  carCount: number
): void {
  const cssRot = headingDeg + ROT_OFFSET;

  const locoEl = el.querySelector('[data-loco]') as HTMLElement | null;
  if (locoEl) locoEl.style.transform = `rotate(${cssRot}deg)`;

  for (let i = 0; i < carCount; i++) {
    const wEl = el.querySelector(`[data-wagon="${i}"]`) as HTMLElement | null;
    if (!wEl) continue;
    const off = wagons[i];
    if (off) {
      wEl.style.left = `${CENTER + off.x - WAGON_W / 2}px`;
      wEl.style.top = `${CENTER + off.y - WAGON_H / 2}px`;
      wEl.style.transform = `rotate(${off.rotation + ROT_OFFSET}deg)`;
    }
  }
}

// ─── Icon builder ─────────────────────────────────────────────────────────────

interface IconParams {
  baseColor: string;
  delayColor: string;
  delayMinutes: number;
  isSelected: boolean;
  carCount: number;
  showWagons: boolean;
  showDelayBadge: boolean;
  scaleFactor: number;
}

function buildIcon({
  baseColor,
  delayColor,
  delayMinutes,
  isSelected,
  carCount,
  showWagons,
  showDelayBadge,
  scaleFactor,
}: IconParams): L.DivIcon {
  const locoW = (isSelected ? LOCO_W_SEL : LOCO_W) * scaleFactor;
  const locoH = (isSelected ? LOCO_H_SEL : LOCO_H) * scaleFactor;
  const headlightSize = Math.max(4, Math.round(7 * scaleFactor));

  const halo = isSelected
    ? '0 0 0 3px rgba(250,204,21,0.9), 0 14px 28px rgba(15,23,42,0.28)'
    : delayMinutes > 0
      ? `0 0 0 2px ${delayColor}, 0 10px 20px rgba(15,23,42,0.2)`
      : '0 10px 20px rgba(15,23,42,0.18)';

  // Wagon placeholder elements — positions written by applyToDOM every rAF.
  let wagonsHtml = '';
  if (showWagons) {
    for (let i = 0; i < carCount; i++) {
      const alpha = Math.max(0.42, 0.95 - i * 0.045).toFixed(2);
      wagonsHtml += `<span data-wagon="${i}" style="position:absolute;left:${CENTER - WAGON_W / 2}px;top:${CENTER - WAGON_H / 2}px;width:${WAGON_W}px;height:${WAGON_H}px;border-radius:4px;background:${baseColor};opacity:${alpha};border:1px solid rgba(255,255,255,0.72);box-shadow:0 4px 10px rgba(15,23,42,0.18);transform:rotate(0deg);transform-origin:center center;pointer-events:auto;"></span>`;
    }
  }

  // Delay badge above the loco.
  const delayBadge =
    showDelayBadge && delayMinutes !== 0
      ? `<span style="position:absolute;left:${CENTER + locoW / 2 + 2}px;top:${CENTER - locoH / 2 - 14}px;background:${delayColor};color:#fff;font-size:9px;padding:2px 5px;border-radius:999px;font-weight:700;white-space:nowrap;box-shadow:0 4px 12px rgba(15,23,42,0.2);pointer-events:none;">${delayMinutes > 0 ? '+' : ''}${delayMinutes}</span>`
      : '';

  const shineW = Math.max(locoW - 16, 8);
  const shine = `<span style="position:absolute;left:5px;top:3px;width:${shineW}px;height:5px;border-radius:999px;background:rgba(255,255,255,0.55);"></span>`;
  // Headlight at the right (flex-end) side = forward end after rotation.
  const headlight = `<span style="width:${headlightSize}px;height:${headlightSize}px;border-radius:999px;background:#fff7cc;box-shadow:0 0 10px rgba(255,244,180,0.9);flex-shrink:0;"></span>`;

  const locoHtml = `
    <div data-loco style="position:absolute;left:${CENTER - locoW / 2}px;top:${CENTER - locoH / 2}px;transform:rotate(0deg);transform-origin:center center;filter:drop-shadow(0 6px 14px rgba(15,23,42,0.18));pointer-events:auto;">
      <span style="position:relative;width:${locoW}px;height:${locoH}px;border-radius:999px;background:${baseColor};display:flex;align-items:center;justify-content:flex-end;padding-right:5px;box-shadow:${halo};border:1px solid rgba(255,255,255,0.8);pointer-events:auto;">
        ${shine}
        ${headlight}
      </span>
    </div>`;

  const html = `<div style="position:relative;width:${SIZE}px;height:${SIZE}px;pointer-events:none;">${wagonsHtml}${locoHtml}${delayBadge}</div>`;

  return L.divIcon({
    html,
    className: 'train-marker',
    iconSize: [SIZE, SIZE],
    iconAnchor: [CENTER, CENTER],
    popupAnchor: [0, -20],
  });
}

// ─── Component ────────────────────────────────────────────────────────────────

interface LeafletTrainMarkerProps {
  trajectory: Trajectory;
  isSelected: boolean;
  onSelect: (id: number | null) => void;
}

export default function LeafletTrainMarker({
  trajectory,
  isSelected,
  onSelect,
}: LeafletTrainMarkerProps) {
  const map = useMap();
  const markerRef = useRef<L.Marker>(null);
  const animRef = useRef<number>(0);
  const rotationRef = useRef<number>(0);
  const wagonOffsetsRef = useRef<WagonOffset[]>([]);

  const viewportWidthMeters = getViewportWidthMeters(map);
  const [zoom, setZoom] = useState(() => map.getZoom());
  const [scaleFactor, setScaleFactor] = useState(() =>
    viewportWidthMeters > 100_000 ? 1 / 2 : 1
  );
  const showWagons = zoom >= WAGONS_MIN_ZOOM;
  const showDelayBadge = viewportWidthMeters <= 100_000;

  const { train_id, meta, consist } = trajectory;
  const carCount = Math.min(consist.car_count, MAX_CARS);
  const delayMinutes = meta.delay_minutes;
  const trainType = meta.train_type;

  // Stable initial Leaflet mount position.
  const initPos = useMemo<[number, number]>(() => {
    const frame = getTrajectoryFrameAt(Date.now(), trajectory);
    if (frame) return [frame.lat, frame.lon];
    const f = trajectory.frames[0];
    return [f?.lat ?? 15.87, f?.lon ?? 100.99];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [train_id]);

  // Zoom and viewport listener — updates icon scale and wagon visibility.
  useEffect(() => {
    const handleUpdate = () => {
      const width = getViewportWidthMeters(map);
      setZoom(map.getZoom());
      setScaleFactor(width > 100_000 ? 1 / 2 : 1);
    };
    handleUpdate();
    map.on('zoomend', handleUpdate);
    map.on('moveend', handleUpdate);
    return () => {
      map.off('zoomend', handleUpdate);
      map.off('moveend', handleUpdate);
    };
  }, [map]);

  // Build icon — regenerated only when display params change.
  const icon = useMemo(
    () =>
      buildIcon({
        baseColor: getTrainTypeColor(trainType),
        delayColor: getDelayColor(delayMinutes),
        delayMinutes,
        isSelected,
        carCount,
        showWagons,
        showDelayBadge,
        scaleFactor,
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      trainType,
      delayMinutes,
      isSelected,
      carCount,
      showWagons,
      showDelayBadge,
      scaleFactor,
    ]
  );

  // After icon regeneration: reapply last-known rotation + wagon positions,
  // and neutralise the pointer-event area of the Leaflet outer element so that
  // only the actual loco/wagon visuals intercept clicks.
  useLayoutEffect(() => {
    const el = markerRef.current?.getElement();
    if (!el) return;
    // The Leaflet marker root covers 360×360 px; setting none here means only
    // children with pointer-events:auto (loco + wagons) are clickable, so the
    // empty surrounding area no longer steals clicks from nearby stations.
    el.style.pointerEvents = 'none';
    applyToDOM(el, rotationRef.current, wagonOffsetsRef.current, carCount);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [icon]);

  // rAF animation loop — moves loco and wagons along the rail polyline.
  // The locomotive head position and heading are both derived from the rail
  // geometry (route_coords + geomFraction) — the same way wagons are placed —
  // so the loco always snaps to the track and the headlight (white dot) always
  // points in the direction of travel.
  useEffect(() => {
    const step = () => {
      const frame = getTrajectoryFrameAt(Date.now(), trajectory);
      if (frame) {
        let locoRotation = frame.rotation;
        let wagonOffsets: WagonOffset[] = [];

        if (trajectory.route_coords.length >= 2) {
          // Project the route polyline to screen pixels.
          const polyline = (trajectory.route_coords as [number, number][]).map(
            ([lon, lat]) => {
              const pt = map.latLngToContainerPoint([lat, lon]);
              return { x: pt.x, y: pt.y };
            }
          );

          // Distance 0 = loco head; wagon distances trail behind the head.
          // For backward trains the sign is reversed so wagons go the right way.
          const sign = frame.travelForward ? 1 : -1;
          const distances = [
            0,
            ...(showWagons
              ? Array.from(
                  { length: carCount },
                  (_, i) => sign * (LEAD_SPACING + i * CAR_SPACING)
                )
              : []),
          ];

          const consistPoints = buildConsistScreenPoints(
            polyline,
            frame.geomFraction,
            frame.rotation,
            distances
          );

          const headPt = consistPoints[0];
          if (headPt) {
            // Snap loco to the polyline position.
            const headLatLng = map.containerPointToLatLng([headPt.x, headPt.y]);
            markerRef.current?.setLatLng(headLatLng);

            // Heading follows the polyline tangent; flip 180° for backward trains
            // so the white dot (headlight) always points in the travel direction.
            locoRotation = frame.travelForward
              ? headPt.rotation
              : (headPt.rotation + 180) % 360;

            if (showWagons) {
              wagonOffsets = consistPoints.slice(1).map((pt) => ({
                x: +(pt.x - headPt.x).toFixed(1),
                y: +(pt.y - headPt.y).toFixed(1),
                // For backward trains the polyline direction is opposite to travel.
                rotation: frame.travelForward ? pt.rotation : pt.rotation + 180,
              }));
            }
          } else {
            markerRef.current?.setLatLng([frame.lat, frame.lon]);
          }
        } else {
          // No polyline — fall back to server-computed GPS position.
          markerRef.current?.setLatLng([frame.lat, frame.lon]);
        }

        rotationRef.current = locoRotation;
        wagonOffsetsRef.current = wagonOffsets;

        const el = markerRef.current?.getElement();
        if (el) applyToDOM(el, locoRotation, wagonOffsets, carCount);
      }

      animRef.current = requestAnimationFrame(step);
    };

    animRef.current = requestAnimationFrame(step);
    return () => {
      cancelAnimationFrame(animRef.current);
    };
  }, [trajectory, map, carCount, showWagons]);

  // Click handler.
  const handleClick = useCallback(() => {
    onSelect(isSelected ? null : train_id);
  }, [onSelect, isSelected, train_id]);

  return (
    <Marker
      ref={markerRef}
      position={initPos}
      icon={icon}
      eventHandlers={{
        click: (e: L.LeafletMouseEvent) => {
          L.DomEvent.stopPropagation(e.originalEvent);
          handleClick();
        },
      }}
    />
  );
}
