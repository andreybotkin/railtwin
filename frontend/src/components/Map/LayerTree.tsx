/**
 * Layer tree UI component.
 *
 * Pattern from geops/trafimage-maps LayerTree:
 * - Grouped by category (Routes, Stations, Trains)
 * - Checkbox toggles per layer
 * - Topic switcher at the top
 * - Collapsible categories
 */

'use client';

import { useState, useCallback } from 'react';
import { Layers, ChevronDown, ChevronRight, X } from 'lucide-react';
import { useMapTopicStore } from '@/lib/stores/map-topic-store';
import type { LayerCategory } from '@/types/map-topics';
import { cn } from '@/lib/utils';

const CATEGORY_LABELS: Record<LayerCategory, { label: string; icon: string }> = {
  base: { label: 'Base Map', icon: '🗺️' },
  routes: { label: 'Routes', icon: '🛤️' },
  stations: { label: 'Stations', icon: '🏛️' },
  trains: { label: 'Trains', icon: '🚂' },
  infrastructure: { label: 'Infrastructure', icon: '🏗️' },
};

interface LayerTreeProps {
  className?: string;
}
function CategoryGroup({ category, children }: { category: LayerCategory; children: React.ReactNode }) {
  const [expanded, setExpanded] = useState(true);
  const { label, icon } = CATEGORY_LABELS[category] ?? { label: category, icon: '📁' };

  return (
    <div className="border-b border-border last:border-b-0">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 px-3 py-2 text-sm font-medium hover:bg-muted transition-colors"
        aria-expanded={expanded}
      >
        {expanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        <span>{icon}</span>
        <span>{label}</span>
      </button>
      {expanded && <div className="pb-1">{children}</div>}
    </div>
  );
}

/**
 * Layer tree panel with topic switcher and layer toggles.
 */
export default function LayerTree({ className }: LayerTreeProps) {
  const {
    layerTreeOpen,
    setLayerTreeOpen,
    getEffectiveLayers,
    toggleLayer,
  } = useMapTopicStore();

  const effectiveLayers = getEffectiveLayers();

  // Group layers by category
  const grouped = effectiveLayers.reduce(
    (acc, layer) => {
      if (!acc[layer.category]) acc[layer.category] = [];
      acc[layer.category].push(layer);
      return acc;
    },
    {} as Record<string, typeof effectiveLayers>,
  );

  const handleToggle = useCallback(
    (key: string) => () => toggleLayer(key),
    [toggleLayer],
  );

  if (!layerTreeOpen) {
    return (
      <button
        onClick={() => setLayerTreeOpen(true)}
        className={cn(
          'absolute top-20 right-2 z-[1000] rounded-lg border bg-background p-2 shadow-md hover:bg-muted transition-colors',
          className,
        )}
        aria-label="Open layer tree"
        title="Layers"
      >
        <Layers className="h-5 w-5" />
      </button>
    );
  }

  return (
    <div
      className={cn(
        'absolute top-20 right-2 z-[1000] w-64 rounded-lg border bg-background shadow-lg overflow-hidden',
        className,
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b px-3 py-2">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Layers className="h-4 w-4" />
          <span>Layers</span>
        </div>
        <button
          onClick={() => setLayerTreeOpen(false)}
          className="rounded p-0.5 hover:bg-muted transition-colors"
          aria-label="Close layer tree"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Topic switcher moved to header */}

      {/* Layer categories */}
      <div className="max-h-[50vh] overflow-y-auto">
        {(['stations', 'trains'] as LayerCategory[]).map((cat) => {
          const layers = grouped[cat];
          if (!layers || layers.length === 0) return null;
          return (
            <CategoryGroup key={cat} category={cat}>
              {layers.map((layer) => (
                <label
                  key={layer.key}
                  className="flex cursor-pointer items-center gap-2 px-6 py-1 text-sm hover:bg-muted/50 transition-colors"
                >
                  <input
                    type="checkbox"
                    checked={layer.visible}
                    onChange={handleToggle(layer.key)}
                    className="h-3.5 w-3.5 rounded border-border accent-primary"
                  />
                  {layer.icon && <span className="text-xs">{layer.icon}</span>}
                  <span className={cn(!layer.visible && 'text-muted-foreground')}>
                    {layer.name}
                  </span>
                </label>
              ))}
            </CategoryGroup>
          );
        })}
      </div>
    </div>
  );
}
