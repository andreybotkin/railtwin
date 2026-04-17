/**
 * Client-side trajectory interpolation.
 *
 * The simulation pre-computes a dense array of frames — each a `(t_ms, lon,
 * lat, geom_fraction, head_distance_m, rotation_deg, speed_kmh, status)`
 * tuple — that already captures dwell windows as zero-speed runs. The client
 * only has to locate the bracketing pair for `nowMs` and linearly interpolate
 * the lon/lat/geom_fraction between them, carrying everything else forward
 * from the start of the bracket.
 */

import type { Trajectory, TrajectoryFrame } from '@/types';

/** Point on the rail polyline together with the metadata the map needs. */
export interface InterpolatedFrame {
  lon: number;
  lat: number;
  rotation: number;
  speedKmh: number;
  geomFraction: number;
  headDistanceM: number;
  status: TrajectoryFrame['status'];
  /** True while `nowMs` is inside the trajectory window. */
  fresh: boolean;
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

function fromFrame(frame: TrajectoryFrame, fresh: boolean): InterpolatedFrame {
  return {
    lon: frame.lon,
    lat: frame.lat,
    rotation: frame.rotation_deg,
    speedKmh: frame.speed_kmh,
    geomFraction: frame.geom_fraction,
    headDistanceM: frame.head_distance_m,
    status: frame.status,
    fresh,
  };
}

/**
 * Interpolate a trajectory frame for the given moment.
 *
 * Returns `null` only when the trajectory has no frames at all. Before the
 * first frame → the first frame (stale). After the last frame → the last
 * frame (stale). In between → a fresh linear interpolation.
 */
export function getTrajectoryFrameAt(
  nowMs: number,
  trajectory: Trajectory,
): InterpolatedFrame | null {
  const { frames } = trajectory;
  if (!frames.length) return null;

  const first = frames[0];
  if (nowMs <= first.t_ms) return fromFrame(first, false);

  const last = frames[frames.length - 1];
  if (nowMs >= last.t_ms) return fromFrame(last, false);

  // Binary search for the bracket (frames are monotonic in t_ms).
  let lo = 0;
  let hi = frames.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (frames[mid].t_ms <= nowMs) lo = mid;
    else hi = mid;
  }

  const start = frames[lo];
  const end = frames[hi];
  const span = end.t_ms - start.t_ms;
  const t = span > 0 ? (nowMs - start.t_ms) / span : 0;

  return {
    lon: lerp(start.lon, end.lon, t),
    lat: lerp(start.lat, end.lat, t),
    rotation: start.rotation_deg,
    speedKmh: start.speed_kmh,
    geomFraction: lerp(start.geom_fraction, end.geom_fraction, t),
    headDistanceM: lerp(start.head_distance_m, end.head_distance_m, t),
    status: start.status,
    fresh: true,
  };
}

/**
 * Check whether the trajectory window still contains `nowMs` (with a small
 * grace period to avoid flicker at the refresh boundary).
 */
export function isTrajectoryValid(
  trajectory: Trajectory,
  nowMs: number,
  graceMs = 5_000,
): boolean {
  return nowMs < trajectory.valid_until_ms + graceMs;
}
