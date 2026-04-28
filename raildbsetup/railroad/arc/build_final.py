import heapq
import math
import re
from collections import defaultdict

import numpy as np
from scipy.spatial import cKDTree

POINT_GAP_THRESHOLD = 0.003
GRAPH_SNAP = 0.0002
SINGLE_TRACK_CLUSTER_TOL = 0.002
EXACT_TRACK_SNAP = 1e-6
PHA_SADET_CENTER = (101.1006416, 14.6445175)
PHA_SADET_RADIUS = 0.03
PHA_SADET_FAR_FRACTION = 0.30

LOPBURI_ALIASES = {"Lopburi Bypass Line", "สายเลี่ยงเมืองลพบุรี"}
KAENG_CHORD_ALIASES = {
    "Kaeng Khoi Junction Chord Line",
    "ทางคู่เลี่ยงเมืองชุมทางแก่งคอย",
}
KHLONG19_ALIASES = {"ทางรถไฟสายชุมทางคลองสิบเก้า–ชุมทางแก่งคอย"}


def parse_coordinates(coords_str):
    points = []
    for token in coords_str.strip().split():
        parts = token.split(",")
        if len(parts) >= 2:
            try:
                lon, lat = float(parts[0]), float(parts[1])
                points.append((round(lon, 6), round(lat, 6)))
            except ValueError:
                pass
    return points


def extract_tags(placemark):
    tags = []
    desc = re.search(r"<description>(.*?)</description>", placemark, re.DOTALL)
    if desc:
        text = desc.group(1).strip()
        if text:
            tags.append(text)

    for name in re.findall(r"<name>(.*?)</name>", placemark, re.DOTALL):
        text = name.strip()
        if text and text != "rail":
            tags.append(text)
    return tags


def polyline_length(points):
    return sum(
        math.dist(points[index - 1], points[index]) for index in range(1, len(points))
    )


def dedupe_consecutive(points, tolerance=1e-9):
    if not points:
        return []

    result = [points[0]]
    for point in points[1:]:
        if math.dist(result[-1], point) > tolerance:
            result.append(point)
    return result


def canonical_segment_key(points):
    coords = tuple(points)
    rev = tuple(reversed(coords))
    return coords if coords <= rev else rev


def min_point_distance(points, center):
    return min(math.dist(point, center) for point in points)


def far_fraction(points, srt_tree):
    distances, _ = srt_tree.query(np.asarray(points, dtype=float))
    return float(np.mean(distances > POINT_GAP_THRESHOLD))


def in_depot_bbox(points):
    arr = np.asarray(points, dtype=float)
    lons, lats = arr[:, 0], arr[:, 1]
    return (
        lons.min() >= 100.538
        and lons.max() <= 100.558
        and lats.min() >= 13.795
        and lats.max() <= 13.815
    )


def parse_osm_segments(osm_kml, srt_tree):
    segments = []
    for placemark in re.findall(r"<Placemark>.*?</Placemark>", osm_kml, re.DOTALL):
        coords_match = re.search(
            r"<coordinates>(.*?)</coordinates>", placemark, re.DOTALL
        )
        if not coords_match:
            continue

        points = dedupe_consecutive(parse_coordinates(coords_match.group(1)))
        if len(points) < 2 or in_depot_bbox(points):
            continue

        segments.append(
            {
                "points": points,
                "tags": set(extract_tags(placemark)),
                "far_fraction": far_fraction(points, srt_tree),
                "key": canonical_segment_key(points),
            }
        )
    return segments


def parse_srt_placemarks(srt_kml):
    placemark_matches = re.findall(
        r'<Placemark id="20260410railwaymapofthailand.*?</Placemark>',
        srt_kml,
        re.DOTALL,
    )
    placemarks = []
    by_name = {}
    for placemark in placemark_matches:
        name = re.search(r"<name>(.*?)</name>", placemark).group(1)
        points = parse_coordinates(
            re.search(r"<coordinates>(.*?)</coordinates>", placemark, re.DOTALL).group(
                1
            )
        )
        record = {"name": name, "placemark": placemark, "points": points}
        placemarks.append(record)
        by_name[name] = record
    return placemarks, by_name


