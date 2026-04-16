import { Layer, Source } from 'react-map-gl/maplibre';

export default function VehiclesLayer() {
  return (
    <Source id="vehicles" type="geojson" data={{ type: 'FeatureCollection', features: [] }}>
      <Layer
        id="vehicles-symbol"
        type="circle"
        paint={{
          'circle-radius': ['case', ['==', ['get', 'body_type'], 'locomotive'], 6, 4],
          'circle-color': ['case', ['==', ['get', 'is_selected'], true], '#F59E0B', '#0EA5E9'],
          'circle-stroke-color': '#fff',
          'circle-stroke-width': 1,
        }}
      />
    </Source>
  );
}
