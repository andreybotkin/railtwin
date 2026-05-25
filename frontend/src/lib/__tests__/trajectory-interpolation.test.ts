import {
  getTrajectoryFrameAt,
  isTrajectoryValid,
} from '@/lib/trajectory-interpolation';
import type { Trajectory, TrajectoryFrame } from '@/types';

function makeFrame(
  partial: Partial<TrajectoryFrame> &
    Pick<TrajectoryFrame, 't_ms' | 'lon' | 'lat'>
): TrajectoryFrame {
  return {
    t_ms: partial.t_ms,
    lon: partial.lon,
    lat: partial.lat,
    geom_fraction: partial.geom_fraction ?? 0,
    head_distance_m: partial.head_distance_m ?? 0,
    rotation_deg: partial.rotation_deg ?? 90,
    speed_kmh: partial.speed_kmh ?? 60,
    status: partial.status ?? 'moving',
  };
}

function makeTrajectory(frames: TrajectoryFrame[]): Trajectory {
  const last = frames[frames.length - 1];
  return {
    train_id: 1,
    generated_at_ms: frames[0]?.t_ms ?? 0,
    valid_until_ms: (last?.t_ms ?? 0) + 60_000,
    route_coords: [
      [100, 13],
      [101, 13],
    ],
    route_length_m: 111_320,
    frames,
    anchors: [],
    consist: {
      locomotive_length_m: 20,
      car_count: 4,
      car_length_m: 20,
      total_length_m: 100,
    },
    meta: {
      train_id: 1,
      train_number: '1',
      train_type: 'ordinary',
      train_name: null,
      color: '#43A047',
      operator: 'SRT',
      origin_station: null,
      destination_station: null,
      origin_station_th: null,
      destination_station_th: null,
      prev_station: null,
      next_station: null,
      next_station_th: null,
      eta_next_ms: null,
      delay_minutes: 0,
      route_id: null,
      route_progress_pct: 0,
      segment_progress_pct: 0,
      current_edge_id: null,
      graph_from_station_id: null,
      graph_to_station_id: null,
      topology_version: null,
    },
    bounds: [100, 13, 101, 13],
  };
}

describe('getTrajectoryFrameAt', () => {
  it('returns null when the trajectory has no frames', () => {
    const trajectory = makeTrajectory([]);
    expect(getTrajectoryFrameAt(1_000, trajectory)).toBeNull();
  });

  it('clamps to the first frame when nowMs is before the trajectory window', () => {
    const trajectory = makeTrajectory([
      makeFrame({ t_ms: 1_000, lon: 100, lat: 13, head_distance_m: 0 }),
      makeFrame({ t_ms: 2_000, lon: 100.5, lat: 13, head_distance_m: 100 }),
    ]);
    const result = getTrajectoryFrameAt(500, trajectory);
    expect(result).not.toBeNull();
    expect(result!.lon).toBeCloseTo(100);
    expect(result!.fresh).toBe(false);
  });

  it('clamps to the last frame when nowMs is past the trajectory end', () => {
    const trajectory = makeTrajectory([
      makeFrame({ t_ms: 1_000, lon: 100, lat: 13 }),
      makeFrame({ t_ms: 2_000, lon: 100.5, lat: 13, head_distance_m: 100 }),
    ]);
    const result = getTrajectoryFrameAt(3_000, trajectory);
    expect(result!.lon).toBeCloseTo(100.5);
    expect(result!.fresh).toBe(false);
  });

  it('linearly interpolates inside the bracketing pair', () => {
    const trajectory = makeTrajectory([
      makeFrame({
        t_ms: 1_000,
        lon: 100,
        lat: 13,
        head_distance_m: 0,
        geom_fraction: 0,
      }),
      makeFrame({
        t_ms: 3_000,
        lon: 101,
        lat: 13,
        head_distance_m: 200,
        geom_fraction: 1,
      }),
    ]);
    const midpoint = getTrajectoryFrameAt(2_000, trajectory)!;
    expect(midpoint.lon).toBeCloseTo(100.5, 5);
    expect(midpoint.headDistanceM).toBeCloseTo(100, 5);
    expect(midpoint.geomFraction).toBeCloseTo(0.5, 5);
    expect(midpoint.fresh).toBe(true);
  });

  it('keeps the head pinned during a dwell (zero-speed) window', () => {
    const trajectory = makeTrajectory([
      makeFrame({
        t_ms: 1_000,
        lon: 100.5,
        lat: 13,
        status: 'dwelling',
        speed_kmh: 0,
        head_distance_m: 100,
        geom_fraction: 0.5,
      }),
      makeFrame({
        t_ms: 5_000,
        lon: 100.5,
        lat: 13,
        status: 'dwelling',
        speed_kmh: 0,
        head_distance_m: 100,
        geom_fraction: 0.5,
      }),
    ]);
    const result = getTrajectoryFrameAt(3_000, trajectory)!;
    expect(result.speedKmh).toBe(0);
    expect(result.status).toBe('dwelling');
    expect(result.headDistanceM).toBeCloseTo(100, 5);
  });
});

describe('isTrajectoryValid', () => {
  it('accepts trajectories within their validity window', () => {
    const trajectory = makeTrajectory([
      makeFrame({ t_ms: 1_000, lon: 100, lat: 13 }),
      makeFrame({ t_ms: 2_000, lon: 101, lat: 13 }),
    ]);
    expect(isTrajectoryValid(trajectory, 2_000)).toBe(true);
  });

  it('rejects trajectories that have fully expired past the grace window', () => {
    const trajectory = makeTrajectory([
      makeFrame({ t_ms: 1_000, lon: 100, lat: 13 }),
      makeFrame({ t_ms: 2_000, lon: 101, lat: 13 }),
    ]);
    const expired = trajectory.valid_until_ms + 10_000;
    expect(isTrajectoryValid(trajectory, expired)).toBe(false);
  });
});