def format_coordinates(points):
    return " ".join(f"{point[0]},{point[1]}" for point in points)


def make_linestring(points):
    return (
        "<LineString><tessellate>1</tessellate>"
        f"<coordinates>{format_coordinates(points)}</coordinates></LineString>"
    )


def make_geometry(lines):
    if len(lines) == 1:
        return make_linestring(lines[0])
    return (
        "<MultiGeometry>"
        + "".join(make_linestring(line) for line in lines)
        + "</MultiGeometry>"
    )


def replace_geometry(placemark, geometry_xml):
    return re.sub(
        r"<MultiGeometry>.*?</MultiGeometry>|<LineString>.*?</LineString>",
        geometry_xml,
        placemark,
        count=1,
        flags=re.DOTALL,
    )


class UnionFind:
    def __init__(self, size):
        self.parent = list(range(size))

    def find(self, item):
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, left, right):
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def build_route_graph(segments, snap_tol=GRAPH_SNAP):
    unique_segments = []
    seen = set()
    endpoints = []
    endpoint_refs = []

    for points in segments:
        cleaned = dedupe_consecutive(points)
        if len(cleaned) < 2:
            continue
        key = canonical_segment_key(cleaned)
        if key in seen:
            continue
        seen.add(key)
        unique_segments.append(cleaned)
        endpoint_refs.append((len(endpoints), len(endpoints) + 1))
        endpoints.extend([cleaned[0], cleaned[-1]])

    if not unique_segments:
        return {}, [], defaultdict(list)

    union_find = UnionFind(len(endpoints))
    for left in range(len(endpoints)):
        for right in range(left + 1, len(endpoints)):
            if math.dist(endpoints[left], endpoints[right]) <= snap_tol:
                union_find.union(left, right)

    root_points = defaultdict(list)
    for index, point in enumerate(endpoints):
        root_points[union_find.find(index)].append(point)

    root_to_node = {}
    node_points = {}
    for root, cluster_points in root_points.items():
        node_id = len(root_to_node)
        root_to_node[root] = node_id
        avg_lon = round(
            sum(point[0] for point in cluster_points) / len(cluster_points), 6
        )
        avg_lat = round(
            sum(point[1] for point in cluster_points) / len(cluster_points), 6
        )
        node_points[node_id] = (avg_lon, avg_lat)

    edges = []
    adjacency = defaultdict(list)
    for points, (start_idx, end_idx) in zip(unique_segments, endpoint_refs):
        start_node = root_to_node[union_find.find(start_idx)]
        end_node = root_to_node[union_find.find(end_idx)]
        edge_id = len(edges)
        edges.append(
            {
                "start": start_node,
                "end": end_node,
                "points": points,
                "length": polyline_length(points),
            }
        )
        adjacency[start_node].append(edge_id)
        adjacency[end_node].append(edge_id)
    return node_points, edges, adjacency


def shortest_path_between_nodes(start, end, adjacency, edges):
    distances = {start: 0.0}
    previous = {}
    heap = [(0.0, start)]

    while heap:
        current_distance, node = heapq.heappop(heap)
        if current_distance > distances[node]:
            continue
        if node == end:
            break

        for edge_id in adjacency.get(node, []):
            edge = edges[edge_id]
            neighbor = edge["end"] if edge["start"] == node else edge["start"]
            new_distance = current_distance + edge["length"]
            if new_distance < distances.get(neighbor, math.inf):
                distances[neighbor] = new_distance
                previous[neighbor] = (node, edge_id)
                heapq.heappush(heap, (new_distance, neighbor))

    if end not in distances:
        return None, math.inf

    path_edges = []
    node = end
    while node != start:
        prev_node, edge_id = previous[node]
        path_edges.append((prev_node, node, edge_id))
        node = prev_node
    path_edges.reverse()
    return path_edges, distances[end]


def path_points_from_edges(path_edges, edges):
    points = []
    for start_node, end_node, edge_id in path_edges:
        edge = edges[edge_id]
        if edge["start"] == start_node and edge["end"] == end_node:
            edge_points = edge["points"]
        else:
            edge_points = list(reversed(edge["points"]))
        points.extend(edge_points if not points else edge_points[1:])
    return dedupe_consecutive(points)


