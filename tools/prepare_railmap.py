from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

BASE_COMMIT = "528dd0633dc0d704e5be2a71fbf83342c3cfe1d4"
SOURCE_PATH = Path("frontend/src/components/Map/RailMap.tsx")
OUTPUT_PATH = Path("generated/RailMap.tsx")
PR_CI_PATH = Path(".github/workflows/pr-ci.yml")
TEMP_WORKFLOW_PATH = Path(".github/workflows/prepare-railmap.yml")

FINAL_PR_CI = """name: Pull Request CI

on:
  pull_request:
    branches: [main]
    paths:
      - 'frontend/**'
      - 'gateway/**'
      - 'k8s/**'
      - '.github/workflows/pr-ci.yml'

concurrency:
  group: pr-ci-${{ github.event.pull_request.number }}
  cancel-in-progress: true

jobs:
  gateway:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: gateway
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: python -m pip install uv
      - run: uv pip install --system -e \".[dev]\"
      - run: ruff check app tests
      - run: black --check app tests
      - run: mypy app
      - run: pytest --cov=app --cov-report=term-missing

  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
      - run: npm run lint
      - name: Type-check
        shell: bash
        run: |
          set -o pipefail
          npm run type-check 2>&1 | tee typecheck.log
      - name: Upload type-check diagnostics
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: frontend-typecheck-log
          path: frontend/typecheck.log
          if-no-files-found: error
      - run: npm run test -- --coverage --passWithNoTests
      - run: npm run build

  manifests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install pyyaml
      - name: Validate Kubernetes YAML
        run: |
          python - <<'PY'
          from pathlib import Path
          import yaml

          for path in Path('k8s').rglob('*.yaml'):
              list(yaml.safe_load_all(path.read_text()))
              print(path)
          PY
        env:
          PYTHONUNBUFFERED: '1'
"""


def baseline() -> str:
    result = subprocess.run(
        ["git", "show", f"{BASE_COMMIT}:{SOURCE_PATH.as_posix()}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"{label} not found")
    return text.replace(old, new, 1)


def generate_railmap() -> str:
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
    return replace_once(
        text,
        map_props,
        """        zoomControl={false}
        scrollWheelZoom
        preferCanvas
      >""",
        "MapContainer props",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    text = generate_railmap()
    if not args.apply:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(text)
        return

    SOURCE_PATH.write_text(text)
    PR_CI_PATH.write_text(FINAL_PR_CI)
    TEMP_WORKFLOW_PATH.unlink(missing_ok=True)
    shutil.rmtree(OUTPUT_PATH.parent, ignore_errors=True)
    Path(__file__).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
