/**
 * Runtime-generated icons for locomotives and carriages.
 *
 * We register one pre-coloured RGBA image per (train-type × body-kind) and
 * pick the right one per feature using a `match` expression on `icon-image`.
 * This avoids the fuzzy/undersized edges we'd get from feeding non-SDF canvas
 * data to MapLibre's SDF loader while still giving every train type its own
 * brand colour.
 *
 * Icons are designed in a 64-wide frame, oriented **pointing east (+x)** so
 * the rotation degrees emitted by the trajectory interpolator can be fed
 * straight into `icon-rotate` (0° = east on the map).
 */

const DEVICE_SCALE = 2;

export type TrainTypeId =
  | 'special_express'
  | 'express'
  | 'rapid'
  | 'ordinary'
  | 'commuter'
  | 'default';

export const TRAIN_TYPE_PALETTE: Record<TrainTypeId, string> = {
  special_express: '#E53935',
  express: '#EF6C00',
  rapid: '#1E88E5',
  ordinary: '#43A047',
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

export function locoIconId(type: TrainTypeId): string {
  return `railtwin-loco-${type}`;
}

export function carriageIconId(type: TrainTypeId): string {
  return `railtwin-carriage-${type}`;
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

/**
 * Modern diesel locomotive silhouette, facing east.
 *
 * Two-tone body: a lighter top half uses the train colour; a darker bottom
 * strip + bogies add depth. A small windshield dot sits near the nose.
 */
function drawLocomotive(
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  color: string,
) {
  const dark = mix(color, '#000000', 0.45);
  const accent = mix(color, '#FFFFFF', 0.45);

  // Bogies — grey stubs underneath.
  ctx.fillStyle = '#1F2937';
  const bogieY = h * 0.72;
  const bogieH = h * 0.14;
  ctx.fillRect(w * 0.14, bogieY, w * 0.12, bogieH);
  ctx.fillRect(w * 0.58, bogieY, w * 0.12, bogieH);

  // Main body with a chiseled nose.
  const bodyTop = h * 0.22;
  const bodyBottom = h * 0.72;
  const noseTipX = w * 0.96;
  const noseBaseX = w * 0.82;
  const tailX = w * 0.08;
  const tailRadius = h * 0.1;
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.moveTo(tailX + tailRadius, bodyTop);
  ctx.lineTo(noseBaseX, bodyTop);
  ctx.lineTo(noseTipX, (bodyTop + bodyBottom) / 2);
  ctx.lineTo(noseBaseX, bodyBottom);
  ctx.lineTo(tailX + tailRadius, bodyBottom);
  ctx.quadraticCurveTo(tailX, bodyBottom, tailX, bodyBottom - tailRadius);
  ctx.lineTo(tailX, bodyTop + tailRadius);
  ctx.quadraticCurveTo(tailX, bodyTop, tailX + tailRadius, bodyTop);
  ctx.closePath();
  ctx.fill();

  // Dark roof strip.
  ctx.fillStyle = dark;
  ctx.beginPath();
  ctx.moveTo(tailX + tailRadius, bodyTop);
  ctx.lineTo(noseBaseX * 0.98, bodyTop);
  ctx.lineTo(noseBaseX * 0.98, bodyTop + h * 0.14);
  ctx.lineTo(tailX + tailRadius, bodyTop + h * 0.14);
  ctx.quadraticCurveTo(
    tailX,
    bodyTop + h * 0.14,
    tailX,
    bodyTop + h * 0.14 - tailRadius,
  );
  ctx.lineTo(tailX, bodyTop + tailRadius);
  ctx.quadraticCurveTo(tailX, bodyTop, tailX + tailRadius, bodyTop);
  ctx.closePath();
  ctx.fill();

  // Windshield highlight near the nose.
  ctx.fillStyle = accent;
  ctx.beginPath();
  ctx.moveTo(w * 0.74, bodyTop + h * 0.18);
  ctx.lineTo(w * 0.82, bodyTop + h * 0.18);
  ctx.lineTo(w * 0.88, bodyTop + h * 0.32);
  ctx.lineTo(w * 0.74, bodyTop + h * 0.32);
  ctx.closePath();
  ctx.fill();

  // White outline around the body for contrast on dark basemaps.
  ctx.strokeStyle = 'rgba(255,255,255,0.9)';
  ctx.lineWidth = 1.2;
  ctx.beginPath();
  ctx.moveTo(tailX + tailRadius, bodyTop);
  ctx.lineTo(noseBaseX, bodyTop);
  ctx.lineTo(noseTipX, (bodyTop + bodyBottom) / 2);
  ctx.lineTo(noseBaseX, bodyBottom);
  ctx.lineTo(tailX + tailRadius, bodyBottom);
  ctx.quadraticCurveTo(tailX, bodyBottom, tailX, bodyBottom - tailRadius);
  ctx.lineTo(tailX, bodyTop + tailRadius);
  ctx.quadraticCurveTo(tailX, bodyTop, tailX + tailRadius, bodyTop);
  ctx.closePath();
  ctx.stroke();
}

/**
 * Passenger carriage silhouette: rounded body, dark windows, two bogies.
 */
function drawCarriage(
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  color: string,
) {
  const dark = mix(color, '#000000', 0.5);

  // Bogies.
  ctx.fillStyle = '#1F2937';
  const bogieY = h * 0.72;
  const bogieH = h * 0.14;
  ctx.fillRect(w * 0.16, bogieY, w * 0.12, bogieH);
  ctx.fillRect(w * 0.72, bogieY, w * 0.12, bogieH);

  // Body.
  const bodyTop = h * 0.3;
  const bodyBottom = h * 0.72;
  const radius = h * 0.15;
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.moveTo(w * 0.06 + radius, bodyTop);
  ctx.lineTo(w * 0.94 - radius, bodyTop);
  ctx.quadraticCurveTo(w * 0.94, bodyTop, w * 0.94, bodyTop + radius);
  ctx.lineTo(w * 0.94, bodyBottom - radius);
  ctx.quadraticCurveTo(w * 0.94, bodyBottom, w * 0.94 - radius, bodyBottom);
  ctx.lineTo(w * 0.06 + radius, bodyBottom);
  ctx.quadraticCurveTo(w * 0.06, bodyBottom, w * 0.06, bodyBottom - radius);
  ctx.lineTo(w * 0.06, bodyTop + radius);
  ctx.quadraticCurveTo(w * 0.06, bodyTop, w * 0.06 + radius, bodyTop);
  ctx.closePath();
  ctx.fill();

  // Window strip.
  ctx.fillStyle = dark;
  const winTop = bodyTop + h * 0.1;
  const winBottom = bodyTop + h * 0.3;
  ctx.fillRect(w * 0.12, winTop, w * 0.76, winBottom - winTop);

  // White outline.
  ctx.strokeStyle = 'rgba(255,255,255,0.85)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(w * 0.06 + radius, bodyTop);
  ctx.lineTo(w * 0.94 - radius, bodyTop);
  ctx.quadraticCurveTo(w * 0.94, bodyTop, w * 0.94, bodyTop + radius);
  ctx.lineTo(w * 0.94, bodyBottom - radius);
  ctx.quadraticCurveTo(w * 0.94, bodyBottom, w * 0.94 - radius, bodyBottom);
  ctx.lineTo(w * 0.06 + radius, bodyBottom);
  ctx.quadraticCurveTo(w * 0.06, bodyBottom, w * 0.06, bodyBottom - radius);
  ctx.lineTo(w * 0.06, bodyTop + radius);
  ctx.quadraticCurveTo(w * 0.06, bodyTop, w * 0.06 + radius, bodyTop);
  ctx.closePath();
  ctx.stroke();
}

/**
 * Soft amber glow for the selected train. Non-SDF so the radial gradient
 * ships its own colour.
 */
function drawHalo(ctx: CanvasRenderingContext2D, w: number, h: number) {
  const cx = w / 2;
  const cy = h / 2;
  const radius = Math.min(w, h) / 2;
  const gradient = ctx.createRadialGradient(cx, cy, radius * 0.2, cx, cy, radius);
  gradient.addColorStop(0, 'rgba(255, 234, 145, 0.95)');
  gradient.addColorStop(0.55, 'rgba(245, 158, 11, 0.5)');
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
export function registerVehicleIcons(map: maplibregl.Map): void {
  for (const type of TRAIN_TYPE_IDS) {
    const color = TRAIN_TYPE_PALETTE[type];
    const locoId = locoIconId(type);
    const carriageId = carriageIconId(type);
    if (!map.hasImage(locoId)) {
      try {
        const img = renderToImageData(64, 28, (ctx, w, h) =>
          drawLocomotive(ctx, w, h, color),
        );
        map.addImage(locoId, img, { pixelRatio: DEVICE_SCALE });
      } catch (err) {
        console.warn(`Failed to register ${locoId}`, err);
      }
    }
    if (!map.hasImage(carriageId)) {
      try {
        const img = renderToImageData(48, 20, (ctx, w, h) =>
          drawCarriage(ctx, w, h, color),
        );
        map.addImage(carriageId, img, { pixelRatio: DEVICE_SCALE });
      } catch (err) {
        console.warn(`Failed to register ${carriageId}`, err);
      }
    }
  }

  if (!map.hasImage(HALO_ICON_ID)) {
    try {
      const img = renderToImageData(96, 96, drawHalo);
      map.addImage(HALO_ICON_ID, img, { pixelRatio: DEVICE_SCALE });
    } catch (err) {
      console.warn('Failed to register halo icon', err);
    }
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

export function buildCarriageMatchExpression(): unknown[] {
  const expr: unknown[] = ['match', ['get', 'train_type']];
  for (const type of TRAIN_TYPE_IDS) {
    if (type === 'default') continue;
    expr.push(type, carriageIconId(type));
  }
  expr.push(carriageIconId('default'));
  return expr;
}
