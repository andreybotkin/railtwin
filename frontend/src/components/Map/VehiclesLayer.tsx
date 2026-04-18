/**
 * Modern vehicle rendering: SDF locomotive + carriage symbols.
 *
 * The single `vehicles` GeoJSON source is updated every rAF by
 * `useRafVehicleTicker`. Each feature carries its own `rotation` so MapLibre
 * can orient the symbol along the track, and its own `color` so we tint the
 * SDF silhouettes on a per-train basis without juggling N image variants.
 *
 * Layer stack (back → front):
 *   1. `vehicles-halo`       — pulsing amber halo behind the selected train.
 *   2. `vehicles-carriage`   — passenger coach silhouette, tinted by color.
 *   3. `vehicles-locomotive` — loco silhouette on top of the carriages.
 *   4. `vehicles-number`     — train number label at high zoom only.
 */

'use client';

import { Layer, Source } from 'react-map-gl/maplibre';

import { VEHICLE_SOURCE_ID } from '@/lib/hooks';
import {
  CARRIAGE_ICON_ID,
  HALO_ICON_ID,
  LOCO_ICON_ID,
} from '@/lib/vehicle-icons';

const EMPTY_FC = { type: 'FeatureCollection' as const, features: [] };

export default function VehiclesLayer() {
  return (
    <Source id={VEHICLE_SOURCE_ID} type="geojson" data={EMPTY_FC}>
      <Layer
        id="vehicles-halo"
        type="symbol"
        filter={['all', ['==', ['get', 'is_selected'], true], ['==', ['get', 'body_kind'], 'locomotive']]}
        layout={{
          'icon-image': HALO_ICON_ID,
          'icon-allow-overlap': true,
          'icon-ignore-placement': true,
          'icon-size': [
            'interpolate',
            ['linear'],
            ['zoom'],
            6, 0.35,
            11, 0.55,
            15, 0.9,
          ],
          'icon-anchor': 'center',
        }}
        paint={{
          'icon-opacity': [
            'interpolate',
            ['linear'],
            ['zoom'],
            6, 0.75,
            15, 0.95,
          ],
        }}
      />
      <Layer
        id="vehicles-carriage"
        type="symbol"
        filter={['==', ['get', 'body_kind'], 'carriage']}
        layout={{
          'icon-image': CARRIAGE_ICON_ID,
          'icon-rotate': ['get', 'rotation'],
          'icon-rotation-alignment': 'map',
          'icon-pitch-alignment': 'map',
          'icon-allow-overlap': true,
          'icon-ignore-placement': true,
          'icon-anchor': 'center',
          'icon-size': [
            'interpolate',
            ['linear'],
            ['zoom'],
            6, 0.18,
            9, 0.28,
            12, 0.5,
            15, 0.85,
          ],
        }}
        paint={{
          'icon-color': ['get', 'color'],
          'icon-halo-color': '#0F172A',
          'icon-halo-width': 0.6,
          'icon-opacity': 0.92,
        }}
      />
      <Layer
        id="vehicles-locomotive"
        type="symbol"
        filter={['==', ['get', 'body_kind'], 'locomotive']}
        layout={{
          'icon-image': LOCO_ICON_ID,
          'icon-rotate': ['get', 'rotation'],
          'icon-rotation-alignment': 'map',
          'icon-pitch-alignment': 'map',
          'icon-allow-overlap': true,
          'icon-ignore-placement': true,
          'icon-anchor': 'center',
          'icon-size': [
            'interpolate',
            ['linear'],
            ['zoom'],
            6, 0.22,
            9, 0.35,
            12, 0.6,
            15, 1.0,
          ],
        }}
        paint={{
          'icon-color': ['get', 'color'],
          'icon-halo-color': '#FFFFFF',
          'icon-halo-width': ['case', ['get', 'is_selected'], 1.5, 0.8],
          'icon-opacity': 1,
        }}
      />
      <Layer
        id="vehicles-number"
        type="symbol"
        minzoom={11}
        filter={['==', ['get', 'body_kind'], 'locomotive']}
        layout={{
          'text-field': ['get', 'train_number'],
          'text-size': [
            'interpolate',
            ['linear'],
            ['zoom'],
            11, 10,
            15, 13,
          ],
          'text-offset': [0, -1.6],
          'text-anchor': 'bottom',
          'text-allow-overlap': true,
          'text-font': ['Noto Sans Bold', 'Open Sans Bold', 'Arial Unicode MS Bold'],
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
