/**
 * Map content component with Leaflet integration.
 *
 * Best practices adopted from geops/trafimage-maps & geops/mobility-toolbox-js:
 * - Dark/light tile switching (CartoDB Voyager / Dark Matter)
 * - Station clustering via MarkerClusterGroup at low zoom
 * - BBOX filtering: send visible bounds to gateway WS for server-side filtering
 * - Map controls: scale bar, fullscreen, geolocation
 * - Permalink: sync map center/zoom/selectedTrain with URL query params
 * - Route highlighting when a train is selected
 * - Canvas-based rendering for 1000+ trains (mobility-toolbox-js RealtimeEngine)
 * - Topic-based architecture: switchable map themes (trafimage-maps)
 * - Generalization by zoom: adaptive detail levels (mobility-toolbox-js motsByZoom)
 * - Layer tree UI: toggleable category layers (trafimage LayerTree)
 */

'use client';

import { useEffect, useMemo, useCallback } from 'react';
import {
  MapContainer,
  TileLayer,
  Polyline,
  Popup,
  ScaleControl,
  useMap,
  useMapEvents,
} from 'react-leaflet';
import MarkerClusterGroup from 'react-leaflet-cluster';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { FullScreen as LeafletFullScreen } from 'leaflet.fullscreen';
import 'leaflet.fullscreen/dist/Control.FullScreen.css';

import { useRoutes, useStations, useTrainTrajectories, useNetworkEdges } from '@/lib/hooks';
import { getRouteColor } from '@/lib/utils';
import { cn } from '@/lib/utils';
import { getTrajectoryClient } from '@/lib/websocket';
import { buildPositionFromTrajectory } from '@/lib/trajectory-interpolation';
import { useMapTopicStore } from '@/lib/stores/map-topic-store';
import CanvasTrainLayer from './CanvasTrainLayer';
import TrainMarker from './TrainMarker';
import StationMarker from './StationMarker';
import LayerTree from './LayerTree';

// Fix Leaflet default icon issue in Next.js
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
});

// Thailand center coordinates
const THAILAND_CENTER: [number, number] = [15.87, 100.9925];
const INITIAL_ZOOM = 6;

interface MapContentProps {
  className?: string;
  selectedTrainId?: number | null;
  onTrainSelect?: (id: number | null) => void;
}

/**
 * Read permalink state from URL query params.
 */
function readPermalink(): { lat?: number; lng?: number; zoom?: number; train?: number } {
  if (typeof window === 'undefined') return {};
  const params = new URLSearchParams(window.location.search);
  const lat = params.get('lat');
  const lng = params.get('lng');
  const zoom = params.get('z');
  const train = params.get('train');
  return {
    lat: lat ? parseFloat(lat) : undefined,
    lng: lng ? parseFloat(lng) : undefined,
    zoom: zoom ? parseInt(zoom, 10) : undefined,
    train: train ? parseInt(train, 10) : undefined,
  };
}

/**
 * Controller component: map resize, permalink, BBOX reporting, fullscreen control,
 * zoom-based generalization updates.
 */
