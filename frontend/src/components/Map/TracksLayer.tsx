import { Layer, Source } from 'react-map-gl/maplibre';

export default function TracksLayer({ edges }: { edges: Record<string, unknown> }) {
  return (
    <Source id="tracks" type="geojson" data={edges as never}>
      <Layer
        id="tracks-line"
        type="line"
        paint={{
          'line-color': [
            'match',
            ['get', 'route_type'],
            'northern',
            '#C62828',
            'northeastern',
            '#1565C0',
            'southern',
            '#2E7D32',
            'eastern',
            '#6A1B9A',
            '#546E7A',
          ],
          'line-width': 2.5,
        }}
      />
    </Source>
  );
}
