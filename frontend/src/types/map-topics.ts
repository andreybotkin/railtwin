/**
 * Map topic / layer configuration types.
 *
 * Pattern from geops/trafimage-maps topic-based architecture:
 * - Topics define switchable map themes (e.g., Railway Operations, Infrastructure, Satellite)
 * - Each topic has a set of layers with visibility and metadata
 * - Layers are grouped into categories for the layer tree UI
 */

/** Individual map layer configuration */
export interface MapLayer {
  /** Unique layer key */
  key: string;
  /** Display name */
  name: string;
  /** i18n message key (e.g. 'layers.routes') */
  nameKey?: string;
  /** Layer category for grouping in tree UI */
  category: LayerCategory;
  /** Whether the layer is currently visible */
  visible: boolean;
  /** Opacity 0–1 */
  opacity: number;
  /** Minimum zoom at which this layer appears */
  minZoom?: number;
  /** Maximum zoom at which this layer appears */
  maxZoom?: number;
  /** Optional description / i18n key */
  description?: string;
  /** Icon identifier for the layer tree */
  icon?: string;
}

/** Layer categories for tree grouping */
export type LayerCategory =
  | 'base'
  | 'routes'
  | 'stations'
  | 'trains'
  | 'infrastructure';

/** Map topic (theme) configuration */
export interface MapTopic {
  /** Unique topic key */
  key: string;
  /** Display name */
  name: string;
  /** i18n message key */
  nameKey?: string;
  /** Description */
  description?: string;
  /** Tile layer URL (overrides default) */
  tileUrl?: string;
  /** Tile attribution */
  tileAttribution?: string;
  /** Which layers are enabled and their default state */
  layers: MapLayer[];
  /** Thumbnail image URL for topic switcher */
  thumbnail?: string;
}

/**
 * Generalization configuration per zoom range.
 * Pattern from mobility-toolbox-js motsByZoom: show different detail
 * levels at different zoom levels.
 */
export interface ZoomGeneralization {
  /** Zoom range start (inclusive) */
  minZoom: number;
  /** Zoom range end (inclusive) */
  maxZoom: number;
  /** Station display mode at this zoom */
  stationMode: 'hidden' | 'major-only' | 'clustered' | 'all';
  /** Train display mode at this zoom */
  trainMode: 'hidden' | 'canvas-dots' | 'canvas-markers' | 'dom-markers';
  /** Route display mode */
  routeMode: 'hidden' | 'simplified' | 'full';
  /** Station marker radius at this zoom */
  stationRadius: number;
  /** Train marker radius at this zoom */
  trainRadius: number;
}
