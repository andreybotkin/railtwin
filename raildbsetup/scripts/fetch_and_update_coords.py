#!/usr/bin/env python3
"""
Fetch exact coordinates for Thai railway stations from OpenStreetMap Overpass API
and update the JSON file.

Usage:
    pip install requests
    python fetch_and_update_coords.py

This script:
1. Queries Overpass API for ALL railway stations/halts in Thailand
2. Matches them with our station list by Thai name
3. Updates coordinates in the JSON file
"""

import requests
import json
import re
import time
import sys
from difflib import SequenceMatcher

# --- CONFIG ---
INPUT_FILE = "thai_railway_stations_full.json"
OUTPUT_FILE = "thai_railway_stations_full_geocoded.json"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# --- STEP 1: Query Overpass API ---
def fetch_osm_stations():
    """Fetch all railway stations and halts in Thailand from OSM"""
    query = """
    [out:json][timeout:180];
    area["ISO3166-1"="TH"]->.a;
    (
      node["railway"="station"](area.a);
      node["railway"="halt"](area.a);
      node["railway"="stop"](area.a);
    );
    out body;
    """
    print("Fetching stations from Overpass API...")
    resp = requests.get(OVERPASS_URL, params={"data": query}, timeout=200)
    resp.raise_for_status()
    data = resp.json()
    
    stations = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        name_th = tags.get("name:th", tags.get("name", ""))
        name_en = tags.get("name:en", "")
        stations.append({
            "osm_id": el["id"],
            "lat": el["lat"],
            "lon": el["lon"],
            "name_th": name_th,
            "name_en": name_en,
            "operator": tags.get("operator", ""),
            "railway": tags.get("railway", ""),
            "all_tags": tags,
        })
    
    print(f"  Found {len(stations)} OSM railway nodes in Thailand")
    return stations

# --- STEP 2: Match stations ---
def normalize_thai(s):
    """Normalize Thai station name for matching"""
    s = s.strip()
    # Remove common prefixes
    for prefix in ["สถานีรถไฟ", "ชุมทาง", "ป้ายหยุดรถ"]:
        s = s.replace(prefix, "").strip()
    return s

def similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()

def match_stations(our_stations, osm_stations):
    """Match our station list with OSM data"""
    # Build lookup by Thai name
    osm_by_th = {}
    for osm in osm_stations:
        name = normalize_thai(osm["name_th"])
        if name:
            osm_by_th[name] = osm
    
    # Build lookup by English name  
    osm_by_en = {}
    for osm in osm_stations:
        name = osm["name_en"].strip()
        if name:
            osm_by_en[name.lower()] = osm
    
    matched = 0
    unmatched = []
    
    for station in our_stations:
        our_th = normalize_thai(station["name_th"])
        our_en = station["name_en"].lower()
        
        # Try exact Thai name match
        if our_th in osm_by_th:
            osm = osm_by_th[our_th]
            station["lat"] = round(osm["lat"], 7)
            station["lon"] = round(osm["lon"], 7)
            station["coord_source"] = "osm_exact_th"
            matched += 1
            continue
        
        # Try exact English name match
        if our_en in osm_by_en:
            osm = osm_by_en[our_en]
            station["lat"] = round(osm["lat"], 7)
            station["lon"] = round(osm["lon"], 7)
            station["coord_source"] = "osm_exact_en"
            matched += 1
            continue
        
        # Try fuzzy Thai name match
        best_score = 0
        best_osm = None
        for osm_name, osm in osm_by_th.items():
            score = similarity(our_th, osm_name)
            if score > best_score:
                best_score = score
                best_osm = osm
        
        if best_score > 0.75:
            station["lat"] = round(best_osm["lat"], 7)
            station["lon"] = round(best_osm["lon"], 7)
            station["coord_source"] = f"osm_fuzzy_th_{best_score:.2f}"
            matched += 1
            continue
        
        # Try fuzzy English name match
        best_score = 0
        best_osm = None
        for osm_name, osm in osm_by_en.items():
            score = similarity(our_en, osm_name)
            if score > best_score:
                best_score = score
                best_osm = osm
        
        if best_score > 0.75:
            station["lat"] = round(best_osm["lat"], 7)
            station["lon"] = round(best_osm["lon"], 7)
            station["coord_source"] = f"osm_fuzzy_en_{best_score:.2f}"
            matched += 1
            continue
        
        unmatched.append(station["name_en"])
    
    return matched, unmatched

# --- STEP 3: Fallback - Nominatim geocoding ---
def geocode_nominatim(station):
    """Geocode a single station using Nominatim"""
    query = f"{station['name_th']} สถานีรถไฟ {station['province']}"
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": query,
        "format": "json",
        "countrycodes": "TH",
        "limit": 1,
    }
    headers = {"User-Agent": "ThaiRailwayStationsGeocoder/1.0"}
    
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        results = resp.json()
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception as e:
        print(f"  Nominatim error for {station['name_en']}: {e}")
    
    return None, None

# --- MAIN ---
def main():
    # Load our station data
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    stations = data["stations"]
    print(f"Loaded {len(stations)} stations from {INPUT_FILE}")
    
    # Fetch OSM data
    osm_stations = fetch_osm_stations()
    
    # Match
    matched, unmatched = match_stations(stations, osm_stations)
    print(f"\nMatched from OSM: {matched}/{len(stations)}")
    print(f"Unmatched: {len(unmatched)}")
    
    # Fallback: Nominatim for unmatched
    if unmatched:
        print(f"\nGeocoding {len(unmatched)} unmatched stations via Nominatim...")
        nom_matched = 0
        for station in stations:
            if station["name_en"] in unmatched:
                lat, lon = geocode_nominatim(station)
                if lat and lon:
                    station["lat"] = round(lat, 7)
                    station["lon"] = round(lon, 7)
                    station["coord_source"] = "nominatim"
                    nom_matched += 1
                else:
                    station["coord_source"] = "unverified"
                time.sleep(1.1)  # Nominatim rate limit
        
        print(f"  Nominatim matched: {nom_matched}/{len(unmatched)}")
    
    # Update metadata
    total_with = sum(1 for s in stations if s.get("coord_source", "").startswith("osm") or s.get("coord_source") == "nominatim")
    data["stations_with_coordinates"] = len(stations)
    data["stations_verified_from_osm"] = sum(1 for s in stations if s.get("coord_source", "").startswith("osm"))
    data["coordinate_sources"] = "OpenStreetMap Overpass API + Nominatim fallback"
    
    # Save
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"\nSaved to {OUTPUT_FILE}")
    print(f"  OSM verified: {data['stations_verified_from_osm']}")
    print(f"  Total with coords: {data['stations_with_coordinates']}")

if __name__ == "__main__":
    main()
