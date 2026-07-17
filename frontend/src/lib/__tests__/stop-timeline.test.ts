import { buildStopTimeline } from '@/lib/stop-timeline';
import type { StopSequenceItem } from '@/types';

function stop(sequence: number, state: StopSequenceItem['state']) {
  return {
    station_name: `Station ${sequence}`,
    station_name_th: null,
    sequence,
    aimed_arrival_minutes: sequence,
    aimed_departure_minutes: sequence,
    arrival_day_offset: 0,
    departure_day_offset: 0,
    delay_minutes: 0,
    state,
  } satisfies StopSequenceItem;
}

describe('buildStopTimeline', () => {
  it('keeps every station and marks the first unpassed stop active', () => {
    const sequence = Array.from({ length: 12 }, (_, index) =>
      stop(index, index < 7 ? 'PASSED' : 'PENDING')
    );

    const timeline = buildStopTimeline(sequence);

    expect(timeline.stops).toHaveLength(12);
    expect(timeline.activeIndex).toBe(7);
  });
});
