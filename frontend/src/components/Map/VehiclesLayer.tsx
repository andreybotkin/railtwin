/**
 * Modern vehicle rendering: per-train-type locomotive + carriage bitmaps.
 *
 * `vehicle-icons.ts` registers one bitmap per (train-type × body-kind) on
 * map load; a `match` expression on `icon-image` picks the right one per
 * feature. Bitmaps already embed the brand colour, so we avoid the SDF
 * fallback edge artifacts and rotate them by converting the north-based
 * bearing to the east-facing bitmap frame in `icon-rotate`.
 *
 * Layer stack (back → front):
 *   1. `vehicles-halo`       — amber halo behind the selected locomotive.
 *   2. `vehicles-carriage`   — passenger coach bitmap per train type.
 *   3. `vehicles-locomotive` — loco bitmap on top of the carriages.
 *   4. `vehicles-number`     — train number label at high zoom.
 */

'use client';

import { Layer, Source } from 'react-map-gl/maplibre';
import type { DataDrivenPropertyValueSpecification } from 'maplibre-gl';

import { VEHICLE_SOURCE_ID } from '@/lib/hooks';
import {
  HALO_ICON_ID,
  buildCarriageMatchExpression,
  buildCarriageMatchExpressionLeft,
  buildLocoMatchExpression,
  buildLocoMatchExpressionLeft,
} from '@/lib/vehicle-icons';

const EMPTY_FC = { type: 'FeatureCollection' as const, features: [] };

// Right-facing icon expressions (eastward baseline, bearing ∈ [0°, 180°)).
const LOCO_ICON_EXPR = buildLocoMatchExpression() as
  unknown as DataDrivenPropertyValueSpecification<string>;
const CARRIAGE_ICON_EXPR = buildCarriageMatchExpression() as
  unknown as DataDrivenPropertyValueSpecification<string>;

// Left-facing icon expressions (westward baseline, bearing ∈ [180°, 360°)).
const LOCO_ICON_LEFT_EXPR = buildLocoMatchExpressionLeft() as
  unknown as DataDrivenPropertyValueSpecification<string>;
const CARRIAGE_ICON_LEFT_EXPR = buildCarriageMatchExpressionLeft() as
  unknown as DataDrivenPropertyValueSpecification<string>;

/**
 * MapLibre `case` expression that picks the left or right icon variant based
 * on the `facing` property. The inner `match` expression resolves the
 * per-train-type icon id, keeping the two concerns separate.
 */
function directedIconExpr(
  rightExpr: DataDrivenPropertyValueSpecification<string>,
  leftExpr: DataDrivenPropertyValueSpecification<string>,
): DataDrivenPropertyValueSpecification<string> {
  return [
    'case',
    ['==', ['get', 'facing'], 'left'],
    leftExpr as unknown,
    rightExpr as unknown,
  ] as unknown as DataDrivenPropertyValueSpecification<string>;
}

/**
 * `icon-rotate` that accounts for the icon baseline direction:
 *   right-facing icons: rotate = bearing - 90  (east baseline)
 *   left-facing icons:  rotate = bearing - 270 (west baseline)
 * Both formulas keep `icon-rotate` in [-90°, 90°] for their respective
 * hemispheres, which ensures bogies always appear at the map-ground side.
 */
const DIRECTED_ROTATION_EXPR = [
  'case',
  ['==', ['get', 'facing'], 'left'],
  ['-', ['coalesce', ['get', 'rotation'], 0], 270],
  ['-', ['coalesce', ['get', 'rotation'], 0], 90],
];

export default function VehiclesLayer() {
  return (
    <Source id={VEHICLE_SOURCE_ID} type="geojson" data={EMPTY_FC}>
      <Layer
        id="vehicles-halo"
        type="symbol"
        filter={[
          'all',
          ['==', ['get', 'is_selected'], true],
          ['==', ['get', 'body_kind'], 'locomotive'],
        ]}
        layout={{
          'icon-image': HALO_ICON_ID,
          'icon-allow-overlap': true,
          'icon-ignore-placement': true,
          'icon-size': [
            'interpolate',
            ['linear'],
            ['zoom'],
            6, 0.4,
            11, 0.6,
            15, 1.0,
          ],
          'icon-anchor': 'center',
        }}
        paint={{
          'icon-opacity': [
            'interpolate',
            ['linear'],
            ['zoom'],
            6, 0.7,
            15, 0.95,
          ],
        }}
      />
      <Layer
        id="vehicles-carriage"
        type="symbol"
        filter={['==', ['get', 'body_kind'], 'carriage']}
        layout={{
          'icon-image': directedIconExpr(CARRIAGE_ICON_EXPR, CARRIAGE_ICON_LEFT_EXPR),
          'icon-rotate': DIRECTED_ROTATION_EXPR as DataDrivenPropertyValueSpecification<number>,
          'icon-rotation-alignment': 'map',
          'icon-pitch-alignment': 'map',
          'icon-allow-overlap': true,
          'icon-ignore-placement': true,
          'icon-anchor': 'center',
          'icon-size': [
            'interpolate',
            ['linear'],
            ['zoom'],
            6, 0.28,
            9, 0.42,
            12, 0.7,
            15, 1.1,
          ],
        }}
        paint={{
          'icon-opacity': 0.95,
        }}
      />
      <Layer
        id="vehicles-locomotive"
        type="symbol"
        filter={['==', ['get', 'body_kind'], 'locomotive']}
        layout={{
          'icon-image': directedIconExpr(LOCO_ICON_EXPR, LOCO_ICON_LEFT_EXPR),
          'icon-rotate': DIRECTED_ROTATION_EXPR as DataDrivenPropertyValueSpecification<number>,
          'icon-rotation-alignment': 'map',
          'icon-pitch-alignment': 'map',
          'icon-allow-overlap': true,
          'icon-ignore-placement': true,
          'icon-anchor': 'center',
          'icon-size': [
            'interpolate',
            ['linear'],
            ['zoom'],
            6, 0.32,
            9, 0.5,
            12, 0.8,
            15, 1.25,
          ],
        }}
      />
      <Layer
        id="vehicles-number"
        type="symbol"
        minzoom={10}
        filter={['==', ['get', 'body_kind'], 'locomotive']}
        layout={{
          'text-field': ['concat', '#', ['get', 'train_number']],
          'text-size': [
            'interpolate',
            ['linear'],
            ['zoom'],
            10, 10,
            15, 13,
          ],
          'text-offset': [0, -1.6],
          'text-anchor': 'bottom',
          'text-allow-overlap': true,
        }}
        paint={{
          'text-color': '#0F172A',
          'text-halo-color': '#FFFFFF',
          'text-halo-width': 1.6,
        }}
      />
    </Source>
  );
}
