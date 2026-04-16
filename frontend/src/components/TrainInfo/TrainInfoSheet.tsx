'use client';

import { X } from 'lucide-react';

import { useRailwayStore } from '@/lib/stores/useRailwayStore';

export default function TrainInfoSheet() {
  const selectedTrainId = useRailwayStore((s) => s.selectedTrainId);
  const trajectories = useRailwayStore((s) => s.trajectories);
  const setSelectedTrainId = useRailwayStore((s) => s.setSelectedTrainId);

  if (!selectedTrainId) return null;
  const trajectory = trajectories.get(selectedTrainId);
  if (!trajectory) return null;

  return (
    <div className="absolute bottom-4 right-4 z-20 w-[320px] rounded-2xl border border-white/30 bg-white/20 p-4 text-white backdrop-blur-xl">
      <div className="mb-3 flex items-center justify-between">
        <span className="rounded-full px-2 py-1 text-xs font-semibold" style={{ backgroundColor: trajectory.meta.color }}>
          #{trajectory.meta.train_number}
        </span>
        <button onClick={() => setSelectedTrainId(null)} aria-label="close">
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="grid grid-cols-2 gap-2 text-sm">
        <div>Delay: {trajectory.meta.delay_minutes ?? 0} min</div>
        <div>Progress: {trajectory.meta.route_progress_pct ?? 0}%</div>
        <div className="col-span-2">{trajectory.meta.prev_station} → {trajectory.meta.next_station}</div>
      </div>
    </div>
  );
}
