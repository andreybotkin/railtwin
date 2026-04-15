/**
 * Default map topics (themes) and zoom generalization rules.
 *
 * trafimage-maps pattern: each topic is a switchable map theme that defines
 * which layers are visible, tile source, and default state.
 *
 * mobility-toolbox-js pattern: zoom generalization defines what level of
 * detail to show at each zoom range (motsByZoom concept).
 */

import type { MapTopic, ZoomGeneralization } from '@/types/map-topics';

// ── Tile URLs ──────────────────────────────────────────────────────
const TILE_VOYAGER = 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png';
const TILE_DARK = 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png';
const TILE_SATELLITE = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';

const ATTR_CARTO = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/">CARTO</a>';
const ATTR_ESRI = 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community';

// ── Shared layer definitions ───────────────────────────────────────

function makeRouteLayers(visible: boolean) {
  return [
    { key: 'routes-northern', name: 'Northern Line', nameKey: 'layers.routeNorthern', category: 'routes' as const, visible, opacity: 1, icon: '🔴' },
    { key: 'routes-northeastern', name: 'Northeastern Line', nameKey: 'layers.routeNortheastern', category: 'routes' as const, visible, opacity: 1, icon: '🔵' },
    { key: 'routes-southern', name: 'Southern Line', nameKey: 'layers.routeSouthern', category: 'routes' as const, visible, opacity: 1, icon: '🟢' },
    { key: 'routes-eastern', name: 'Eastern Line', nameKey: 'layers.routeEastern', category: 'routes' as const, visible, opacity: 1, icon: '🟠' },
  ];
}

function makeStationLayers(visible: boolean) {
  return [
    { key: 'stations-major', name: 'Major Stations', nameKey: 'layers.stationsMajor', category: 'stations' as const, visible, opacity: 1, minZoom: 0, icon: '🏛️' },
    { key: 'stations-all', name: 'All Stations', nameKey: 'layers.stationsAll', category: 'stations' as const, visible, opacity: 1, minZoom: 8, icon: '📍' },
  ];
}

function makeTrainLayers(visible: boolean) {
  return [
    { key: 'trains-special-express', name: 'Special Express', nameKey: 'layers.trainsSpecialExpress', category: 'trains' as const, visible, opacity: 1, icon: '🚅' },
    { key: 'trains-rapid', name: 'Rapid', nameKey: 'layers.trainsRapid', category: 'trains' as const, visible, opacity: 1, icon: '🚆' },
    { key: 'trains-ordinary', name: 'Ordinary', nameKey: 'layers.trainsOrdinary', category: 'trains' as const, visible, opacity: 1, icon: '🚃' },
  ];
}

function makeInfrastructureLayers(visible: boolean) {
  return [
    {
      key: 'infrastructure-tracks',
      name: 'Track Network Graph',
      nameKey: 'layers.infrastructureTracks',
      category: 'infrastructure' as const,
      visible,
      opacity: 0.8,
      minZoom: 7,
      description: 'Station-to-station directed track segments (network topology graph)',
      icon: '🛤️',
    },
  ];
}

// ── Topics ──────────────────────────────────────────────────────────

export const DEFAULT_TOPICS: MapTopic[] = [
  {
    key: 'railway',
    name: 'Light Map',
    nameKey: 'topics.railway',
    description: 'Real-time train operations with routes, stations, and live positions',
    tileUrl: TILE_VOYAGER,
    tileAttribution: ATTR_CARTO,
    thumbnail: '/images/topic-railway.png',
    layers: [
      ...makeRouteLayers(true),
      ...makeStationLayers(true),
      ...makeTrainLayers(true),
      ...makeInfrastructureLayers(false),
    ],
  },
  {
    key: 'dark',
    name: 'Dark Map',
    nameKey: 'topics.dark',
    description: 'Dark theme for low-light environments',
    tileUrl: TILE_DARK,
    tileAttribution: ATTR_CARTO,
    thumbnail: '/images/topic-dark.png',
    layers: [
      ...makeRouteLayers(true),
      ...makeStationLayers(true),
      ...makeTrainLayers(true),
      ...makeInfrastructureLayers(false),
    ],
  },
  {
    key: 'satellite',
    name: 'Satellite',
    nameKey: 'topics.satellite',
    description: 'Aerial imagery with railway overlay',
    tileUrl: TILE_SATELLITE,
    tileAttribution: ATTR_ESRI,
    thumbnail: '/images/topic-satellite.png',
    layers: [
      ...makeRouteLayers(true),
      ...makeStationLayers(true),
      ...makeTrainLayers(true),
      ...makeInfrastructureLayers(false),
    ],
  },
];

// ── Zoom Generalization ─────────────────────────────────────────────
// Pattern from mobility-toolbox-js motsByZoom:
// At low zoom → minimal detail, canvas dots
// At high zoom → full detail, DOM markers

// NOTE: station codes in the DB are Thai script (e.g. 'กท.'), not Latin.
// 'major-only' mode was removed because the old Latin-code MAJOR_STATIONS set
// never matched anything. Stations are now visible from zoom 5 as clusters.
export const ZOOM_GENERALIZATION: ZoomGeneralization[] = [
  {
    minZoom: 0,
    maxZoom: 4,
    stationMode: 'clustered',
    trainMode: 'canvas-dots',
    routeMode: 'simplified',
    stationRadius: 5,
    trainRadius: 3,
  },
  {
    minZoom: 5,
    maxZoom: 7,
    stationMode: 'clustered',
    trainMode: 'canvas-dots',
    routeMode: 'full',
    stationRadius: 5,
    trainRadius: 4,
  },
  {
    minZoom: 8,
    maxZoom: 9,
    stationMode: 'clustered',
    trainMode: 'canvas-markers',
    routeMode: 'full',
    stationRadius: 5,
    trainRadius: 5,
  },
  {
    minZoom: 10,
    maxZoom: 11,
    stationMode: 'all',
    trainMode: 'canvas-markers',
    routeMode: 'full',
    stationRadius: 6,
    trainRadius: 6,
  },
  {
    minZoom: 12,
    maxZoom: 20,
    stationMode: 'all',
    trainMode: 'dom-markers',
    routeMode: 'full',
    stationRadius: 8,
    trainRadius: 8,
  },
];

/**
 * Get generalization config for a given zoom level.
 */
export function getGeneralizationForZoom(zoom: number): ZoomGeneralization {
  return (
    ZOOM_GENERALIZATION.find((g) => zoom >= g.minZoom && zoom <= g.maxZoom) ??
    ZOOM_GENERALIZATION[ZOOM_GENERALIZATION.length - 1]
  );
}