def cluster_nodes(node_points, tolerance):
    node_ids = list(node_points)
    union_find = UnionFind(len(node_ids))
    for left in range(len(node_ids)):
        for right in range(left + 1, len(node_ids)):
            if (
                math.dist(node_points[node_ids[left]], node_points[node_ids[right]])
                <= tolerance
            ):
                union_find.union(left, right)

    groups = defaultdict(list)
    for index, node_id in enumerate(node_ids):
        groups[union_find.find(index)].append(node_id)
    return list(groups.values())


def single_track_path(segments, cluster_tolerance=SINGLE_TRACK_CLUSTER_TOL):
    node_points, edges, adjacency = build_route_graph(segments)
    if not edges:
        return []

    groups = cluster_nodes(node_points, cluster_tolerance)
    best = None
    for left_index in range(len(groups)):
        for right_index in range(left_index + 1, len(groups)):
            left_group = groups[left_index]
            right_group = groups[right_index]
            left_centroid = np.mean(
                np.asarray([node_points[node_id] for node_id in left_group]), axis=0
            )
            right_centroid = np.mean(
                np.asarray([node_points[node_id] for node_id in right_group]), axis=0
            )
            separation = math.dist(left_centroid, right_centroid)
            for start_node in left_group:
                for end_node in right_group:
                    path_edges, distance = shortest_path_between_nodes(
                        start_node, end_node, adjacency, edges
                    )
                    if not path_edges:
                        continue
                    if (
                        best is None
                        or separation > best["separation"]
                        or (
                            abs(separation - best["separation"]) < 1e-9
                            and distance < best["distance"]
                        )
                    ):
                        best = {
                            "separation": separation,
                            "distance": distance,
                            "points": path_points_from_edges(path_edges, edges),
                        }
    return best["points"] if best else []


def segments_by_aliases(osm_segments, aliases):
    segments = []
    seen = set()
    for segment in osm_segments:
        if segment["tags"] & aliases and segment["key"] not in seen:
            seen.add(segment["key"])
            segments.append(segment["points"])
    return segments


def merge_chains(first, second):
    if not first:
        return list(second)
    if not second:
        return list(first)
    result = list(first)
    if math.dist(result[-1], second[0]) > 1e-9:
        result.append(second[0])
    result.extend(second[1:])
    return dedupe_consecutive(result)


def orient_chain_towards(chain, target_point):
    if not chain:
        return []
    if math.dist(chain[0], target_point) <= math.dist(chain[-1], target_point):
        return list(chain)
    return list(reversed(chain))


def choose_leaf(nodes, adjacency, scorer):
    leaves = [node_id for node_id in nodes if len(adjacency[node_id]) == 1]
    return min(leaves, key=lambda node_id: scorer(nodes[node_id]))


def leaf_nodes(node_points, adjacency):
    return [node_id for node_id in node_points if len(adjacency[node_id]) == 1]


def branch_line(base_points, chain):
    info = locate_chain_on_base(base_points, chain)
    branch = dedupe_consecutive(
        [base_points[info["start_idx"]]]
        + info["chain"]
        + [base_points[info["end_idx"]]]
    )
    return branch, info


def choose_chord_track(chord_segments, south_targets, north_targets):
    node_points, edges, adjacency = build_route_graph(
        chord_segments, snap_tol=EXACT_TRACK_SNAP
    )
    if not edges:
        return []

    leaves = leaf_nodes(node_points, adjacency)
    south_tree = cKDTree(np.asarray(south_targets, dtype=float))
    north_tree = cKDTree(np.asarray(north_targets, dtype=float))
    best = None

    for index, start in enumerate(leaves):
        for end in leaves[index + 1 :]:
            path_edges, distance = shortest_path_between_nodes(
                start, end, adjacency, edges
            )
            if not path_edges:
                continue
            path = path_points_from_edges(path_edges, edges)
            for candidate in (path, list(reversed(path))):
                south_gap, _ = south_tree.query(candidate[0])
                north_gap, _ = north_tree.query(candidate[-1])
                score = (
                    float(south_gap + north_gap),
                    float(north_gap),
                    float(south_gap),
                    float(distance),
                )
                if best is None or score < best["score"]:
                    best = {"score": score, "points": candidate}
    return best["points"] if best else []


