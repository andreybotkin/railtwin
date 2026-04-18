/**
 * Runtime-generated SVG icons for locomotives and carriages.
 *
 * We register two **SDF** (signed distance field) silhouettes with MapLibre at
 * map-load time — one for locomotives, one for carriages. SDF images can be
 * tinted per-feature via the `icon-color` property, so a single icon handles
 * every train-type colour without us shipping N colour variants.
 *
 * The silhouette itself is drawn white-on-transparent onto an offscreen
 * canvas: MapLibre's SDF loader treats every pixel as "inside" (white) or
 * "outside" (transparent) and uses the alpha channel to build the distance
 * field. For crisp edges at all zooms we render the source SVG 2× the logical
 * size, then MapLibre shrinks it with anti-aliasing.
 *
 * Icons are designed in a 64-wide frame, oriented **pointing east (+x)** so
 * that the `rotation` degrees emitted by the trajectory interpolator can be
 * fed straight into `icon-rotate` (0° = east on the map).
 */

export const LOCO_ICON_ID = 'railtwin-loco';
export const CARRIAGE_ICON_ID = 'railtwin-carriage';
export const HALO_ICON_ID = 'railtwin-halo';

const DEVICE_SCALE = 2;

interface IconDef {
  id: string;
  width: number;
  height: number;
  sdf: boolean;
  draw: (ctx: CanvasRenderingContext2D, w: number, h: number) => void;
}

/**
 * Stylised modern diesel locomotive body, nose facing east (right).
 *
 * The silhouette is a rounded rectangle with a chiseled nose, a canopy
 * window, a pantograph-style marker on the roof and two visible bogies.
 * It must stay as a single filled white shape for the SDF loader to read
 * the alpha as a distance field.
 */
function drawLocomotive(ctx: CanvasRenderingContext2D, w: number, h: number) {
  ctx.save();
  ctx.fillStyle = '#FFFFFF';

  // Main body — chiseled nose on the east side.
  const body = new Path2D();
  const bodyBottom = h * 0.22;
  const bodyTop = h * 0.72;
  const noseTipX = w * 0.96;
  const noseBaseX = w * 0.82;
  const tailX = w * 0.08;
  const tailRadius = h * 0.08;
  body.moveTo(tailX + tailRadius, bodyBottom);
  body.lineTo(noseBaseX, bodyBottom);
  body.lineTo(noseTipX, (bodyBottom + bodyTop) / 2);
  body.lineTo(noseBaseX, bodyTop);
  body.lineTo(tailX + tailRadius, bodyTop);
  body.quadraticCurveTo(tailX, bodyTop, tailX, bodyTop - tailRadius);
  body.lineTo(tailX, bodyBottom + tailRadius);
  body.quadraticCurveTo(tailX, bodyBottom, tailX + tailRadius, bodyBottom);
  body.closePath();
  ctx.fill(body);

  // Bogies — two stubby rectangles hanging below the body.
  const bogieY = bodyTop;
  const bogieH = h * 0.12;
  const bogieW = w * 0.12;
  ctx.fillRect(w * 0.15, bogieY, bogieW, bogieH);
  ctx.fillRect(w * 0.58, bogieY, bogieW, bogieH);

  // Roof pantograph marker — a small trapezoid above the body.
  ctx.beginPath();
  ctx.moveTo(w * 0.35, bodyBottom);
  ctx.lineTo(w * 0.5, bodyBottom);
  ctx.lineTo(w * 0.46, bodyBottom - h * 0.12);
  ctx.lineTo(w * 0.39, bodyBottom - h * 0.12);
  ctx.closePath();
  ctx.fill();

  ctx.restore();
}

/**
 * Carriage body — a rounded rectangle with two bogies underneath.
 * Smaller vertical footprint than the loco so the consist reads as "loco in
 * front, coaches behind" at a glance.
 */
