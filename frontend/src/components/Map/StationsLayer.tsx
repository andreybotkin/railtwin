/**
 * Renders stations as a clustered MapLibre symbol source. Three layers:
 *
 *  - cluster bubble   → visible at low zoom when many stations collapse.
 *  - cluster count    → numeric label on the bubble.
 *  - unclustered dot  → individual station at high zoom.
 */

'use client';

import { useMemo } from 'react';
import { Layer, Source } from 'react-map-gl/maplibre';

import type { FeatureCollection, Feature, Point } from 'geojson';

import type { Station } from '@/types';

interface StationsLayerProps {
  stations: Station[];
}

interface StationProps {
  station_id: number;
  name: string;
  code: string;
}

function toFeatureCollection(stations: Station[]): FeatureCollection<Point, StationProps> {
  const features: Feature<Point, StationProps>[] = stations
    .filter((station) => station.location?.coordinates?.length === 2)
    .map((station) => ({
      type: 'Feature',
      geometry: {
        type: 'Point',
        coordinates: station.location.coordinates,
      },
      properties: {
        station_id: station.id,
        name: station.name,
        code: station.code,
      },
    }));
  return { type: 'FeatureCollection', features };
}

export default function StationsLayer({ stations }: StationsLayerProps) {
  const data = useMemo(() => toFeatureCollection(stations), [stations]);

  return (
    <Source
      id="stations"
      type="geojson"
      data={data}
      cluster
      clusterMaxZoom={10}
      clusterRadius={40}
    >
      <Layer
        id="stations-clusters"
        type="circle"
        filter={['has', 'point_count']}
        paint={{
          'circle-color': '#1F2937',
          'circle-opacity': 0.85,
          'circle-radius': [
            'step', ['get', 'point_count'],
            14, 10,
            18, 50,
            24,
          ],
          'circle-stroke-color': '#FFFFFF',
          'circle-stroke-width': 2,
        }}
      />
      <Layer
        id="stations-cluster-count"
        type="symbol"
        filter={['has', 'point_count']}
        layout={{
          'text-field': ['get', 'point_count_abbreviated'],
          'text-size': 12,
          'text-allow-overlap': true,
        }}
        paint={{ 'text-color': '#FFFFFF' }}
      />
      <Layer
        id="stations-unclustered"
        type="circle"
        filter={['!', ['has', 'point_count']]}
        paint={{
          'circle-color': '#FFFFFF',
          'circle-stroke-color': '#111827',
          'circle-stroke-width': 2,
          'circle-radius': [
            'interpolate', ['linear'], ['zoom'],
            7, 2.5,
            11, 4,
            15, 6,
          ],
        }}
      />
      <Layer
        id="stations-labels"
        type="symbol"
        minzoom={11}
        filter={['!', ['has', 'point_count']]}
        layout={{
          'text-field': ['get', 'name'],
          'text-size': 11,
          'text-offset': [0, 1.1],
          'text-anchor': 'top',
          'text-optional': true,
        }}
        paint={{
          'text-color': '#111827',
          'text-halo-color': '#FFFFFF',
          'text-halo-width': 1.2,
        }}
      />
    </Source>
  );
}
