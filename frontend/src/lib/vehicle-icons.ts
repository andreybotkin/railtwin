/**
 * Runtime-generated icons for locomotives and carriages.
 *
 * We register one pre-coloured RGBA image per (train-type × body-kind) and
 * pick the right one per feature using a `match` expression on `icon-image`.
 * This avoids the fuzzy/undersized edges we'd get from feeding non-SDF canvas
 * data to MapLibre's SDF loader while still giving every train type its own
 * brand colour.
 *
 * Icons are designed in a wide frame, oriented **pointing east (+x)** so the
 * north-based bearing emitted by the trajectory interpolator can be converted
 * to east-facing icon rotation by subtracting 90° before applying
 * `icon-rotate`. Every shape is drawn on a single oversampled canvas so
 * MapLibre can downscale it without the usual edge shimmer.
 */

import type { Map as MapLibreMap } from 'maplibre-gl';

const DEVICE_SCALE = 3;

export type TrainTypeId =
  | 'special_express'
  | 'express'
  | 'rapid'
  | 'ordinary'
  | 'commuter'
  | 'default';

export const TRAIN_TYPE_PALETTE: Record<TrainTypeId, string> = {
  special_express: '#E53935',
  express: '#F57C00',
  rapid: '#1E88E5',
  ordinary: '#2E7D32',
  commuter: '#8E24AA',
  default: '#2196F3',
};

export const TRAIN_TYPE_IDS: TrainTypeId[] = [
  'special_express',
  'express',
  'rapid',
  'ordinary',
  'commuter',
  'default',
];

export const HALO_ICON_ID = 'railtwin-halo';
export const LIFT_GATE_ICON_ID = 'lift_gate';

export function locoIconId(type: TrainTypeId): string {
  return `railtwin-loco-${type}`;
}

export function locoIconIdLeft(type: TrainTypeId): string {
  return `railtwin-loco-${type}-left`;
}

export function carriageIconId(type: TrainTypeId): string {
  return `railtwin-carriage-${type}`;
}

export function carriageIconIdLeft(type: TrainTypeId): string {
  return `railtwin-carriage-${type}-left`;
}

function hexToRgb(hex: string): { r: number; g: number; b: number } {
  const parsed = hex.replace('#', '');
  return {
    r: parseInt(parsed.slice(0, 2), 16),
    g: parseInt(parsed.slice(2, 4), 16),
    b: parseInt(parsed.slice(4, 6), 16),
  };
}

function mix(c1: string, c2: string, t: number): string {
  const a = hexToRgb(c1);
  const b = hexToRgb(c2);
  const r = Math.round(a.r + (b.r - a.r) * t);
  const g = Math.round(a.g + (b.g - a.g) * t);
  const bl = Math.round(a.b + (b.b - a.b) * t);
  return `rgb(${r}, ${g}, ${bl})`;
}