function drawCarriage(ctx: CanvasRenderingContext2D, w: number, h: number) {
  ctx.save();
  ctx.fillStyle = '#FFFFFF';

  const bodyTop = h * 0.3;
  const bodyBottom = h * 0.7;
  const radius = h * 0.12;

  ctx.beginPath();
  ctx.moveTo(w * 0.05 + radius, bodyTop);
  ctx.lineTo(w * 0.95 - radius, bodyTop);
  ctx.quadraticCurveTo(w * 0.95, bodyTop, w * 0.95, bodyTop + radius);
  ctx.lineTo(w * 0.95, bodyBottom - radius);
  ctx.quadraticCurveTo(w * 0.95, bodyBottom, w * 0.95 - radius, bodyBottom);
  ctx.lineTo(w * 0.05 + radius, bodyBottom);
  ctx.quadraticCurveTo(w * 0.05, bodyBottom, w * 0.05, bodyBottom - radius);
  ctx.lineTo(w * 0.05, bodyTop + radius);
  ctx.quadraticCurveTo(w * 0.05, bodyTop, w * 0.05 + radius, bodyTop);
  ctx.closePath();
  ctx.fill();

  const bogieY = bodyBottom;
  const bogieH = h * 0.15;
  ctx.fillRect(w * 0.14, bogieY, w * 0.14, bogieH);
  ctx.fillRect(w * 0.72, bogieY, w * 0.14, bogieH);

  ctx.restore();
}

/**
 * Halo for the selected train — a soft radial gradient rendered into a
 * non-SDF image so it can display its own gradient colour without tinting.
 */
function drawHalo(ctx: CanvasRenderingContext2D, w: number, h: number) {
  const cx = w / 2;
  const cy = h / 2;
  const radius = Math.min(w, h) / 2;
  const gradient = ctx.createRadialGradient(cx, cy, radius * 0.2, cx, cy, radius);
  gradient.addColorStop(0, 'rgba(255, 234, 145, 0.9)');
  gradient.addColorStop(0.55, 'rgba(245, 158, 11, 0.35)');
  gradient.addColorStop(1, 'rgba(245, 158, 11, 0)');
  ctx.fillStyle = gradient;
  ctx.beginPath();
  ctx.arc(cx, cy, radius, 0, Math.PI * 2);
  ctx.fill();
}

const ICONS: IconDef[] = [
  { id: LOCO_ICON_ID, width: 64, height: 28, sdf: true, draw: drawLocomotive },
  { id: CARRIAGE_ICON_ID, width: 48, height: 20, sdf: true, draw: drawCarriage },
  { id: HALO_ICON_ID, width: 96, height: 96, sdf: false, draw: drawHalo },
];

function renderIcon(def: IconDef): ImageData {
  const canvas = document.createElement('canvas');
  const pixelW = def.width * DEVICE_SCALE;
  const pixelH = def.height * DEVICE_SCALE;
  canvas.width = pixelW;
  canvas.height = pixelH;

  const ctx = canvas.getContext('2d');
  if (!ctx) {
    throw new Error('2D canvas context unavailable — cannot build vehicle icons');
  }
  ctx.scale(DEVICE_SCALE, DEVICE_SCALE);
  def.draw(ctx, def.width, def.height);
  return ctx.getImageData(0, 0, pixelW, pixelH);
}

/**
 * Register every icon on a MapLibre instance. Safe to call more than once —
 * existing images are skipped rather than re-added.
 */
export function registerVehicleIcons(map: maplibregl.Map): void {
  for (const def of ICONS) {
    if (map.hasImage(def.id)) continue;
    try {
      const imageData = renderIcon(def);
      map.addImage(def.id, imageData, {
        sdf: def.sdf,
        pixelRatio: DEVICE_SCALE,
      });
    } catch (err) {
      // Non-fatal: the layer gracefully degrades to no icons.
      console.warn(`Failed to register icon ${def.id}`, err);
    }
  }
}
