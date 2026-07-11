from __future__ import annotations

import subprocess
from pathlib import Path

BASE_COMMIT = "528dd0633dc0d704e5be2a71fbf83342c3cfe1d4"
SOURCE_PATH = "frontend/src/components/Map/RailMap.tsx"
OUTPUT_PATH = Path("generated/RailMap.tsx")


def baseline() -> str:
    result = subprocess.run(
        ["git", "show", f"{BASE_COMMIT}:{SOURCE_PATH}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"{label} not found")
    return text.replace(old, new, 1)


def main() -> None:
    text = baseline()
    text = replace_once(
        text,
        "import type { Trajectory } from '@/types';",
        "import type { NetworkEdgeCollection, Trajectory } from '@/types';",
        "trajectory import",
    )

    marker = (
        "// ─── Inner map component (has access to useMap / useMapEvents) "
        "────────────────\n"
    )
    canvas_component = """// ─── Canvas-backed static network ────────────────────────────────────────────

const EMPTY_NETWORK: NetworkEdgeCollection = {
  type: 'FeatureCollection',
  features: [],
};

function TracksCanvasLayer({
  edges,
}: {
  edges?: NetworkEdgeCollection | null;
}) {
  const map = useMap();
  const renderer = useMemo(() => L.canvas({ padding: 0.5 }), []);

  const collection = useMemo<NetworkEdgeCollection>(() => {
    const source = edges ?? EMPTY_NETWORK;
    const seen = new Set<string>();
    return {
      type: 'FeatureCollection',
      features: source.features.filter((edge) => {
        const a = edge.properties.from_node_id;
        const b = edge.properties.to_node_id;
        const key = `${Math.min(a, b)}:${Math.max(a, b)}`;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      }),
    };
  }, [edges]);

  useEffect(() => {
    if (collection.features.length === 0) return;

    const casing = L.geoJSON(collection as never, {
      interactive: false,
      style: {
        renderer,
        color: '#FFFFFF',
        weight: 6,
        opacity: 0.62,
        lineCap: 'round',
        lineJoin: 'round',
      },
    });
    const routes = L.geoJSON(collection as never, {
      interactive: false,
      style: (feature) => ({
        renderer,
        color: getRouteColor(String(feature?.properties?.route_type ?? '')),
        weight: 4,
        opacity: 0.82,
        lineCap: 'round',
        lineJoin: 'round',
      }),
    });
    const group = L.layerGroup([casing, routes]).addTo(map);
    return () => {
      map.removeLayer(group);
    };
  }, [collection, map, renderer]);

  return null;
}

"""
    text = replace_once(text, marker, canvas_component + marker, "MapCore marker")

    derived = """  const stations = topology?.stations ?? [];
  const networkEdges = topology?.network_edges?.features ?? [];

  // Deduplicate edges (same segment may appear from both directions)
  const displayEdges = useMemo(() => {
    const seen = new Set<string>();
    return networkEdges.filter((edge) => {
      const a = edge.properties.from_node_id;
      const b = edge.properties.to_node_id;
      const key = `${Math.min(a, b)}:${Math.max(a, b)}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [networkEdges]);
"""
    text = replace_once(
        text,
        derived,
        "  const stations = topology?.stations ?? [];\n",
        "network derivation",
    )

    network_render = """      {/* Route network — thick coloured polylines */}
      {displayEdges.map((edge, idx) => {
        const positions = edge.geometry.coordinates.map(
          ([lon, lat]) => [lat, lon] as [number, number]
        );
        const routeType = edge.properties.route_type ?? '';
        return (
          <Polyline
            key={`edge-${idx}`}
            positions={positions}
            color={getRouteColor(routeType)}
            weight={4}
            opacity={0.8}
            interactive={false}
          />
        );
      })}
"""
    text = replace_once(
        text,
        network_render,
        """      {/* Route network — one Canvas-backed GeoJSON layer */}
      <TracksCanvasLayer edges={topology?.network_edges} />
""",
        "network render",
    )

    map_props = """        zoomControl={false}
        scrollWheelZoom
      >"""
    text = replace_once(
        text,
        map_props,
        """        zoomControl={false}
        scrollWheelZoom
        preferCanvas
      >""",
        "MapContainer props",
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(text)


if __name__ == "__main__":
    main()
