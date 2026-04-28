#!/usr/bin/env python3
"""
Fetch exact coordinates for Thai railway stations from OpenStreetMap Overpass API.

Usage:
    pip install requests
    python fetch_and_update_coords.py

Pipeline:
1. Overpass API -> all railway nodes in Thailand
2. Match by Thai name (raw + normalized) and English name (exact + fuzzy)
3. Nominatim fallback for unmatched
4. Preserves Google Places verified coords
"""

import json
import time
from difflib import SequenceMatcher

import requests

INPUT_FILE = "thai_railway_stations_full.json"
OUTPUT_FILE = "thai_railway_stations_full.json"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


def fetch_osm():
    query = """[out:json][timeout:180];
    area["ISO3166-1"="TH"]->.a;
    (node["railway"="station"](area.a);node["railway"="halt"](area.a);node["railway"="stop"](area.a););
    out body;"""
    print("Fetching from Overpass API...")
    r = requests.get(OVERPASS_URL, params={"data": query}, timeout=200)
    r.raise_for_status()
    nodes = []
    for el in r.json().get("elements", []):
        t = el.get("tags", {})
        nodes.append(
            {
                "lat": el["lat"],
                "lon": el["lon"],
                "name_th": t.get("name:th", t.get("name", "")),
                "name_en": t.get("name:en", ""),
            }
        )
    print(f"  {len(nodes)} OSM nodes found")
    return nodes


def norm(s):
    s = s.strip().lower()
    for p in ["สถานีรถไฟ", "ชุมทาง", "ป้ายหยุดรถ"]:
        s = s.replace(p, "")
    return s.strip()


def sim(a, b):
    return SequenceMatcher(None, a, b).ratio()


def match(stations, osm):
    by_th = {norm(o["name_th"]): o for o in osm if o["name_th"].strip()}
    by_th_raw = {o["name_th"].strip(): o for o in osm if o["name_th"].strip()}
    by_en = {}
    for o in osm:
        n = o["name_en"].strip().lower()
        if n and n not in by_en:
            by_en[n] = o
    matched, unmatched = 0, []
    for s in stations:
        if s.get("coord_source") == "google_places":
            matched += 1
            continue
        th_raw = s.get("name_th", "").strip()
        th = norm(s.get("name_th", ""))
        en = s["name_en"].lower().strip()
        sched = s.get("schedule_name", "").lower().strip()
        found = None
        if th_raw and th_raw in by_th_raw:
            found = by_th_raw[th_raw]
            src = "osm_th_raw"
        elif th and th in by_th:
            found = by_th[th]
            src = "osm_th"
        elif en and en in by_en:
            found = by_en[en]
            src = "osm_en"
        elif sched and sched in by_en:
            found = by_en[sched]
            src = "osm_sched"
        else:
            # fuzzy Thai
            best, bf = 0, None
            if th:
                for k, o in by_th.items():
                    sc = sim(th, k)
                    if sc > best:
                        best, bf = sc, o
            if best > 0.80:
                found = bf
                src = f"osm_fuzzy_th_{best:.2f}"
            else:
                best, bf = 0, None
                if en:
                    for k, o in by_en.items():
                        sc = sim(en, k)
                        if sc > best:
                            best, bf = sc, o
                if best > 0.80:
                    found = bf
                    src = f"osm_fuzzy_en_{best:.2f}"
        if found:
            s["lat"] = round(found["lat"], 7)
            s["lon"] = round(found["lon"], 7)
            s["coord_source"] = src
            if not s.get("name_th") and found.get("name_th"):
                s["name_th"] = found["name_th"]
            matched += 1
        else:
            unmatched.append(s["name_en"])
    return matched, unmatched


def nominatim(station):
    queries = []
    if station.get("name_th"):
        queries.append(f"{station['name_th']} สถานีรถไฟ")
    queries.append(f"{station['name_en']} railway station Thailand")
    if station.get("province"):
        queries.append(f"{station['name_en']} {station['province']} Thailand")
    for q in queries:
        try:
            r = requests.get(
                NOMINATIM_URL,
                params={"q": q, "format": "json", "countrycodes": "TH", "limit": 1},
                headers={"User-Agent": "ThaiRailGeocoder/1.0"},
                timeout=10,
            )
            res = r.json()
            if res:
                lat, lon = float(res[0]["lat"]), float(res[0]["lon"])
                if 5.5 < lat < 21 and 97 < lon < 106:
                    return lat, lon
        except Exception as e:
            print(f"  Nominatim err {station['name_en']}: {e}")
        time.sleep(1.1)
    return None, None


def main():
    with open(INPUT_FILE, encoding="utf-8") as f:
        data = json.load(f)
    stations = data["stations"]
    print(f"Loaded {len(stations)} stations")
    osm = fetch_osm()
    m, um = match(stations, osm)
    print(f"OSM matched: {m}/{len(stations)}, unmatched: {len(um)}")
    if um:
        print(f"Nominatim for {len(um)} stations...")
        nm = 0
        for s in stations:
            if s["name_en"] in um:
                lat, lon = nominatim(s)
                if lat:
                    s["lat"], s["lon"] = round(lat, 7), round(lon, 7)
                    s["coord_source"] = "nominatim"
                    nm += 1
                    print(f"  + {s['name_en']}")
                else:
                    if s.get("coord_source") != "google_places":
                        s["coord_source"] = "unverified"
                    print(f"  - {s['name_en']}")
        print(f"  Nominatim: {nm}/{len(um)}")
    data["total_stations"] = len(stations)
    osm_c = sum(1 for s in stations if str(s.get("coord_source", "")).startswith("osm"))
    data["coords_osm"] = osm_c
    data["coords_google"] = sum(
        1 for s in stations if s.get("coord_source") == "google_places"
    )
    data["coords_nominatim"] = sum(
        1 for s in stations if s.get("coord_source") == "nominatim"
    )
    data["coords_unverified"] = sum(
        1
        for s in stations
        if s.get("coord_source") in ("unverified", "estimated", "needs_geocoding")
    )
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(
        f"\nSaved {OUTPUT_FILE}: {len(stations)} stations, OSM={osm_c}, Google={data['coords_google']}, Nominatim={data['coords_nominatim']}, Unverified={data['coords_unverified']}"
    )


if __name__ == "__main__":
    main()
