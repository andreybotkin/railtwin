import { nearestTrainId } from '@/lib/train-selection';

describe('nearestTrainId', () => {
  it('selects the locomotive nearest to the pointer, not the marker on top', () => {
    expect(
      nearestTrainId(
        { x: 101, y: 100 },
        [
          { trainId: 10, x: 100, y: 100 },
          { trainId: 11, x: 112, y: 100 },
        ],
        11
      )
    ).toBe(10);
  });

  it('uses the clicked marker when no positions are available', () => {
    expect(nearestTrainId({ x: 0, y: 0 }, [], 42)).toBe(42);
  });
});
