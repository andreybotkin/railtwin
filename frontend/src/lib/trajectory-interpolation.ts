/**
 * Client-side trajectory interpolation.
 *
 * Port of geops/mobility-toolbox-js `getVehiclePosition.ts` and `renderTrajectories.ts`
 * adapted for WGS84 (lat/lon) coordinates used by Leaflet — no EPSG:3857 projection needed.
 *
 * Core idea (from RealtimeEngine):
 *   The server generates `time_intervals = [[unix_ms, geom_frac, rotation_deg], ...]`
 *   covering TRAJECTORY_LOOKAHEAD_SECONDS ahead.  On every rAF tick the client calls
 *   `getVehiclePosition(Date.now(), trajectory)` to compute the exact position — no
 *   waiting for the next server update needed, giving truly smooth 60fps movement.
 *
 * @see https://github.com/geops/mobility-toolbox-js/blob/master/src/common/utils/getVehiclePosition.ts
 * @see https://github.com/geops/mobility-toolbox-js/blob/master/src/common/utils/renderTrajectories.ts
 */

import type { TrainTrajectory } from '@/types';

/** Result of position interpolation at a given moment. */
export interface VehiclePosition {
  /** WGS84 longitude */
  lon: number;
  /** WGS84 latitude */
  lat: number;
  /** Heading in degrees 0–360, 0 = North */
  rotation: number;
}

/**
 * Interpolate a position along a GeoJSON LineString at a given fractional position.
 *
 * Port of OL `LineString.getCoordinateAt()` in pure JavaScript for WGS84 coordinates.
 *
 * @param coordinates  Array of [lon, lat] pairs constituting the LineString.
 * @param fraction     0.0 = first point, 1.0 = last point.
 * @returns [lon, lat] at the requested fraction.
 */
export function interpolateLineString(
  coordinates: [number, number][],
  fraction: number,
): [number, number] {
  if (!coordinates.length) return [0, 0];
  if (fraction <= 0) return coordinates[0];
  if (fraction >= 1) return coordinates[coordinates.length - 1];

  // Compute cumulative Euclidean distances (fast enough for WGS84 at country scale)
  let totalLength = 0;
  const segLengths: number[] = [];
  for (let i = 0; i < coordinates.length - 1; i++) {
    const dx = coordinates[i + 1][0] - coordinates[i][0];
    const dy = coordinates[i + 1][1] - coordinates[i][1];
    const len = Math.sqrt(dx * dx + dy * dy);
    segLengths.push(len);
    totalLength += len;
  }

  if (totalLength === 0) return coordinates[0];

  const target = fraction * totalLength;
  let accumulated = 0;

  for (let i = 0; i < segLengths.length; i++) {
    if (accumulated + segLengths[i] >= target) {
      const t = segLengths[i] > 0 ? (target - accumulated) / segLengths[i] : 0;
      const lon = coordinates[i][0] + t * (coordinates[i + 1][0] - coordinates[i][0]);
      const lat = coordinates[i][1] + t * (coordinates[i + 1][1] - coordinates[i][1]);
      return [lon, lat];
    }
    accumulated += segLengths[i];
  }

  return coordinates[coordinates.length - 1];
}

/**
 * Compute a vehicle's current position given its trajectory and the current time.
 *
 * geops pattern: time_intervals = [[unix_ms, geom_frac, rotation_deg], ...]
 *   - If `nowMs < first interval`  → display first known position
 *   - If `nowMs > last interval`   → display last known position
 *   - Otherwise:                   → interpolate inside the matching bracket
 *
 * @param nowMs          Current Unix timestamp in milliseconds (Date.now()).
 * @param trajectory     Trajectory object from the gateway /ws/trajectory endpoint.
 * @returns              Position + rotation at `nowMs`, or null if trajectory is empty.
 */
export function getVehiclePosition(
  nowMs: number,
  trajectory: TrainTrajectory,
): VehiclePosition | null {
  const { time_intervals: intervals } = trajectory.properties;
  const coords = trajectory.geometry.coordinates as [number, number][];

  if (!intervals.length || !coords.length) return null;

  const firstInterval = intervals[0];
  const lastInterval = intervals[intervals.length - 1];

  let geomFrac: number;
  let rotation: number;

  if (nowMs <= firstInterval[0]) {
    // Before trajectory start: show first known position
    geomFrac = firstInterval[1];
    rotation = firstInterval[2];
  } else if (nowMs >= lastInterval[0]) {
    // After trajectory end: show last known position
    geomFrac = lastInterval[1];
    rotation = lastInterval[2];
  } else {
    // Find the enclosing bracket and interpolate
    geomFrac = lastInterval[1];
    rotation = lastInterval[2];

    for (let j = 0; j < intervals.length - 1; j++) {
      const [tStart, fracStart, rotStart] = intervals[j];
      const [tEnd, fracEnd] = intervals[j + 1];

      if (tStart <= nowMs && nowMs <= tEnd) {
        const timeFrac = (tEnd - tStart) > 0 ? (nowMs - tStart) / (tEnd - tStart) : 0;
        geomFrac = fracStart + timeFrac * (fracEnd - fracStart);
        // Rotation is taken from the start of the bracket (heading doesn't interpolate well)
        rotation = rotStart;
        break;
      }
    }
  }

  const [lon, lat] = interpolateLineString(coords, geomFrac);
  return { lon, lat, rotation };
}

/**
 * Check whether a trajectory's time_intervals are still valid at `nowMs`.
 * Returns false if the trajectory has expired and should be removed from the map.
 *
 * geops `purgeOutOfDateTrajectories()` pattern.
 */
export function isTrajectoryValid(trajectory: TrainTrajectory, nowMs: number): boolean {
  const intervals = trajectory.properties.time_intervals;
  if (!intervals.length) return false;
  const lastTime = intervals[intervals.length - 1][0];
  // Keep trajectory a few seconds past its end to avoid flicker on refresh boundary
  return nowMs < lastTime + 5000;
}