function roundedRectPath(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  radius: number,
) {
  const r = Math.min(radius, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

/**
 * Modern diesel locomotive silhouette, facing east.
 *
 * Design:
 *   - Soft ground-shadow ellipse for depth.
 *   - Two dark rounded bogies peek below the body.
 *   - Body is a rounded wedge with a short angled nose.
 *   - Top half is a vertical gradient (brand colour → slightly darker)
 *     to read as a curved roof at small sizes.
 *   - A narrow dark roof strip and a white windshield mark the cab,
 *     giving the icon a clear "front".
 *   - A warm amber headlight pip on the nose.
 */
function drawLocomotive(
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  color: string,
) {
  const dark = mix(color, '#000000', 0.5);
  const light = mix(color, '#FFFFFF', 0.18);

  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';

  // Ground shadow.
  ctx.save();
  ctx.fillStyle = 'rgba(15, 23, 42, 0.22)';
  ctx.filter = 'blur(2px)';
  ctx.beginPath();
  ctx.ellipse(w * 0.52, h * 0.88, w * 0.42, h * 0.08, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();

  // Bogies.
  ctx.fillStyle = '#111827';
  roundedRectPath(ctx, w * 0.14, h * 0.74, w * 0.16, h * 0.14, h * 0.04);
  ctx.fill();
  roundedRectPath(ctx, w * 0.6, h * 0.74, w * 0.16, h * 0.14, h * 0.04);
  ctx.fill();

  // Body outline (wedge + rounded tail).
  const bodyTop = h * 0.22;
  const bodyBottom = h * 0.74;
  const tailX = w * 0.06;
  const tailR = h * 0.12;
  const shoulderX = w * 0.78;
  const noseTipX = w * 0.97;
  const midY = (bodyTop + bodyBottom) / 2;

  const bodyPath = () => {
    ctx.beginPath();
    ctx.moveTo(tailX + tailR, bodyTop);
    ctx.lineTo(shoulderX, bodyTop);
    ctx.quadraticCurveTo(w * 0.92, bodyTop + h * 0.04, noseTipX, midY);
    ctx.quadraticCurveTo(w * 0.92, bodyBottom - h * 0.04, shoulderX, bodyBottom);
    ctx.lineTo(tailX + tailR, bodyBottom);
    ctx.quadraticCurveTo(tailX, bodyBottom, tailX, bodyBottom - tailR);
    ctx.lineTo(tailX, bodyTop + tailR);
    ctx.quadraticCurveTo(tailX, bodyTop, tailX + tailR, bodyTop);
    ctx.closePath();
  };

  // Body fill with vertical gradient.
  const gradient = ctx.createLinearGradient(0, bodyTop, 0, bodyBottom);
  gradient.addColorStop(0, light);
  gradient.addColorStop(0.5, color);
  gradient.addColorStop(1, dark);
  ctx.fillStyle = gradient;
  bodyPath();
  ctx.fill();

  // Dark roof strip for silhouette at low zoom.
  ctx.save();
  ctx.fillStyle = dark;
  bodyPath();
  ctx.clip();
  ctx.fillRect(tailX, bodyTop, w, h * 0.1);
  ctx.restore();

  // Cab windshield (wrap-around).
  ctx.fillStyle = 'rgba(226, 232, 240, 0.95)';
  ctx.beginPath();
  ctx.moveTo(w * 0.7, bodyTop + h * 0.14);
  ctx.lineTo(w * 0.82, bodyTop + h * 0.14);
  ctx.quadraticCurveTo(
    w * 0.89,
    bodyTop + h * 0.2,
    w * 0.92,
    bodyTop + h * 0.32,
  );
  ctx.lineTo(w * 0.7, bodyTop + h * 0.32);
  ctx.closePath();
  ctx.fill();

  // Subtle side window strip on the engine hood.
  ctx.fillStyle = 'rgba(15, 23, 42, 0.55)';
  roundedRectPath(
    ctx,
    w * 0.18,
    bodyTop + h * 0.16,
    w * 0.48,
    h * 0.16,
    h * 0.04,
  );
  ctx.fill();

  // Headlight.
  ctx.fillStyle = '#FCD34D';
  ctx.beginPath();
  ctx.arc(w * 0.955, midY, h * 0.05, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.9)';
  ctx.lineWidth = 0.6;
  ctx.stroke();

  // White outline for contrast.
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.92)';
  ctx.lineWidth = 1.3;
  bodyPath();
  ctx.stroke();
}

/**
 * Passenger carriage silhouette: softly rounded body, dark window strip
 * split into panes, two bogies, ground shadow.
 */
function drawCarriage(
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  color: string,
) {
  const dark = mix(color, '#000000', 0.55);
  const light = mix(color, '#FFFFFF', 0.12);

  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';

  // Ground shadow.
  ctx.save();
  ctx.fillStyle = 'rgba(15, 23, 42, 0.2)';
  ctx.filter = 'blur(1.8px)';
  ctx.beginPath();
  ctx.ellipse(w * 0.5, h * 0.86, w * 0.44, h * 0.07, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();

  // Bogies.
  ctx.fillStyle = '#111827';
  roundedRectPath(ctx, w * 0.16, h * 0.72, w * 0.14, h * 0.14, h * 0.04);
  ctx.fill();
  roundedRectPath(ctx, w * 0.7, h * 0.72, w * 0.14, h * 0.14, h * 0.04);
  ctx.fill();

  // Body.
  const bodyTop = h * 0.26;
  const bodyBottom = h * 0.72;
  const bodyX = w * 0.04;
  const bodyW = w * 0.92;
  const bodyH = bodyBottom - bodyTop;
  const bodyR = h * 0.14;

  const gradient = ctx.createLinearGradient(0, bodyTop, 0, bodyBottom);
  gradient.addColorStop(0, light);
  gradient.addColorStop(0.55, color);
  gradient.addColorStop(1, dark);
  ctx.fillStyle = gradient;
  roundedRectPath(ctx, bodyX, bodyTop, bodyW, bodyH, bodyR);
  ctx.fill();

  // Window strip (split into panes for texture).
  const winTop = bodyTop + h * 0.1;
  const winH = h * 0.2;
  const winPadX = w * 0.08;
  const winInnerW = bodyW - winPadX * 2;
  const winPanes = 5;
  const paneGap = w * 0.012;
  const paneW = (winInnerW - paneGap * (winPanes - 1)) / winPanes;
  ctx.fillStyle = 'rgba(15, 23, 42, 0.8)';
  for (let i = 0; i < winPanes; i++) {
    const x = bodyX + winPadX + i * (paneW + paneGap);
    roundedRectPath(ctx, x, winTop, paneW, winH, h * 0.03);
    ctx.fill();
  }

  // Window highlight (subtle top sheen).
  ctx.fillStyle = 'rgba(255, 255, 255, 0.12)';
  ctx.fillRect(bodyX + winPadX, winTop, winInnerW, winH * 0.28);

  // Body outline.
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.85)';
  ctx.lineWidth = 1.1;
  roundedRectPath(ctx, bodyX, bodyTop, bodyW, bodyH, bodyR);
  ctx.stroke();
}

/**
 * Soft amber glow for the selected train.
 */
function drawHalo(ctx: CanvasRenderingContext2D, w: number, h: number) {
  const cx = w / 2;
  const cy = h / 2;
  const radius = Math.min(w, h) / 2;
  const gradient = ctx.createRadialGradient(cx, cy, radius * 0.15, cx, cy, radius);
  gradient.addColorStop(0, 'rgba(255, 234, 145, 0.95)');
  gradient.addColorStop(0.55, 'rgba(245, 158, 11, 0.45)');
  gradient.addColorStop(1, 'rgba(245, 158, 11, 0)');
  ctx.fillStyle = gradient;
  ctx.beginPath();
  ctx.arc(cx, cy, radius, 0, Math.PI * 2);
  ctx.fill();
}

type Drawer = (ctx: CanvasRenderingContext2D, w: number, h: number) => void;

function renderToImageData(w: number, h: number, draw: Drawer): ImageData {
  const canvas = document.createElement('canvas');
  const pixelW = w * DEVICE_SCALE;
  const pixelH = h * DEVICE_SCALE;
  canvas.width = pixelW;
  canvas.height = pixelH;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('2D canvas context unavailable');
  ctx.scale(DEVICE_SCALE, DEVICE_SCALE);
  draw(ctx, w, h);
  return ctx.getImageData(0, 0, pixelW, pixelH);
}

/**
 * Register every icon on a MapLibre instance. Safe to call more than once —
 * existing images are skipped rather than re-added.
 */
export function registerVehicleIcons(map: MapLibreMap): void {
  for (const type of TRAIN_TYPE_IDS) {
    const color = TRAIN_TYPE_PALETTE[type];
    const locoId = locoIconId(type);
    const carriageId = carriageIconId(type);
    const locoLeftId = locoIconIdLeft(type);
    const carriageLeftId = carriageIconIdLeft(type);
    if (!map.hasImage(locoId)) {
      try {
        const img = renderToImageData(72, 30, (ctx, w, h) =>
          drawLocomotive(ctx, w, h, color),
        );
        map.addImage(locoId, img, { pixelRatio: DEVICE_SCALE });
      } catch (err) {
        console.warn(`Failed to register ${locoId}`, err);
      }
    }
    if (!map.hasImage(locoLeftId)) {
      try {
        // Horizontally mirrored locomotive for left-facing (westward) trains.
        const img = renderToImageData(72, 30, (ctx, w, h) => {
          ctx.save();
          ctx.translate(w, 0);
          ctx.scale(-1, 1);
          drawLocomotive(ctx, w, h, color);
          ctx.restore();
        });
        map.addImage(locoLeftId, img, { pixelRatio: DEVICE_SCALE });
      } catch (err) {
        console.warn(`Failed to register ${locoLeftId}`, err);
      }
    }
    if (!map.hasImage(carriageId)) {
      try {
        const img = renderToImageData(54, 22, (ctx, w, h) =>
          drawCarriage(ctx, w, h, color),
        );
        map.addImage(carriageId, img, { pixelRatio: DEVICE_SCALE });
      } catch (err) {
        console.warn(`Failed to register ${carriageId}`, err);
      }
    }
    if (!map.hasImage(carriageLeftId)) {
      try {
        // Horizontally mirrored carriage for left-facing trains.
        const img = renderToImageData(54, 22, (ctx, w, h) => {
          ctx.save();
          ctx.translate(w, 0);
          ctx.scale(-1, 1);
          drawCarriage(ctx, w, h, color);
          ctx.restore();
        });
        map.addImage(carriageLeftId, img, { pixelRatio: DEVICE_SCALE });
      } catch (err) {
        console.warn(`Failed to register ${carriageLeftId}`, err);
      }
    }
  }

  if (!map.hasImage(HALO_ICON_ID)) {
    try {
      const img = renderToImageData(112, 112, drawHalo);
      map.addImage(HALO_ICON_ID, img, { pixelRatio: DEVICE_SCALE });
    } catch (err) {
      console.warn('Failed to register halo icon', err);
    }
  }
}

export function registerLiftGateFallback(map: MapLibreMap): void {
  if (map.hasImage(LIFT_GATE_ICON_ID)) return;

  try {
    const img = renderToImageData(24, 24, (ctx, w, h) => {
      ctx.strokeStyle = 'rgba(71, 85, 105, 0.96)';
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';

      ctx.lineWidth = 2.2;
      ctx.beginPath();
      ctx.moveTo(w * 0.29, h * 0.21);
      ctx.lineTo(w * 0.29, h * 0.79);
      ctx.stroke();

      ctx.beginPath();
      ctx.moveTo(w * 0.71, h * 0.21);
      ctx.lineTo(w * 0.71, h * 0.79);
      ctx.stroke();

      ctx.beginPath();
      ctx.moveTo(w * 0.29, h * 0.31);
      ctx.lineTo(w * 0.71, h * 0.31);
      ctx.stroke();

      ctx.strokeStyle = 'rgba(148, 163, 184, 0.9)';
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      ctx.moveTo(w * 0.2, h * 0.79);
      ctx.lineTo(w * 0.8, h * 0.79);
      ctx.stroke();
    });

    map.addImage(LIFT_GATE_ICON_ID, img, { pixelRatio: DEVICE_SCALE });
  } catch (err) {
    console.warn('Failed to register lift_gate icon', err);
  }
}

/**
 * Build the `match` expression MapLibre needs to pick the per-type icon from
 * a feature's `train_type` property. Used by `VehiclesLayer`.
 */
export function buildLocoMatchExpression(): unknown[] {
  const expr: unknown[] = ['match', ['get', 'train_type']];
  for (const type of TRAIN_TYPE_IDS) {
    if (type === 'default') continue;
    expr.push(type, locoIconId(type));
  }
  expr.push(locoIconId('default'));
  return expr;
}

export function buildLocoMatchExpressionLeft(): unknown[] {
  const expr: unknown[] = ['match', ['get', 'train_type']];
  for (const type of TRAIN_TYPE_IDS) {
    if (type === 'default') continue;
    expr.push(type, locoIconIdLeft(type));
  }
  expr.push(locoIconIdLeft('default'));
  return expr;
}

export function buildCarriageMatchExpression(): unknown[] {
  const expr: unknown[] = ['match', ['get', 'train_type']];
  for (const type of TRAIN_TYPE_IDS) {
    if (type === 'default') continue;
    expr.push(type, carriageIconId(type));
  }
  expr.push(carriageIconId('default'));
  return expr;
}

export function buildCarriageMatchExpressionLeft(): unknown[] {
  const expr: unknown[] = ['match', ['get', 'train_type']];
  for (const type of TRAIN_TYPE_IDS) {
    if (type === 'default') continue;
    expr.push(type, carriageIconIdLeft(type));
  }
  expr.push(carriageIconIdLeft('default'));
  return expr;
}