def build_kaeng_branch(osm_segments, ban_points, ubon_points):
    khlong_segments = segments_by_aliases(osm_segments, KHLONG19_ALIASES)
    nodes, edges, adjacency = build_route_graph(khlong_segments)
    if not edges:
        return []

    leaves = leaf_nodes(nodes, adjacency)
    ban_tree = cKDTree(np.asarray(ban_points, dtype=float))
    south_leaf = min(leaves, key=lambda node_id: ban_tree.query(nodes[node_id])[0])
    north_candidates = [nodes[node_id] for node_id in leaves if node_id != south_leaf]

    chord_chain = choose_chord_track(
        segments_by_aliases(osm_segments, KAENG_CHORD_ALIASES),
        north_candidates,
        ubon_points,
    )
    if not chord_chain:
        return []

    chord_chain = orient_chain_towards(
        chord_chain,
        min(north_candidates, key=lambda point: math.dist(point, chord_chain[0])),
    )
    north_leaf = min(
        [node_id for node_id in leaves if node_id != south_leaf],
        key=lambda node_id: math.dist(nodes[node_id], chord_chain[0]),
    )

    khlong_path_edges, _ = shortest_path_between_nodes(
        south_leaf, north_leaf, adjacency, edges
    )
    khlong_chain = path_points_from_edges(khlong_path_edges, edges)
    khlong_chain = orient_chain_towards(
        khlong_chain, ban_points[ban_tree.query(khlong_chain[0])[1]]
    )

    chord_chain = orient_chain_towards(chord_chain, khlong_chain[-1])
    chord_join_idx = min(
        range(len(chord_chain)),
        key=lambda idx: math.dist(chord_chain[idx], khlong_chain[-1]),
    )
    if 0 < chord_join_idx < len(chord_chain):
        chord_chain = chord_chain[chord_join_idx:]
    return merge_chains(khlong_chain, chord_chain)


def collect_pha_sadet_chain(osm_segments):
    candidates = {}
    for segment in osm_segments:
        if (
            min_point_distance(segment["points"], PHA_SADET_CENTER) <= PHA_SADET_RADIUS
            and segment["far_fraction"] >= PHA_SADET_FAR_FRACTION
        ):
            candidates[segment["key"]] = segment["points"]
    if not candidates:
        return []
    return max(
        candidates.values(),
        key=lambda points: (
            math.dist(points[0], points[-1]) / polyline_length(points),
            -polyline_length(points),
        ),
    )


def locate_chain_on_base(base_points, chain):
    base_tree = cKDTree(np.asarray(base_points, dtype=float))
    best = None
    for candidate in (chain, list(reversed(chain))):
        start_distance, start_idx = base_tree.query(candidate[0])
        end_distance, end_idx = base_tree.query(candidate[-1])
        start_idx = int(start_idx)
        end_idx = int(end_idx)
        if start_idx >= end_idx:
            continue
        score = (float(start_distance + end_distance), -(end_idx - start_idx))
        if best is None or score < best["score"]:
            best = {
                "score": score,
                "start_idx": start_idx,
                "end_idx": end_idx,
                "chain": list(candidate),
                "start_distance": float(start_distance),
                "end_distance": float(end_distance),
            }

    if best is None:
        raise ValueError("Failed to orient splice chain against base line")

    return best


def splice_line(base_points, chain):
    best = locate_chain_on_base(base_points, chain)

    replacement = dedupe_consecutive(
        [base_points[best["start_idx"]]]
        + best["chain"]
        + [base_points[best["end_idx"]]]
    )
    merged = dedupe_consecutive(
        base_points[: best["start_idx"]]
        + replacement
        + base_points[best["end_idx"] + 1 :]
    )
    return merged, best


