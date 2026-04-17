/**
 * MapLibre style resolver.
 *
 * Default: OpenFreeMap `liberty` — an OSM-based vector style hosted for free
 * at `tiles.openfreemap.org`, no API key, CC-BY attribution. Override with
 * `NEXT_PUBLIC_MAP_STYLE_URL` (e.g. MapTiler) when you need a different style.
 */

import type { StyleSpecification } from 'maplibre-gl';

const DEFAULT_STYLE_URL = 'https://tiles.openfreemap.org/styles/liberty';

export function getMapStyleUrl(): string | StyleSpecification {
  return process.env.NEXT_PUBLIC_MAP_STYLE_URL || DEFAULT_STYLE_URL;
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
