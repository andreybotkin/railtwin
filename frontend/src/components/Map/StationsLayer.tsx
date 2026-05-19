/**
 * Renders stations from a plain GeoJSON point source.
 *
 * Stations that never appear in a timetable are shown only at closer zoom and
 * with lower opacity, so the map stays readable at country scale.
 */

'use client';

import { useMemo } from 'react';
import { Layer, Source } from 'react-map-gl/maplibre';

import type { FeatureCollection, Feature, Point } from 'geojson';

import type { Station } from '@/types';

interface StationsLayerProps {
  stations: Station[] | null | undefined;
  selectedStationId: number | null;
}

interface StationProps {
  station_id: number;
  name: string;
  code: string;
  has_schedule: boolean;
  is_selected: boolean;
}

export const STATIONS_INTERACTIVE_LAYERS = [
  'stations-scheduled',
  'stations-unscheduled',
  'stations-selected-halo',
  'stations-selected',
  'stations-labels-scheduled',
  'stations-labels-unscheduled',
] as const;

function toFeatureCollection(
  stations: Station[],
  selectedStationId: number | null
): FeatureCollection<Point, StationProps> {
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
        has_schedule: Boolean(station.has_schedule),
        is_selected: station.id === selectedStationId,
      },
    }));
  return { type: 'FeatureCollection', features };
}

export default function StationsLayer({
  stations,
  selectedStationId,
}: StationsLayerProps) {
  const data = useMemo(
    () => toFeatureCollection(stations ?? [], selectedStationId),
    [selectedStationId, stations]
  );

  return (
    <Source id="stations" type="geojson" data={data}>
      <Layer
        id="stations-scheduled"
        type="circle"
        filter={['==', ['get', 'has_schedule'], true]}
        paint={{
          'circle-color': '#0F172A',
          'circle-stroke-color': '#FFFFFF',
          'circle-stroke-width': 1.8,
          'circle-radius': [
            'interpolate',
            ['linear'],
            ['zoom'],
            5.5,
            1.8,
            7,
            2.6,
            11,
            4.8,
            15,
            7,
          ],
          'circle-opacity': 0.96,
        }}
      />
      <Layer
        id="stations-unscheduled"
        type="circle"
        minzoom={10}
        filter={['!=', ['get', 'has_schedule'], true]}
        paint={{
          'circle-color': '#0F172A',
          'circle-stroke-color': '#FFFFFF',
          'circle-stroke-width': 1.6,
          'circle-radius': [
            'interpolate',
            ['linear'],
            ['zoom'],
            10,
            1.5,
            12,
            2.2,
            15,
            5,
          ],
          'circle-opacity': 0.34,
        }}
      />
      <Layer
        id="stations-selected-halo"
        type="circle"
        filter={['==', ['get', 'is_selected'], true]}
        paint={{
          'circle-color': 'rgba(245, 158, 11, 0.22)',
          'circle-stroke-color': '#F59E0B',
          'circle-stroke-width': 2,
          'circle-radius': [
            'interpolate',
            ['linear'],
            ['zoom'],
            7,
            9,
            11,
            12,
            15,
            16,
          ],
        }}
      />
      <Layer
        id="stations-selected"
        type="circle"
        filter={['==', ['get', 'is_selected'], true]}
        paint={{
          'circle-color': '#F59E0B',
          'circle-stroke-color': '#0F172A',
          'circle-stroke-width': 2,
          'circle-radius': [
            'interpolate',
            ['linear'],
            ['zoom'],
            7,
            4.5,
            11,
            6,
            15,
            8,
          ],
        }}
      />
      <Layer
        id="stations-labels-scheduled"
        type="symbol"
        filter={['==', ['get', 'has_schedule'], true]}
        minzoom={10}
        layout={{
          'text-field': ['get', 'name'],
          'text-size': 11.5,
          'text-offset': [0, 1.1],
          'text-anchor': 'top',
        }}
        paint={{
          'text-color': '#0F172A',
          'text-halo-color': '#FFFFFF',
          'text-halo-width': 1.6,
        }}
      />
      <Layer
        id="stations-labels-unscheduled"
        type="symbol"
        filter={['!=', ['get', 'has_schedule'], true]}
        minzoom={12}
        layout={{
          'text-field': ['get', 'name'],
          'text-size': 11.5,
          'text-offset': [0, 1.1],
          'text-anchor': 'top',
        }}
        paint={{
          'text-color': '#0F172A',
          'text-halo-color': '#FFFFFF',
          'text-halo-width': 1.6,
          'text-opacity': 0.6,
        }}
      />
    </Source>
  );
}
