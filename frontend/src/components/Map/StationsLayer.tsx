import { Layer, Source } from 'react-map-gl/maplibre';

export default function StationsLayer({ stations }: { stations: Record<string, unknown>[] }) {
  return (
    <Source
      id="stations"
      type="geojson"
      cluster
      clusterRadius={40}
      data={{
        type: 'FeatureCollection',
        features: stations.map((station) => ({
          type: 'Feature',
          geometry: (station.location ?? { type: 'Point', coordinates: [0, 0] }) as never,
          properties: station,
        })),
      }}
    >
      <Layer id="station-clusters" type="circle" filter={['has', 'point_count']} paint={{ 'circle-color': '#1E293B', 'circle-radius': 14 }} />
      <Layer id="station-points" type="circle" filter={['!', ['has', 'point_count']]} paint={{ 'circle-color': '#ffffff', 'circle-radius': 3, 'circle-stroke-width': 1, 'circle-stroke-color': '#0f172a' }} />
    </Source>
  );
}
