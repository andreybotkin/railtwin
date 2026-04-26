import { buildConsistGeoPoints } from '@/lib/wagon-placement';
import type { ConsistSpec } from '@/types';

const CONSIST: ConsistSpec = {
  locomotive_length_m: 20,
  car_count: 3,
  car_length_m: 24,
  total_length_m: 20 + 3 * 24,
};

function equatorPolyline(lengthM: number): [number, number][] {
  // 1° at the equator ≈ 111_320 m — generate a straight east-going line.
  const metresPerDegree = 111_320;
  const endLon = lengthM / metresPerDegree;
  return [
    [0, 0],
    [endLon, 0],
  ];
}

describe('buildConsistGeoPoints', () => {
  it('returns one entry per body with the locomotive first', () => {
    const placements = buildConsistGeoPoints(equatorPolyline(5_000), 1_000, CONSIST);
    expect(placements).toHaveLength(1 + CONSIST.car_count);
    expect(placements[0].kind).toBe('locomotive');
    expect(placements[0].index).toBe(0);
    expect(placements.slice(1).every((body) => body.kind === 'carriage')).toBe(true);
  });

  it('places carriages behind the locomotive along the polyline', () => {
    const polyline = equatorPolyline(10_000);
    const placements = buildConsistGeoPoints(polyline, 5_000, CONSIST);
    const longitudes = placements.map((body) => body.lon);
    // Each subsequent body should sit to the west of (smaller lon than) the
    // previous one, because the polyline runs east and the tail trails behind.
    for (let i = 1; i < longitudes.length; i += 1) {
      expect(longitudes[i]).toBeLessThan(longitudes[i - 1]);
    }
  });

  it('extrapolates behind the polyline start when the train has not fully departed', () => {
    const polyline = equatorPolyline(1_000);
    const placements = buildConsistGeoPoints(polyline, 10, CONSIST);
    // With only 10 m cleared, every carriage must sit at a negative longitude.
    const tailLons = placements.slice(1).map((b) => b.lon);
    expect(tailLons.every((lon) => lon < 0)).toBe(true);
  });

  it('returns an empty array when the polyline has fewer than two coords', () => {
    expect(buildConsistGeoPoints([[0, 0]], 100, CONSIST)).toEqual([]);
    expect(buildConsistGeoPoints([], 100, CONSIST)).toEqual([]);
  });

  it('places carriages east of the locomotive for backward trains', () => {
    const polyline = equatorPolyline(10_000);
    // Backward train: head at 5000 m from the polyline START, but travelling
    // east→west (polyline was stored west→east). The tail should extend EAST
    // of the locomotive (larger lon), not west.
    const placements = buildConsistGeoPoints(polyline, 5_000, CONSIST, false);
    const longitudes = placements.map((body) => body.lon);
    for (let i = 1; i < longitudes.length; i += 1) {
      expect(longitudes[i]).toBeGreaterThan(longitudes[i - 1]);
    }
  });

  it('rotates bodies 180° for backward trains', () => {
    const polyline = equatorPolyline(10_000);
    const forward = buildConsistGeoPoints(polyline, 5_000, CONSIST, true);
    const backward = buildConsistGeoPoints(polyline, 5_000, CONSIST, false);
    const diff =
      ((backward[0].rotationDeg - forward[0].rotationDeg) % 360 + 360) % 360;
    expect(Math.abs(diff - 180)).toBeLessThan(1);
  });
});
