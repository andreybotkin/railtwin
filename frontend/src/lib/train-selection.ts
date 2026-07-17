export interface TrainScreenPoint {
  trainId: number;
  x: number;
  y: number;
}

/** Pick the locomotive whose centre is closest to the actual pointer position. */
export function nearestTrainId(
  click: { x: number; y: number },
  trains: TrainScreenPoint[],
  fallbackTrainId: number
): number {
  let nearestId = fallbackTrainId;
  let nearestDistanceSquared = Number.POSITIVE_INFINITY;

  for (const train of trains) {
    const dx = train.x - click.x;
    const dy = train.y - click.y;
    const distanceSquared = dx * dx + dy * dy;
    if (distanceSquared < nearestDistanceSquared) {
      nearestDistanceSquared = distanceSquared;
      nearestId = train.trainId;
    }
  }

  return nearestId;
}
