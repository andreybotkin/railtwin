export interface ConsistSpec {
  locomotive_length_m: number;
  car_count: number;
  car_length_m: number;
  total_length_m?: number;
}

export interface TrajectoryFrame {
  t_ms: number;
  lon: number;
  lat: number;
  geom_fraction: number;
  rotation_deg: number;
  speed_kmh: number;
  status: 'moving' | 'dwelling' | 'arrived';
}

export interface Trajectory {
  train_id: number;
  generated_at_ms: number;
  valid_until_ms: number;
  route_coords: [number, number][];
  route_length_m: number;
  frames: TrajectoryFrame[];
  anchors: Record<string, unknown>[];
  consist: ConsistSpec;
  meta: {
    train_id: number;
    train_number: string;
    train_type?: string | null;
    color: string;
    prev_station?: string | null;
    next_station?: string | null;
    delay_minutes?: number;
    route_progress_pct?: number;
  };
}

export function getTrajectoryFrameAt(nowMs: number, trajectory: Trajectory): TrajectoryFrame | null {
  const frames = trajectory.frames;
  if (!frames.length) return null;
  if (nowMs <= frames[0].t_ms) return frames[0];
  if (nowMs >= frames[frames.length - 1].t_ms) return frames[frames.length - 1];

  for (let i = 0; i < frames.length - 1; i++) {
    const start = frames[i];
    const end = frames[i + 1];
    if (start.t_ms <= nowMs && nowMs <= end.t_ms) {
      const t = end.t_ms === start.t_ms ? 0 : (nowMs - start.t_ms) / (end.t_ms - start.t_ms);
      return {
        t_ms: nowMs,
        lon: start.lon + (end.lon - start.lon) * t,
        lat: start.lat + (end.lat - start.lat) * t,
        geom_fraction: start.geom_fraction + (end.geom_fraction - start.geom_fraction) * t,
        rotation_deg: start.rotation_deg,
        speed_kmh: start.speed_kmh + (end.speed_kmh - start.speed_kmh) * t,
        status: start.status,
      };
    }
  }

  return frames[frames.length - 1];
}
