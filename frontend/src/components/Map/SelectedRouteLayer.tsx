/**
 * Highlights the polyline the currently selected train rides.
 *
 * Uses the trajectory's `route_coords` (the same authoritative polyline the
 * consist is laid out on) so the highlight never drifts from the rails. Two
 * layers: a white casing for contrast against the coloured tracks, and an
 * amber accent line on top.
 */

'use client';

import { useMemo } from 'react';
import type { Feature, FeatureCollection, LineString } from 'geojson';
import { Layer, Source } from 'react-map-gl/maplibre';

import { useRailwayStore } from '@/lib/stores/railway-store';

const EMPTY_FC: FeatureCollection<LineString> = {
  type: 'FeatureCollection',
  features: [],
};

export default function SelectedRouteLayer() {
  const selectedTrainId = useRailwayStore((s) => s.selectedTrainId);
  const routeCoords = useRailwayStore((s) =>
    selectedTrainId !== null
      ? s.trajectories.get(selectedTrainId)?.route_coords ?? null
      : null,
  );

  const data = useMemo<FeatureCollection<LineString>>(() => {
    if (!routeCoords || routeCoords.length < 2) return EMPTY_FC;
    const feature: Feature<LineString> = {
      type: 'Feature',
      geometry: {
        type: 'LineString',
        coordinates: routeCoords.map(([lon, lat]) => [lon, lat]),
      },
      properties: {},
    };
    return { type: 'FeatureCollection', features: [feature] };
  }, [routeCoords]);

  return (
    <Source id="selected-route" type="geojson" data={data}>
      <Layer
        id="selected-route-casing"
        type="line"
        paint={{
          'line-color': '#FFFFFF',
          'line-width': [
            'interpolate',
            ['linear'],
            ['zoom'],
            5,
            3,
            10,
            7,
            14,
            11,
          ],
          'line-opacity': 0.9,
        }}
        layout={{ 'line-join': 'round', 'line-cap': 'round' }}
      />
      <Layer
        id="selected-route-line"
        type="line"
        paint={{
          'line-color': '#F59E0B',
          'line-width': [
            'interpolate',
            ['linear'],
            ['zoom'],
            5,
            1.5,
            10,
            4,
            14,
            7,
          ],
          'line-opacity': 0.95,
        }}
        layout={{ 'line-join': 'round', 'line-cap': 'round' }}
      />
    </Source>
  );
}
