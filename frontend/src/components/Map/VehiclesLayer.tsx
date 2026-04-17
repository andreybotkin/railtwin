/**
 * Vehicle source + circle layers.
 *
 * The source is deliberately empty at mount time — the rAF ticker
 * (`useRafVehicleTicker`) swaps its data each frame via `source.setData`. That
 * keeps the number of React renders constant regardless of trajectory churn.
 *
 * Two layers share the source:
 *   - `vehicles-carriage`  : small dot for each wagon, shown behind the loco.
 *   - `vehicles-locomotive`: bigger, coloured dot at the head of the train.
 */

'use client';

import { Layer, Source } from 'react-map-gl/maplibre';

import { VEHICLE_SOURCE_ID } from '@/lib/hooks';

const EMPTY_FC = { type: 'FeatureCollection' as const, features: [] };

export default function VehiclesLayer() {
  return (
    <Source id={VEHICLE_SOURCE_ID} type="geojson" data={EMPTY_FC}>
      <Layer
        id="vehicles-carriage"
        type="circle"
        filter={['==', ['get', 'body_kind'], 'carriage']}
        paint={{
          'circle-color': ['get', 'color'],
          'circle-opacity': 0.85,
          'circle-radius': [
            'interpolate', ['linear'], ['zoom'],
            6, 2,
            11, 4,
            15, 7,
          ],
          'circle-stroke-color': '#111827',
          'circle-stroke-width': [
            'case', ['get', 'is_selected'], 2, 0.5,
          ],
        }}
      />
      <Layer
        id="vehicles-locomotive"
        type="circle"
        filter={['==', ['get', 'body_kind'], 'locomotive']}
        paint={{
          'circle-color': ['get', 'color'],
          'circle-radius': [
            'interpolate', ['linear'], ['zoom'],
            6, 4,
            11, 7,
            15, 11,
          ],
          'circle-stroke-color': '#FFFFFF',
          'circle-stroke-width': [
            'case', ['get', 'is_selected'], 3, 1.5,
          ],
        }}
      />
      <Layer
        id="vehicles-number"
        type="symbol"
        minzoom={11}
        filter={['==', ['get', 'body_kind'], 'locomotive']}
        layout={{
          'text-field': ['get', 'train_number'],
          'text-size': 11,
          'text-offset': [0, -1.4],
          'text-anchor': 'bottom',
          'text-allow-overlap': true,
        }}
        paint={{
          'text-color': '#0F172A',
          'text-halo-color': '#FFFFFF',
          'text-halo-width': 1.4,
        }}
      />
    </Source>
  );
}
