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

import type { TrainPositionUpdate, TrainTrajectory } from '@/types';

/** Result of position interpolation at a given moment. */
export interface VehiclePosition {
  /** WGS84 longitude */
  lon: number;
  /** WGS84 latitude */
  lat: number;
  /** Heading in degrees 0–360, 0 = North */
  rotation: number;
}

export interface VehicleTrajectoryState extends VehiclePosition {
  /** 0..1 fraction along the trajectory geometry */
  geomFraction: number;
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
  const state = getVehicleTrajectoryState(nowMs, trajectory);
  if (!state) return null;
  return {
    lon: state.lon,
    lat: state.lat,
    rotation: state.rotation,
  };
}

export function getVehicleTrajectoryState(
  nowMs: number,
  trajectory: TrainTrajectory,
): VehicleTrajectoryState | null {
  const {
    time_intervals: intervals,
    coordinate_timestamps: coordinateTimestamps,
  } = trajectory.properties;
  const coords = trajectory.geometry.coordinates as [number, number][];

  if (coordinateTimestamps && coordinateTimestamps.length) {
    const firstPoint = coordinateTimestamps[0];
    const lastPoint = coordinateTimestamps[coordinateTimestamps.length - 1];

    if (nowMs <= firstPoint[0]) {
      return {
        lon: firstPoint[1][0],
        lat: firstPoint[1][1],
        rotation: firstPoint[2],
        geomFraction: intervals[0]?.[1] ?? 0,
      };
    }
    if (nowMs >= lastPoint[0]) {
      return {
        lon: lastPoint[1][0],
        lat: lastPoint[1][1],
        rotation: lastPoint[2],
        geomFraction: intervals[intervals.length - 1]?.[1] ?? 1,
      };
    }

    for (let j = 0; j < coordinateTimestamps.length - 1; j++) {
      const [tStart, startCoord, rotStart] = coordinateTimestamps[j];
      const [tEnd, endCoord] = coordinateTimestamps[j + 1];
      if (tStart <= nowMs && nowMs <= tEnd) {
        const timeFrac = (tEnd - tStart) > 0 ? (nowMs - tStart) / (tEnd - tStart) : 0;
        const lon = startCoord[0] + timeFrac * (endCoord[0] - startCoord[0]);
        const lat = startCoord[1] + timeFrac * (endCoord[1] - startCoord[1]);
        let geomFraction = intervals[intervals.length - 1]?.[1] ?? 1;
        for (let i = 0; i < intervals.length - 1; i++) {
          const [intervalStart, fracStart] = intervals[i];
          const [intervalEnd, fracEnd] = intervals[i + 1];
          if (intervalStart <= nowMs && nowMs <= intervalEnd) {
            const intervalFrac = (intervalEnd - intervalStart) > 0
              ? (nowMs - intervalStart) / (intervalEnd - intervalStart)
              : 0;
            geomFraction = fracStart + intervalFrac * (fracEnd - fracStart);
            break;
          }
        }
        return { lon, lat, rotation: rotStart, geomFraction };
      }
    }
  }

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
  return { lon, lat, rotation, geomFraction: geomFrac };
}

export function getVehiclePositionAtFraction(
  trajectory: TrainTrajectory,
  geomFraction: number,
  fallbackRotation = 0,
): VehiclePosition | null {
  const coords = trajectory.geometry.coordinates as [number, number][];
  if (!coords.length) return null;

  const safeFraction = Math.max(0, Math.min(1, geomFraction));
  const [lon, lat] = interpolateLineString(coords, safeFraction);
  const sampleStep = 0.0025;
  const beforeFraction = Math.max(0, safeFraction - sampleStep);
  const afterFraction = Math.min(1, safeFraction + sampleStep);
  const [beforeLon, beforeLat] = interpolateLineString(coords, beforeFraction);
  const [afterLon, afterLat] = interpolateLineString(coords, afterFraction);
  const dx = afterLon - beforeLon;
  const dy = afterLat - beforeLat;

  let rotation = fallbackRotation;
  if (Math.abs(dx) > 1e-9 || Math.abs(dy) > 1e-9) {
    rotation = (Math.atan2(dx, dy) * 180) / Math.PI;
    if (rotation < 0) rotation += 360;
  }

  return { lon, lat, rotation };
}

/**
 * Build a train-position snapshot from a trajectory payload.
 *
 * The trajectory already contains the metadata the map needs for popups and
 * route highlighting, while the exact current coordinates come from
 * `getVehiclePosition()`.
 */
export function buildPositionFromTrajectory(
  trajectory: TrainTrajectory,
  nowMs: number,
): TrainPositionUpdate | null {
  const vehiclePosition = getVehiclePosition(nowMs, trajectory);
  if (!vehiclePosition) {
    return null;
  }

  const props = trajectory.properties;
  return {
    train_id: props.train_id,
    train_number: props.train_number,
    train_type: props.train_type,
    route_id: props.route_id,
    location: {
      type: 'Point',
      coordinates: [vehiclePosition.lon, vehiclePosition.lat],
    },
    speed: props.speed ?? null,
    heading: vehiclePosition.rotation,
    status: props.status ?? 'moving',
    delay_minutes: props.delay_minutes,
    next_station: props.next_station,
    prev_station: props.prev_station,
    eta_next_station: props.eta_next_station ?? null,
    progress: props.progress ?? 0,
    route_progress: props.route_progress ?? undefined,
    segment_progress: props.segment_progress ?? undefined,
    current_edge_id: props.current_edge_id,
    graph_from_station_id: props.graph_from_station_id,
    graph_to_station_id: props.graph_to_station_id,
    topology_version: props.topology_version,
  };
}

/**
 * Check whether a trajectory's time_intervals are still valid at `nowMs`.
 * Returns false if the trajectory has expired and should be removed from the map.
 *
 * geops `purgeOutOfDateTrajectories()` pattern.
 */
export function isTrajectoryValid(trajectory: TrainTrajectory, nowMs: number): boolean {
  const coordinateTimestamps = trajectory.properties.coordinate_timestamps;
  if (coordinateTimestamps && coordinateTimestamps.length) {
    const lastTime = coordinateTimestamps[coordinateTimestamps.length - 1][0];
    return nowMs < lastTime + 5000;
  }

  const intervals = trajectory.properties.time_intervals;
  if (!intervals.length) return false;
  const lastTime = intervals[intervals.length - 1][0];
  // Keep trajectory a few seconds past its end to avoid flicker on refresh boundary
  return nowMs < lastTime + 5000;
}
