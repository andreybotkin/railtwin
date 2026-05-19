/**
 * Geodesic wagon placement.
 *
 * Given the authoritative polyline the train rides (`route_coords` — [lon, lat]
 * in WGS84), the head position expressed in metres along that polyline
 * (`headDistanceM`), and a `ConsistSpec`, emit one `BodyPlacement` per
 * locomotive + carriage with a lon/lat centre and a heading. All arithmetic
 * is done in metres on the great-circle line via turf, so wagons stay glued
 * to the rail under any zoom level.
 *
 * `travelForward` reflects whether the train's `geom_fraction` increases over
 * time. When it is `false` (southbound train on a north→south polyline), the
 * consist is laid out from the head toward the *end* of the polyline instead
 * of its start, and every body's bearing is flipped 180°.
 */

import { along } from '@turf/along';
import { bearing } from '@turf/bearing';
import { lineString, point } from '@turf/helpers';
import { length as turfLength } from '@turf/length';

import type { ConsistSpec } from '@/types';

export type BodyKind = 'locomotive' | 'carriage';

export interface BodyPlacement {
  kind: BodyKind;
  /** 0 = locomotive, 1..N = carriages counted from the loco. */
  index: number;
  lon: number;
  lat: number;
  /** Length of the body in metres — useful for icon sizing. */
  lengthM: number;
  /** Compass bearing in degrees, 0 = north, 90 = east. */
  rotationDeg: number;
  /**
   * True when the body is facing the left/west hemisphere (bearing ∈ [180°, 360°)).
   * Used to select a horizontally-mirrored icon so bogies always appear at the
   * bottom regardless of travel direction.
   */
  facingLeft: boolean;
}

interface BodyLayout {
  kind: BodyKind;
  index: number;
  lengthM: number;
  /** Distance between the train head and the centre of this body (metres). */
  offsetM: number;
}

function layoutBodies(consist: ConsistSpec): BodyLayout[] {
  const layout: BodyLayout[] = [];
  const locoLength = Math.max(0, consist.locomotive_length_m);

  layout.push({
    kind: 'locomotive',
    index: 0,
    lengthM: locoLength,
    offsetM: locoLength / 2,
  });

  let cursor = locoLength;
  for (let i = 0; i < consist.car_count; i += 1) {
    const carLength = Math.max(0, consist.car_length_m);
    layout.push({
      kind: 'carriage',
      index: i + 1,
      lengthM: carLength,
      offsetM: cursor + carLength / 2,
    });
    cursor += carLength;
  }

  return layout;
}

function normaliseBearing(deg: number): number {
  let value = deg;
  while (value < 0) value += 360;
  while (value >= 360) value -= 360;
  return value;
}

function bearingBetween(
  a: [number, number],
  b: [number, number],
  fallback: number
): number {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  if (Math.abs(dx) < 1e-12 && Math.abs(dy) < 1e-12) {
    return normaliseBearing(fallback);
  }
  return normaliseBearing(bearing(point(a), point(b)));
}

/**
 * Place every body (locomotive + carriages) along the polyline so that the
 * locomotive's nose sits `headDistanceM` metres from the polyline start.
 *
 * Handles polylines that are shorter than the consist (the tail of the train
 * extrapolates past the origin using the first/last segment's bearing — which
 * only happens as trains depart their origin).
 */