function MapController({ onBBoxChange }: { onBBoxChange: (bbox: string) => void }) {
  const map = useMap();
  const setZoom = useMapTopicStore((s) => s.setZoom);

  // Invalidate map size on resize
  useEffect(() => {
    const invalidateMap = () => map.invalidateSize({ animate: false });
    const delayedInvalidate = setTimeout(invalidateMap, 100);
    const observer = new ResizeObserver(() => invalidateMap());
    observer.observe(map.getContainer());
    window.addEventListener('resize', invalidateMap);
    return () => {
      clearTimeout(delayedInvalidate);
      observer.disconnect();
      window.removeEventListener('resize', invalidateMap);
    };
  }, [map]);

  // Add fullscreen control (pattern from trafimage-maps MapControls)
  useEffect(() => {
    const ctrl = new LeafletFullScreen({ position: 'topright' });
    ctrl.addTo(map);
    return () => { ctrl.remove(); };
  }, [map]);

  // Permalink: update URL on moveend, report BBOX, track zoom for generalization
  useMapEvents({
    moveend() {
      const center = map.getCenter();
      const zoom = map.getZoom();
      const params = new URLSearchParams(window.location.search);
      params.set('lat', center.lat.toFixed(4));
      params.set('lng', center.lng.toFixed(4));
      params.set('z', String(zoom));
      const newUrl = `${window.location.pathname}?${params.toString()}`;
      window.history.replaceState(null, '', newUrl);

      // BBOX filtering
      const bounds = map.getBounds();
      const bbox = `${bounds.getWest().toFixed(4)},${bounds.getSouth().toFixed(4)},${bounds.getEast().toFixed(4)},${bounds.getNorth().toFixed(4)}`;
      onBBoxChange(bbox);

      // Update zoom in store for generalization
      setZoom(zoom);
    },
  });

  // Restore permalink on mount
  useEffect(() => {
    const { lat, lng, zoom } = readPermalink();
    if (lat !== undefined && lng !== undefined) {
      map.setView([lat, lng], zoom ?? map.getZoom(), { animate: false });
    }
    // Send initial BBOX + set initial zoom
    const bounds = map.getBounds();
    const bbox = `${bounds.getWest().toFixed(4)},${bounds.getSouth().toFixed(4)},${bounds.getEast().toFixed(4)},${bounds.getNorth().toFixed(4)}`;
    onBBoxChange(bbox);
    setZoom(map.getZoom());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return null;
}

/**
 * Geolocation button control.
 */
function LocateControl() {
  const map = useMap();

  useEffect(() => {
    const control = new L.Control({ position: 'topright' });
    control.onAdd = () => {
      const btn = L.DomUtil.create('div', 'leaflet-bar leaflet-control');
      btn.innerHTML = '<a href="#" title="My location" role="button" aria-label="Show my location" style="font-size:18px;line-height:26px;text-align:center;width:26px;height:26px;display:block">⊕</a>';
      btn.onclick = (e) => {
        e.preventDefault();
        e.stopPropagation();
        map.locate({ setView: true, maxZoom: 12 });
      };
      L.DomEvent.disableClickPropagation(btn);
      return btn;
    };
    control.addTo(map);
    return () => { control.remove(); };
  }, [map]);

  return null;
}

export default function MapContent({ className, selectedTrainId, onTrainSelect }: MapContentProps) {
  const { data: routesData } = useRoutes();
  const { data: stationsData } = useStations();
  const { trajectories } = useTrainTrajectories();
  const { data: networkEdgesData } = useNetworkEdges();

  // Topic store
  const activeTopic = useMapTopicStore((s) => s.getActiveTopic());
  const generalization = useMapTopicStore((s) => s.generalization);
  const isLayerVisible = useMapTopicStore((s) => s.isLayerVisible);

  const trainPositions = useMemo(() => {
    const nowMs = Date.now();
    return Array.from(trajectories.values())
      .map((trajectory) => buildPositionFromTrajectory(trajectory, nowMs))
      .filter((position): position is NonNullable<typeof position> => position !== null);
  }, [trajectories]);

  const routes = routesData?.items || [];
  const stations = stationsData?.items || [];
  const displayNetworkEdges = useMemo(() => {
    const features = networkEdgesData?.features || [];
    const seen = new Set<string>();
    return features.filter((edge) => {
      const props = edge.properties;
      const fromStationId = props.from_station_id ?? props.from_node_id;
      const toStationId = props.to_station_id ?? props.to_node_id;
      const key = [Math.min(fromStationId, toStationId), Math.max(fromStationId, toStationId)].join(':');
      if (seen.has(key)) {
        return false;
      }
      seen.add(key);
      return true;
    });
  }, [networkEdgesData]);

  // --- Generalization: filter stations by zoom level ---
  const visibleStations = useMemo(() => {
    if (generalization.stationMode === 'hidden') return [];
    // 'major-only' mode was retired — station codes in DB are Thai-script and won't
    // match any English constants. All stations are now shown (clustered at low zoom).
    return stations;
  }, [stations, generalization.stationMode]);

  // --- Generalization: filter trains by type based on layer visibility ---
  const visibleTrains = useMemo(() => {
    return trainPositions.filter((p) => {
      if (p.train_type === 'special_express' && !isLayerVisible('trains-special-express')) return false;
      if (p.train_type === 'rapid' && !isLayerVisible('trains-rapid')) return false;
      if (p.train_type === 'ordinary' && !isLayerVisible('trains-ordinary')) return false;
      return true;
    });
  }, [trainPositions, isLayerVisible]);

  // All routes are always visible
  const visibleRoutes = routes;

  // The selected train always shows as a rich DOM marker regardless of zoom
  const selectedTrainPosition = useMemo(
    () => trainPositions.find((p) => p.train_id === selectedTrainId),
    [trainPositions, selectedTrainId],
  );

  // Non-selected trains for canvas rendering
  const canvasTrains = useMemo(
    () => visibleTrains.filter((p) => p.train_id !== selectedTrainId),
    [visibleTrains, selectedTrainId],
  );

  // Whether to use DOM markers for all trains (high zoom) or canvas
  const useDomTrains = generalization.trainMode === 'dom-markers';

  // Tile URL: driven entirely by the active topic
  const tileUrl = activeTopic.tileUrl || 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png';
  const tileAttribution = activeTopic.tileAttribution || '';

  // BBOX change handler — sends to both position and trajectory WS clients
  const handleBBoxChange = useCallback((bbox: string) => {
    const trajClient = getTrajectoryClient();
    if (trajClient.isConnected()) trajClient.sendBBox(bbox);
  }, []);

  // Permalink: persist selected train in URL
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const params = new URLSearchParams(window.location.search);
    if (selectedTrainId) {
      params.set('train', String(selectedTrainId));
    } else {
      params.delete('train');
    }
    const newUrl = `${window.location.pathname}?${params.toString()}`;
    window.history.replaceState(null, '', newUrl);
  }, [selectedTrainId]);

  // Are any station layers visible?
  const showStations = isLayerVisible('stations-major') || isLayerVisible('stations-all');
  // Should we cluster?
  const useCluster = generalization.stationMode === 'clustered';

  return (
    <div className={cn('h-full w-full', className)}>
      <MapContainer
        center={THAILAND_CENTER}
        zoom={INITIAL_ZOOM}
        className="h-full w-full"
        attributionControl={false}
        zoomControl={true}
        scrollWheelZoom={true}
      >
        <MapController onBBoxChange={handleBBoxChange} />
        <LocateControl />
        <ScaleControl position="bottomright" imperial={false} />

        {/* Tile layer — driven by active topic */}
        <TileLayer
          key={activeTopic.key}
          attribution={tileAttribution}
          url={tileUrl}
        />

        {/* Network topology track segments — infrastructure layer (off by default) */}
        {isLayerVisible('infrastructure-tracks') &&
          displayNetworkEdges.map((edge, idx) => {
            const coords = edge.geometry.coordinates.map(
              ([lon, lat]) => [lat, lon] as [number, number],
            );
            return (
              <Polyline
                key={`ne-${idx}`}
                positions={coords}
                color="#555555"
                weight={2}
                opacity={0.7}
              />
            );
          })}

        {/* Railway routes — filtered by layer tree, highlight selected train's route */}
        {generalization.routeMode !== 'hidden' &&
          visibleRoutes.map((route) => {
            if (!route.line_geometry?.coordinates) return null;

            const positions = route.line_geometry.coordinates.map(
              (coord) => [coord[1], coord[0]] as [number, number],
            );

            const isHighlighted = selectedTrainPosition?.route_id === route.id;

            return (
              <Polyline
                key={route.id}
                positions={positions}
                color={getRouteColor(route.route_type)}
                weight={isHighlighted ? 7 : 4}
                opacity={isHighlighted ? 1.0 : 0.7}
              >
                <Popup>
                  <div className="min-w-[150px]">
                    <h3 className="font-semibold">{route.name}</h3>
                    {route.name_th && (
                      <p className="text-sm text-muted-foreground">{route.name_th}</p>
                    )}
                    <p className="text-sm">Distance: {route.distance_km} km</p>
                  </div>
                </Popup>
              </Polyline>
            );
          })}

        {/* Stations — generalized by zoom */}
        {showStations && useCluster && (
          <MarkerClusterGroup
            chunkedLoading
            maxClusterRadius={40}
            disableClusteringAtZoom={10}
            spiderfyOnMaxZoom={true}
            showCoverageOnHover={false}
          >
            {visibleStations.map((station) => (
              <StationMarker key={station.id} station={station} />
            ))}
          </MarkerClusterGroup>
        )}
        {showStations && !useCluster &&
          visibleStations.map((station) => (
            <StationMarker key={station.id} station={station} />
          ))}

        {/* Trains — Canvas-based for performance at low/medium zoom */}
        {!useDomTrains && generalization.trainMode !== 'hidden' && (
          <CanvasTrainLayer
            positions={canvasTrains}
            trajectories={trajectories}
            selectedTrainId={selectedTrainId}
            onTrainSelect={onTrainSelect}
          />
        )}

        {/* Trains — DOM-based at high zoom for rich interactivity */}
        {useDomTrains &&
          visibleTrains
            .filter((p) => p.train_id !== selectedTrainId)
            .map((position) => (
              <TrainMarker
                key={position.train_id}
                position={position}
                trajectory={trajectories.get(position.train_id)}
                isSelected={false}
                onSelect={onTrainSelect}
              />
            ))}

        {/* Selected train always uses rich DOM marker for popup/interaction */}
        {selectedTrainPosition && (
          <TrainMarker
            key={selectedTrainId}
            position={selectedTrainPosition}
            trajectory={trajectories.get(selectedTrainPosition.train_id)}
            isSelected={true}
            onSelect={onTrainSelect}
          />
        )}

        {/* Selected train full trajectory polyline (geops pattern: show full route on select) */}
        {selectedTrainId && trajectories.get(selectedTrainId) && (() => {
          const traj = trajectories.get(selectedTrainId)!;
          const coords = traj.geometry.coordinates.map(
            ([lon, lat]) => [lat, lon] as [number, number],
          );
          return (
            <Polyline
              key={`traj-${selectedTrainId}`}
              positions={coords}
              color={traj.properties.line.color}
              weight={4}
              opacity={0.9}
              dashArray="8 4"
            />
          );
        })()}
      </MapContainer>

      {/* Layer tree overlay (trafimage-maps LayerTree pattern) */}
      <LayerTree />
    </div>
  );
}
