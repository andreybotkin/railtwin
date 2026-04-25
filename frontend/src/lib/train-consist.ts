/**
 * Screen-space consist placement.
 *
 * Converts a geographic route polyline to screen pixels, then walks along it
 * to find where each wagon sits.  This runs inside the rAF loop every frame,
 * so it must be fast — no turf, no GeoJSON, pure pixel math.
 *
 * Ported from the main branch TrainMarker with travelForward support added.
 */

export interface ScreenPoint {
  x: number;
  y: number;
}

export interface ConsistScreenPoint extends ScreenPoint {
  /** Compass bearing of the polyline at this point, 0 = N, 90 = E … */
  rotation: number;
}

function normalizeHeading(rotation: number): number {
  let n = rotation;
  while (n < 0) n += 360;
  while (n >= 360) n -= 360;
  return n;
}

function getHeadingDegrees(
  from: ScreenPoint,
  to: ScreenPoint,
  fallbackRotation: number,
): number {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  if (Math.abs(dx) < 1e-9 && Math.abs(dy) < 1e-9) {
    return normalizeHeading(fallbackRotation);
  }
  // screen-space: x right, y down.  atan2(dx, -dy) gives compass bearing.
  return normalizeHeading((Math.atan2(dx, -dy) * 180) / Math.PI);
}

function interpolatePoint(
  start: ScreenPoint,
  end: ScreenPoint,
  distanceFromStart: number,
): ScreenPoint {
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const segLen = Math.hypot(dx, dy);
  if (segLen <= 1e-9) return { x: start.x, y: start.y };
  const ratio = distanceFromStart / segLen;
  return { x: start.x + dx * ratio, y: start.y + dy * ratio };
}

/**
 * Place wagon anchor points along a screen-space polyline.
 *
 * @param polyline       Route polyline in screen pixels (already converted via
 *                       map.latLngToContainerPoint).
 * @param geomFraction   Head position as a 0–1 fraction of the polyline length.
 * @param fallbackRotation  Compass heading to use when a segment is zero-length.
 * @param distancesBehindHead  Array of pixel distances behind the head (positive
 *                       = toward polyline start for forward trains; pass negative
 *                       values for backward trains so wagons trail correctly).
 */
export function buildConsistScreenPoints(
  polyline: ScreenPoint[],
  geomFraction: number,
  fallbackRotation: number,
  distancesBehindHead: number[],
): ConsistScreenPoint[] {
  if (polyline.length < 2 || distancesBehindHead.length === 0) return [];

  // Build cumulative pixel lengths along the polyline.
  const cumulative: number[] = [0];
  let totalLength = 0;
  for (let i = 0; i < polyline.length - 1; i++) {
    totalLength += Math.hypot(
      polyline[i + 1].x - polyline[i].x,
      polyline[i + 1].y - polyline[i].y,
    );
    cumulative.push(totalLength);
  }

  if (totalLength <= 1e-9) {
    return distancesBehindHead.map(() => ({
      x: polyline[0].x,
      y: polyline[0].y,
      rotation: normalizeHeading(fallbackRotation),
    }));
  }

  const headDistance = Math.max(0, Math.min(1, geomFraction)) * totalLength;

  // For extrapolation before the start.
  const firstTangentHeading = getHeadingDegrees(polyline[0], polyline[1], fallbackRotation);
  const firstDx = polyline[1].x - polyline[0].x;
  const firstDy = polyline[1].y - polyline[0].y;
  const firstLen = Math.hypot(firstDx, firstDy) || 1;

  // For extrapolation past the end.
  const lastIdx = polyline.length - 1;
  const lastTangentHeading = getHeadingDegrees(polyline[lastIdx - 1], polyline[lastIdx], fallbackRotation);
  const lastDx = polyline[lastIdx].x - polyline[lastIdx - 1].x;
  const lastDy = polyline[lastIdx].y - polyline[lastIdx - 1].y;
  const lastLen = Math.hypot(lastDx, lastDy) || 1;

  const points: ConsistScreenPoint[] = [];

  for (const dist of distancesBehindHead) {
    const targetDistance = headDistance - dist;

    if (targetDistance <= 0) {
      // Extrapolate before the polyline start.
      const extra = -targetDistance;
      points.push({
        x: polyline[0].x - (firstDx / firstLen) * extra,
        y: polyline[0].y - (firstDy / firstLen) * extra,
        rotation: firstTangentHeading,
      });
      continue;
    }

    if (targetDistance >= totalLength) {
      // Extrapolate past the polyline end.
      const extra = targetDistance - totalLength;
      points.push({
        x: polyline[lastIdx].x + (lastDx / lastLen) * extra,
        y: polyline[lastIdx].y + (lastDy / lastLen) * extra,
        rotation: lastTangentHeading,
      });
      continue;
    }

    // Find the segment containing targetDistance.
    let segIdx = 0;
    while (segIdx < cumulative.length - 1 && cumulative[segIdx + 1] < targetDistance) {
      segIdx++;
    }

    const segStart = polyline[segIdx];
    const segEnd = polyline[Math.min(segIdx + 1, polyline.length - 1)];
    const localDist = targetDistance - cumulative[segIdx];
    const pt = interpolatePoint(segStart, segEnd, localDist);

    points.push({
      x: pt.x,
      y: pt.y,
      rotation: getHeadingDegrees(segStart, segEnd, fallbackRotation),
    });
  }

  return points;
}
