/**
 * MapLibre style resolver.
 *
 * Three themes:
 *   light     — OpenFreeMap "liberty" vector style (OSM-based, CC-BY)
 *   dark      — CARTO dark_all raster tiles (no API key needed)
 *   satellite — ESRI World Imagery raster tiles (no API key needed)
 *
 * Override with `NEXT_PUBLIC_MAP_STYLE_URL` (e.g. MapTiler) to replace the
 * light style when you need a custom vector style.
 */

import type { StyleSpecification } from 'maplibre-gl';

export type AppTheme = 'light' | 'dark' | 'satellite';

const DEFAULT_LIGHT_STYLE = 'https://tiles.openfreemap.org/styles/liberty';

const DARK_STYLE: StyleSpecification = {
  version: 8,
  glyphs: 'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf',
  sprite: 'https://tiles.openfreemap.org/sprites/liberty/sprite',
  sources: {
    'carto-dark': {
      type: 'raster',
      tiles: [
        'https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png',
        'https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png',
        'https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png',
      ],
      tileSize: 256,
      maxzoom: 19,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/">CARTO</a>',
    },
  },
  layers: [
    {
      id: 'carto-dark-layer',
      type: 'raster',
      source: 'carto-dark',
    },
  ],
};

const SATELLITE_STYLE: StyleSpecification = {
  version: 8,
  glyphs: 'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf',
  sprite: 'https://tiles.openfreemap.org/sprites/liberty/sprite',
  sources: {
    'esri-satellite': {
      type: 'raster',
      tiles: [
        'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      ],
      tileSize: 256,
      maxzoom: 18,
      attribution:
        'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community',
    },
  },
  layers: [
    {
      id: 'satellite-base',
      type: 'raster',
      source: 'esri-satellite',
    },
  ],
};

export function getMapStyleForTheme(
  theme: AppTheme
): string | StyleSpecification {
  if (theme === 'dark') return DARK_STYLE;
  if (theme === 'satellite') return SATELLITE_STYLE;
  return process.env.NEXT_PUBLIC_MAP_STYLE_URL || DEFAULT_LIGHT_STYLE;
}

/** @deprecated Use getMapStyleForTheme */
export function getMapStyleUrl(): string | StyleSpecification {
  return process.env.NEXT_PUBLIC_MAP_STYLE_URL || DEFAULT_LIGHT_STYLE;
}

export const THAILAND_VIEW = {
  longitude: 100.5,
  latitude: 13.75,
  zoom: 5.5,
};

/** Canonical per-route-type colours used across tracks + train icons. */
export const ROUTE_COLORS: Record<string, string> = {
  northern: '#C62828',
  northeastern: '#1565C0',
  southern: '#2E7D32',
  eastern: '#6A1B9A',
};

export const DEFAULT_ROUTE_COLOR = '#546E7A';
