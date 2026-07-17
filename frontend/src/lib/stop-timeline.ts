import type { StopSequenceItem } from '@/types';

export interface StopTimeline {
  stops: StopSequenceItem[];
  activeIndex: number;
}

/** Keep the complete timetable; the info sheet itself provides scrolling. */
export function buildStopTimeline(
  sequence: StopSequenceItem[] | null | undefined
): StopTimeline {
  const stops = sequence ? [...sequence] : [];
  return {
    stops,
    activeIndex: stops.findIndex((stop) => stop.state !== 'PASSED'),
  };
}
