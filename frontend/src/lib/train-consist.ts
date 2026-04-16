export interface ScreenPoint {
  x: number;
  y: number;
}

export interface ConsistScreenPoint extends ScreenPoint {
  rotation: number;
}

export interface ConsistPhysicsNode extends ScreenPoint {
  prevX: number;
  prevY: number;
}

function normalizeHeading(rotation: number): number {
  let normalized = rotation;
  while (normalized < 0) normalized += 360;
  while (normalized >= 360) normalized -= 360;
  return normalized;
}

function getHeadingDegrees(
  from: ScreenPoint,
  to: ScreenPoint,
  fallbackRotation: number
): number {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  if (Math.abs(dx) < 1e-9 && Math.abs(dy) < 1e-9) {
    return normalizeHeading(fallbackRotation);
  }

  return normalizeHeading((Math.atan2(dx, -dy) * 180) / Math.PI);
}

function interpolatePoint(
  start: ScreenPoint,
  end: ScreenPoint,
  distanceFromStart: number
): ScreenPoint {
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const segmentLength = Math.hypot(dx, dy);
  if (segmentLength <= 1e-9) {
    return { x: start.x, y: start.y };
  }

  const ratio = distanceFromStart / segmentLength;
  return {
    x: start.x + dx * ratio,
    y: start.y + dy * ratio,
  };
}

export function buildConsistScreenPoints(
  polyline: ScreenPoint[],
  geomFraction: number,
  fallbackRotation: number,
  distancesBehindHead: number[]
): ConsistScreenPoint[] {
  if (polyline.length < 2 || distancesBehindHead.length === 0) return [];

  const cumulative: number[] = [0];
  let totalLength = 0;
  for (let index = 0; index < polyline.length - 1; index += 1) {
    totalLength += Math.hypot(
      polyline[index + 1].x - polyline[index].x,
      polyline[index + 1].y - polyline[index].y
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
  const firstTangentHeading = getHeadingDegrees(
    polyline[0],
    polyline[1],
    fallbackRotation
  );
  const firstDx = polyline[1].x - polyline[0].x;
  const firstDy = polyline[1].y - polyline[0].y;
  const firstLength = Math.hypot(firstDx, firstDy) || 1;

  const points: ConsistScreenPoint[] = [];

  for (const distanceBehindHead of distancesBehindHead) {
    const targetDistance = headDistance - distanceBehindHead;

    if (targetDistance <= 0) {
      const extraDistance = -targetDistance;
      points.push({
        x: polyline[0].x - (firstDx / firstLength) * extraDistance,
        y: polyline[0].y - (firstDy / firstLength) * extraDistance,
        rotation: firstTangentHeading,
      });
      continue;
    }

    let segmentIndex = 0;
    while (
      segmentIndex < cumulative.length - 1 &&
      cumulative[segmentIndex + 1] < targetDistance
    ) {
      segmentIndex += 1;
    }

    const segmentStart = polyline[segmentIndex];
    const segmentEnd =
      polyline[Math.min(segmentIndex + 1, polyline.length - 1)];
    const localDistance = targetDistance - cumulative[segmentIndex];
    const point = interpolatePoint(segmentStart, segmentEnd, localDistance);

    points.push({
      x: point.x,
      y: point.y,
      rotation: getHeadingDegrees(segmentStart, segmentEnd, fallbackRotation),
    });
  }

  return points;
}

/**
 * Position-based dynamics update for a train consist.
 *
 * Uses Verlet integration + distance constraints so wagons remain connected to
 * each other and to the locomotive while still having physically plausible lag.
 */
export function solveConsistPhysics(
  nodes: ConsistPhysicsNode[],
  head: ScreenPoint,
  targetPathPoints: ConsistScreenPoint[],
  linkSpacingPx: number,
  dtSeconds: number
): ConsistScreenPoint[] {
  if (nodes.length === 0) return [];

  const damping = 0.86;
  const attraction = 0.34;
  const dt = Math.min(Math.max(dtSeconds, 1 / 240), 0.1);

  for (let i = 0; i < nodes.length; i += 1) {
    const node = nodes[i];
    const target = targetPathPoints[i] ??
      targetPathPoints[targetPathPoints.length - 1] ?? {
        x: head.x,
        y: head.y,
        rotation: 0,
      };

    const velocityX = (node.x - node.prevX) * damping;
    const velocityY = (node.y - node.prevY) * damping;

    node.prevX = node.x;
    node.prevY = node.y;

    node.x += velocityX;
    node.y += velocityY;

    // Gentle convergence to route-derived target to keep consist hugging rails.
    node.x += (target.x - node.x) * attraction * dt * 60;
    node.y += (target.y - node.y) * attraction * dt * 60;
  }

  // Gauss-Seidel distance projection (rope/chain constraint solver).
  const iterations = 4;
  for (let iter = 0; iter < iterations; iter += 1) {
    let anchorX = head.x;
    let anchorY = head.y;

    for (let i = 0; i < nodes.length; i += 1) {
      const node = nodes[i];
      const dx = node.x - anchorX;
      const dy = node.y - anchorY;
      const dist = Math.hypot(dx, dy) || 1;
      const correction = (dist - linkSpacingPx) / dist;

      node.x -= dx * correction;
      node.y -= dy * correction;

      anchorX = node.x;
      anchorY = node.y;
    }
  }

  const solved: ConsistScreenPoint[] = [];
  for (let i = 0; i < nodes.length; i += 1) {
    const node = nodes[i];
    const front = i === 0 ? head : nodes[i - 1];
    solved.push({
      x: node.x,
      y: node.y,
      rotation: getHeadingDegrees(
        node,
        front,
        targetPathPoints[i]?.rotation ?? 0
      ),
    });
  }

  return solved;
}
