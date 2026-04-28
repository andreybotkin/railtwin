import json
from collections import defaultdict, deque

with open("graph.json", "r") as f:
    data = json.load(f)
    adjacency = data.get("adjacency", {})

with open("nodes.json", "r") as f:
    nodes_feat = json.load(f)
    features = nodes_feat.get("features", [])

# Build graph using dict
adj = defaultdict(set)
for u, neighbors in adjacency.items():
    u_int = int(u)
    for v in neighbors:
        v_int = int(v)
        adj[u_int].add(v_int)
        adj[v_int].add(u_int)

nodes = list(adj.keys())
visited = set()
components = []

for node in nodes:
    if node not in visited:
        component = set()
        queue = deque([node])
        visited.add(node)
        while queue:
            curr = queue.popleft()
            component.add(curr)
            for neighbor in adj[curr]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        components.append(component)

component_sizes = sorted([len(c) for c in components], reverse=True)

station_nodes = set()
for feat in features:
    props = feat.get("properties", {})
    if props.get("station_id") is not None:
        station_nodes.add(feat.get("id"))

stations_in_components = []
for i, comp in enumerate(components):
    stations_in_comp = station_nodes.intersection(comp)
    if stations_in_comp:
        stations_in_components.append(len(stations_in_comp))

all_stations_in_one = (
    (
        len(stations_in_components) == 1
        and stations_in_components[0] == len(station_nodes)
    )
    if station_nodes
    else True
)

print(f"Total Nodes in graph: {len(adj)}")
print(f"Component sizes (top 5): {component_sizes[:5]}")
print(f"Number of connected components: {len(components)}")
print(f"Total station nodes: {len(station_nodes)}")
print(f"Station nodes found across {len(stations_in_components)} components")
print(f"Stations per component: {stations_in_components}")
print(f"All station nodes in one component: {all_stations_in_one}")