def main():
    with open("20260428RailwayMapofThailand.kml", encoding="utf-8") as file_obj:
        srt_kml = file_obj.read()
    with open("hotosm_tha_railways_lines_kml.kml", encoding="utf-8") as file_obj:
        osm_kml = file_obj.read()

    srt_points = []
    for block in re.findall(r"<coordinates>(.*?)</coordinates>", srt_kml, re.DOTALL):
        srt_points.extend(parse_coordinates(block))
    srt_tree = cKDTree(np.asarray(srt_points, dtype=float))

    osm_segments = parse_osm_segments(osm_kml, srt_tree)
    srt_placemarks, srt_by_name = parse_srt_placemarks(srt_kml)

    lopburi_chain = single_track_path(
        segments_by_aliases(osm_segments, LOPBURI_ALIASES)
    )
    chiang_mai_points, chiang_info = splice_line(
        srt_by_name["Chiang Mai"]["points"], lopburi_chain
    )
    srt_by_name["Chiang Mai"]["placemark"] = replace_geometry(
        srt_by_name["Chiang Mai"]["placemark"],
        make_geometry([chiang_mai_points]),
    )

    kaeng_branch = build_kaeng_branch(
        osm_segments,
        srt_by_name["Ban Khlong Luk Border"]["points"],
        srt_by_name["Ubon Ratchathani"]["points"],
    )
    ban_tree = cKDTree(
        np.asarray(srt_by_name["Ban Khlong Luk Border"]["points"], dtype=float)
    )
    south_distance, south_idx = ban_tree.query(kaeng_branch[0])
    if float(south_distance) > 1e-9:
        kaeng_branch = dedupe_consecutive(
            [srt_by_name["Ban Khlong Luk Border"]["points"][int(south_idx)]]
            + kaeng_branch
        )
    ban_branch_geometry = make_geometry(
        [srt_by_name["Ban Khlong Luk Border"]["points"], kaeng_branch]
    )
    srt_by_name["Ban Khlong Luk Border"]["placemark"] = replace_geometry(
        srt_by_name["Ban Khlong Luk Border"]["placemark"],
        ban_branch_geometry,
    )

    pha_sadet_chain = collect_pha_sadet_chain(osm_segments)
    ubon_branch, ubon_info = branch_line(
        srt_by_name["Ubon Ratchathani"]["points"], pha_sadet_chain
    )
    srt_by_name["Ubon Ratchathani"]["placemark"] = replace_geometry(
        srt_by_name["Ubon Ratchathani"]["placemark"],
        make_geometry([srt_by_name["Ubon Ratchathani"]["points"], ubon_branch]),
    )

    schema1 = re.search(
        r'<Schema name="20260410railwaymapofthailand__lines".*?</Schema>',
        srt_kml,
        re.DOTALL,
    ).group(0)
    final_placemarks = [record["placemark"] for record in srt_placemarks]

    output = f'''<?xml version="1.0" encoding="utf-8" ?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document id="root_doc">
  <name>Thailand Railways - Complete Map</name>
  <description>SRT named routes (16 lines, red) with Lopburi Bypass merged into Chiang Mai, Kaeng Khoi chord added to Ban Khlong Luk Border, and Pha Sadet straightened in Ubon Ratchathani.</description>
  {schema1}
  <Folder>
    <name>Thailand Railways</name>
    {'\n'.join(final_placemarks)}
  </Folder>
</Document>
</kml>'''

    with open("thailand_railways_combined.kml", "w", encoding="utf-8") as file_obj:
        file_obj.write(output)

    print("Integrated sections: 3")
    print(
        f"  Chiang Mai ← Lopburi Bypass Line: {len(lopburi_chain)} pts, "
        f"splice {chiang_info['start_idx']}:{chiang_info['end_idx']}"
    )
    print(
        f"  Ban Khlong Luk Border ← Kaeng Khoi branch: {len(kaeng_branch)} pts, south anchor {int(south_idx)}"
    )
    print(
        f"  Ubon Ratchathani ← Pha Sadet Tunnel: {len(pha_sadet_chain)} pts, "
        f"branch {ubon_info['start_idx']}:{ubon_info['end_idx']}"
    )
    print(f"Total Placemarks: {len(final_placemarks)}")
    print(f"Output: {len(output.encode('utf-8')) // 1024} KB")


if __name__ == "__main__":
    main()
