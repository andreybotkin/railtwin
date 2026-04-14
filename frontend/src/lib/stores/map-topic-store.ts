/**
 * Zustand store for map topic & layer state.
 *
 * Pattern from geops/trafimage-maps:
 * - Active topic determines tile source, visible layers, and theme
 * - Layers can be toggled individually within the layer tree
 * - Zoom generalization rules automatically adjust detail levels
 */

import { create } from 'zustand';
import type { MapLayer, MapTopic } from '@/types/map-topics';
import { DEFAULT_TOPICS, getGeneralizationForZoom } from '@/lib/map-topics';
import type { ZoomGeneralization } from '@/types/map-topics';

interface MapTopicState {
  /** All available topics */
  topics: MapTopic[];
  /** Currently active topic key */
  activeTopicKey: string;
  /** Layer overrides (user toggles, per topic) */
  layerOverrides: Map<string, boolean>;
  /** Current map zoom level */
  zoom: number;
  /** Current generalization config (derived from zoom) */
  generalization: ZoomGeneralization;
  /** Whether the layer tree panel is open */
  layerTreeOpen: boolean;

  // Actions
  setActiveTopic: (key: string) => void;
  toggleLayer: (layerKey: string) => void;
  setLayerVisible: (layerKey: string, visible: boolean) => void;
  setLayerOpacity: (layerKey: string, opacity: number) => void;
  setZoom: (zoom: number) => void;
  setLayerTreeOpen: (open: boolean) => void;
  /** Get the effective layers for the active topic (with user overrides) */
  getEffectiveLayers: () => MapLayer[];
  /** Check if a specific layer is visible (considering zoom generalization) */
  isLayerVisible: (layerKey: string) => boolean;
  /** Get the active topic object */
  getActiveTopic: () => MapTopic;
}

export const useMapTopicStore = create<MapTopicState>((set, get) => ({
  topics: DEFAULT_TOPICS,
  activeTopicKey: 'railway',
  layerOverrides: new Map(),
  zoom: 6,
  generalization: getGeneralizationForZoom(6),
  layerTreeOpen: false,

  setActiveTopic: (key) => {
    set({ activeTopicKey: key, layerOverrides: new Map() });
  },

  toggleLayer: (layerKey) => {
    const state = get();
    const overrides = new Map(state.layerOverrides);
    const current = state.isLayerVisible(layerKey);
    overrides.set(layerKey, !current);
    set({ layerOverrides: overrides });
  },

  setLayerVisible: (layerKey, visible) => {
    const state = get();
    const overrides = new Map(state.layerOverrides);
    overrides.set(layerKey, visible);
    set({ layerOverrides: overrides });
  },

  setLayerOpacity: (layerKey, opacity) => {
    const state = get();
    const topic = state.getActiveTopic();
    const layers = topic.layers.map((l) =>
      l.key === layerKey ? { ...l, opacity } : l,
    );
    const topics = state.topics.map((t) =>
      t.key === topic.key ? { ...t, layers } : t,
    );
    set({ topics });
  },

  setZoom: (zoom) => {
    set({ zoom, generalization: getGeneralizationForZoom(zoom) });
  },

  setLayerTreeOpen: (open) => set({ layerTreeOpen: open }),

  getEffectiveLayers: () => {
    const state = get();
    const topic = state.getActiveTopic();
    return topic.layers.map((layer) => {
      const override = state.layerOverrides.get(layer.key);
      return {
        ...layer,
        visible: override !== undefined ? override : layer.visible,
      };
    });
  },

  isLayerVisible: (layerKey) => {
    const state = get();
    const topic = state.getActiveTopic();
    const layer = topic.layers.find((l) => l.key === layerKey);
    if (!layer) return false;
    const override = state.layerOverrides.get(layerKey);
    const visible = override !== undefined ? override : layer.visible;
    // Also check zoom constraints
    if (layer.minZoom !== undefined && state.zoom < layer.minZoom) return false;
    if (layer.maxZoom !== undefined && state.zoom > layer.maxZoom) return false;
    return visible;
  },

  getActiveTopic: () => {
    const state = get();
    return state.topics.find((t) => t.key === state.activeTopicKey) ?? state.topics[0];
  },
}));