export function buildConsistGeoPoints(
  routeCoords: [number, number][],
  headDistanceM: number,
  consist: ConsistSpec,
  travelForward = true
): BodyPlacement[] {
  if (routeCoords.length < 2) return [];

  const line = lineString(routeCoords);
  const totalLengthKm = turfLength(line, { units: 'kilometers' });
  const totalLengthM = totalLengthKm * 1_000;
  if (totalLengthM <= 0) return [];

  const clampedHead = Math.max(0, Math.min(totalLengthM, headDistanceM));
  const layout = layoutBodies(consist);

  const firstBearing = bearingBetween(routeCoords[0], routeCoords[1], 0);
  const lastBearing = bearingBetween(
    routeCoords[routeCoords.length - 2],
    routeCoords[routeCoords.length - 1],
    firstBearing
  );
  const epsilonKm = 0.002; // 2 metres — short enough to stay on one segment.

  // Forward trains lay the consist out at SMALLER polyline distances than the
  // head (toward the start). Backward trains use LARGER distances (toward the
  // end) so carriages still trail behind the locomotive visually.
  const sign = travelForward ? -1 : 1;

  const placements: BodyPlacement[] = [];

  for (const body of layout) {
    const targetM = clampedHead + sign * body.offsetM;

    if (targetM < 0) {
      // Forward train whose tail hasn't cleared the polyline start yet.
      const extraKm = -targetM / 1_000;
      const origin = routeCoords[0];
      const reverseBearing = normaliseBearing(firstBearing + 180);
      const [lon, lat] = offsetPoint(origin, reverseBearing, extraKm);
      placements.push({
        kind: body.kind,
        index: body.index,
        lon,
        lat,
        lengthM: body.lengthM,
        rotationDeg: firstBearing,
        facingLeft: firstBearing >= 180,
      });
      continue;
    }

    if (targetM > totalLengthM) {
      // Backward train whose tail hasn't cleared the polyline end yet.
      const extraKm = (targetM - totalLengthM) / 1_000;
      const end = routeCoords[routeCoords.length - 1];
      const [lon, lat] = offsetPoint(end, lastBearing, extraKm);
      const backwardRotation = normaliseBearing(lastBearing + 180);
      placements.push({
        kind: body.kind,
        index: body.index,
        lon,
        lat,
        lengthM: body.lengthM,
        rotationDeg: backwardRotation,
        facingLeft: backwardRotation >= 180,
      });
      continue;
    }

    const targetKm = targetM / 1_000;
    const centre = along(line, targetKm, { units: 'kilometers' });
    const lookBack = along(line, Math.max(0, targetKm - epsilonKm), {
      units: 'kilometers',
    });
    const lookAhead = along(
      line,
      Math.min(totalLengthKm, targetKm + epsilonKm),
      { units: 'kilometers' }
    );

    const [cx, cy] = centre.geometry.coordinates as [number, number];
    const back = lookBack.geometry.coordinates as [number, number];
    const forward = lookAhead.geometry.coordinates as [number, number];
    const polylineBearing = bearingBetween(back, forward, firstBearing);
    const rotationDeg = travelForward
      ? polylineBearing
      : normaliseBearing(polylineBearing + 180);

    placements.push({
      kind: body.kind,
      index: body.index,
      lon: cx,
      lat: cy,
      lengthM: body.lengthM,
      rotationDeg,
      facingLeft: rotationDeg >= 180,
    });
  }

  return placements;
}

/** Geodesic offset — distance in km along a bearing from a [lon, lat]. */
function offsetPoint(
  origin: [number, number],
  bearingDeg: number,
  distanceKm: number
): [number, number] {
  const R = 6_371; // Earth radius (km) — matches turf's default.
  const bearingRad = (bearingDeg * Math.PI) / 180;
  const lat1 = (origin[1] * Math.PI) / 180;
  const lon1 = (origin[0] * Math.PI) / 180;
  const angular = distanceKm / R;

  const lat2 = Math.asin(
    Math.sin(lat1) * Math.cos(angular) +
      Math.cos(lat1) * Math.sin(angular) * Math.cos(bearingRad)
  );
  const lon2 =
    lon1 +
    Math.atan2(
      Math.sin(bearingRad) * Math.sin(angular) * Math.cos(lat1),
      Math.cos(angular) - Math.sin(lat1) * Math.sin(lat2)
    );

  return [(lon2 * 180) / Math.PI, (lat2 * 180) / Math.PI];
}
