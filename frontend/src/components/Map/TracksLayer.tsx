/**
 * Renders the railway track network as a MapLibre line-layer coloured by
 * `route_type`. The topology snapshot comes from `/api/v1/map/topology` and
 * is already a valid FeatureCollection — we hand it straight to a GeoJSON
 * source.
 */

'use client';

import { Layer, Source } from 'react-map-gl/maplibre';

import type { NetworkEdgeCollection } from '@/types';

import {
  DEFAULT_ROUTE_COLOR,
  ROUTE_COLORS,
} from './map-style';

interface TracksLayerProps {
  edges: NetworkEdgeCollection | null | undefined;
}

const EMPTY_EDGES: NetworkEdgeCollection = {
  type: 'FeatureCollection',
  features: [],
};

const colorMatch = [
  'match',
  ['get', 'route_type'],
  'northern', ROUTE_COLORS.northern,
  'northeastern', ROUTE_COLORS.northeastern,
  'southern', ROUTE_COLORS.southern,
  'eastern', ROUTE_COLORS.eastern,
  DEFAULT_ROUTE_COLOR,
] as const;

export default function TracksLayer({ edges }: TracksLayerProps) {
  return (
    <Source id="tracks" type="geojson" data={edges ?? EMPTY_EDGES}>
      <Layer
        id="tracks-casing"
        type="line"
        paint={{
          'line-color': '#FFFFFF',
          'line-width': [
            'interpolate', ['linear'], ['zoom'],
            5, 1.5,
            10, 4,
            14, 7,
          ],
          'line-opacity': 0.85,
        }}
        layout={{ 'line-join': 'round', 'line-cap': 'round' }}
      />
      <Layer
        id="tracks-line"
        type="line"
        paint={{
          'line-color': colorMatch as unknown as string,
          'line-width': [
            'interpolate', ['linear'], ['zoom'],
            5, 0.6,
            10, 2,
            14, 4,
          ],
        }}
        layout={{ 'line-join': 'round', 'line-cap': 'round' }}
      />
    </Source>
  );
}
