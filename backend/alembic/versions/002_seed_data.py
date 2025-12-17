"""Seed data migration - Thailand Railway data

Revision ID: 002
Revises: 001
Create Date: 2024-01-01 00:01:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Thailand Railway Stations Data (real coordinates)
STATIONS = [
    # Bangkok and Central
    {"name": "Bangkok Hua Lamphong", "name_th": "กรุงเทพ (หัวลำโพง)", "code": "BKK", "lon": 100.5167, "lat": 13.7383, "city": "Bangkok", "province": "Bangkok"},
    {"name": "Bang Sue Grand", "name_th": "กลางบางซื่อ", "code": "BSG", "lon": 100.5283, "lat": 13.8028, "city": "Bangkok", "province": "Bangkok"},
    {"name": "Don Mueang", "name_th": "ดอนเมือง", "code": "DMG", "lon": 100.5897, "lat": 13.9125, "city": "Bangkok", "province": "Bangkok"},
    {"name": "Rangsit", "name_th": "รังสิต", "code": "RST", "lon": 100.6089, "lat": 13.9650, "city": "Pathum Thani", "province": "Pathum Thani"},
    
    # Northern Line
    {"name": "Ayutthaya", "name_th": "อยุธยา", "code": "AYA", "lon": 100.5583, "lat": 14.3533, "city": "Ayutthaya", "province": "Ayutthaya"},
    {"name": "Lopburi", "name_th": "ลพบุรี", "code": "LBI", "lon": 100.6167, "lat": 14.7989, "city": "Lopburi", "province": "Lopburi"},
    {"name": "Nakhon Sawan", "name_th": "นครสวรรค์", "code": "NSW", "lon": 100.1167, "lat": 15.7000, "city": "Nakhon Sawan", "province": "Nakhon Sawan"},
    {"name": "Phitsanulok", "name_th": "พิษณุโลก", "code": "PSL", "lon": 100.2667, "lat": 16.8167, "city": "Phitsanulok", "province": "Phitsanulok"},
    {"name": "Uttaradit", "name_th": "อุตรดิตถ์", "code": "UTD", "lon": 100.1000, "lat": 17.6167, "city": "Uttaradit", "province": "Uttaradit"},
    {"name": "Lampang", "name_th": "ลำปาง", "code": "LPG", "lon": 99.5000, "lat": 18.2833, "city": "Lampang", "province": "Lampang"},
    {"name": "Lamphun", "name_th": "ลำพูน", "code": "LPN", "lon": 99.0000, "lat": 18.5667, "city": "Lamphun", "province": "Lamphun"},
    {"name": "Chiang Mai", "name_th": "เชียงใหม่", "code": "CNX", "lon": 98.9833, "lat": 18.7667, "city": "Chiang Mai", "province": "Chiang Mai"},
    
    # Northeastern Line
    {"name": "Saraburi", "name_th": "สระบุรี", "code": "SBI", "lon": 100.9167, "lat": 14.5333, "city": "Saraburi", "province": "Saraburi"},
    {"name": "Pak Chong", "name_th": "ปากช่อง", "code": "PKC", "lon": 101.4167, "lat": 14.7000, "city": "Pak Chong", "province": "Nakhon Ratchasima"},
    {"name": "Nakhon Ratchasima", "name_th": "นครราชสีมา", "code": "NKR", "lon": 102.1000, "lat": 14.9667, "city": "Nakhon Ratchasima", "province": "Nakhon Ratchasima"},
    {"name": "Buri Ram", "name_th": "บุรีรัมย์", "code": "BRM", "lon": 103.1000, "lat": 14.9833, "city": "Buri Ram", "province": "Buri Ram"},
    {"name": "Surin", "name_th": "สุรินทร์", "code": "SRN", "lon": 103.4833, "lat": 14.8667, "city": "Surin", "province": "Surin"},
    {"name": "Ubon Ratchathani", "name_th": "อุบลราชธานี", "code": "UBN", "lon": 104.8500, "lat": 15.2500, "city": "Ubon Ratchathani", "province": "Ubon Ratchathani"},
    {"name": "Khon Kaen", "name_th": "ขอนแก่น", "code": "KKN", "lon": 102.8333, "lat": 16.4333, "city": "Khon Kaen", "province": "Khon Kaen"},
    {"name": "Udon Thani", "name_th": "อุดรธานี", "code": "UDT", "lon": 102.8167, "lat": 17.4150, "city": "Udon Thani", "province": "Udon Thani"},
    {"name": "Nong Khai", "name_th": "หนองคาย", "code": "NKI", "lon": 102.7500, "lat": 17.8667, "city": "Nong Khai", "province": "Nong Khai"},
    
    # Southern Line
    {"name": "Nakhon Pathom", "name_th": "นครปฐม", "code": "NPT", "lon": 100.0500, "lat": 13.8167, "city": "Nakhon Pathom", "province": "Nakhon Pathom"},
    {"name": "Ratchaburi", "name_th": "ราชบุรี", "code": "RBI", "lon": 99.8333, "lat": 13.5333, "city": "Ratchaburi", "province": "Ratchaburi"},
    {"name": "Phetchaburi", "name_th": "เพชรบุรี", "code": "PBR", "lon": 99.9500, "lat": 13.1167, "city": "Phetchaburi", "province": "Phetchaburi"},
    {"name": "Hua Hin", "name_th": "หัวหิน", "code": "HHN", "lon": 99.9500, "lat": 12.5667, "city": "Hua Hin", "province": "Prachuap Khiri Khan"},
    {"name": "Chumphon", "name_th": "ชุมพร", "code": "CPN", "lon": 99.1833, "lat": 10.5000, "city": "Chumphon", "province": "Chumphon"},
    {"name": "Surat Thani", "name_th": "สุราษฎร์ธานี", "code": "SRT", "lon": 99.3167, "lat": 9.1333, "city": "Surat Thani", "province": "Surat Thani"},
    {"name": "Nakhon Si Thammarat", "name_th": "นครศรีธรรมราช", "code": "NST", "lon": 100.0000, "lat": 8.4333, "city": "Nakhon Si Thammarat", "province": "Nakhon Si Thammarat"},
    {"name": "Hat Yai", "name_th": "หาดใหญ่", "code": "HDY", "lon": 100.4667, "lat": 7.0167, "city": "Hat Yai", "province": "Songkhla"},
    {"name": "Sungai Kolok", "name_th": "สุไหงโก-ลก", "code": "SGK", "lon": 101.9667, "lat": 6.0333, "city": "Sungai Kolok", "province": "Narathiwat"},
    
    # Eastern Line
    {"name": "Chachoengsao", "name_th": "ฉะเชิงเทรา", "code": "CCS", "lon": 101.0667, "lat": 13.6833, "city": "Chachoengsao", "province": "Chachoengsao"},
    {"name": "Pattaya", "name_th": "พัทยา", "code": "PTY", "lon": 100.8833, "lat": 12.9333, "city": "Pattaya", "province": "Chonburi"},
    {"name": "Aranyaprathet", "name_th": "อรัญประเทศ", "code": "APT", "lon": 102.5000, "lat": 13.6833, "city": "Aranyaprathet", "province": "Sa Kaeo"},
]

# Thailand Railway Routes
ROUTES = [
    {
        "name": "Northern Line",
        "name_th": "สายเหนือ",
        "route_type": "northern",
        "distance_km": 751,
        "color": "#E53935",
        "stations": ["BKK", "BSG", "DMG", "RST", "AYA", "LBI", "NSW", "PSL", "UTD", "LPG", "LPN", "CNX"],
    },
    {
        "name": "Northeastern Line (Ubon)",
        "name_th": "สายตะวันออกเฉียงเหนือ (อุบล)",
        "route_type": "northeastern",
        "distance_km": 575,
        "color": "#1E88E5",
        "stations": ["BKK", "BSG", "RST", "AYA", "SBI", "PKC", "NKR", "BRM", "SRN", "UBN"],
    },
    {
        "name": "Northeastern Line (Nong Khai)",
        "name_th": "สายตะวันออกเฉียงเหนือ (หนองคาย)",
        "route_type": "northeastern",
        "distance_km": 624,
        "color": "#43A047",
        "stations": ["BKK", "BSG", "RST", "AYA", "SBI", "PKC", "NKR", "KKN", "UDT", "NKI"],
    },
    {
        "name": "Southern Line",
        "name_th": "สายใต้",
        "route_type": "southern",
        "distance_km": 990,
        "color": "#FB8C00",
        "stations": ["BKK", "BSG", "NPT", "RBI", "PBR", "HHN", "CPN", "SRT", "NST", "HDY", "SGK"],
    },
    {
        "name": "Eastern Line",
        "name_th": "สายตะวันออก",
        "route_type": "eastern",
        "distance_km": 255,
        "color": "#8E24AA",
        "stations": ["BKK", "CCS", "PTY", "APT"],
    },
]

# Sample Trains
TRAINS = [
    # Northern Line Trains
    {"train_number": "9", "train_type": "special_express", "name": "Northern Express", "capacity": 500, "route_idx": 0},
    {"train_number": "13", "train_type": "special_express", "name": "Chiang Mai Special", "capacity": 500, "route_idx": 0},
    {"train_number": "51", "train_type": "rapid", "name": "Northern Rapid", "capacity": 400, "route_idx": 0},
    {"train_number": "109", "train_type": "ordinary", "name": None, "capacity": 300, "route_idx": 0},
    
    # Northeastern Line Trains (Ubon)
    {"train_number": "21", "train_type": "special_express", "name": "Isan Express", "capacity": 500, "route_idx": 1},
    {"train_number": "67", "train_type": "rapid", "name": "Ubon Rapid", "capacity": 400, "route_idx": 1},
    {"train_number": "139", "train_type": "ordinary", "name": None, "capacity": 300, "route_idx": 1},
    
    # Northeastern Line Trains (Nong Khai)
    {"train_number": "25", "train_type": "special_express", "name": "Nong Khai Express", "capacity": 500, "route_idx": 2},
    {"train_number": "75", "train_type": "rapid", "name": "Khon Kaen Rapid", "capacity": 400, "route_idx": 2},
    {"train_number": "133", "train_type": "ordinary", "name": None, "capacity": 300, "route_idx": 2},
    
    # Southern Line Trains
    {"train_number": "31", "train_type": "special_express", "name": "Southern Star", "capacity": 500, "route_idx": 3},
    {"train_number": "37", "train_type": "special_express", "name": "Hat Yai Express", "capacity": 500, "route_idx": 3},
    {"train_number": "83", "train_type": "rapid", "name": "Southern Rapid", "capacity": 400, "route_idx": 3},
    {"train_number": "171", "train_type": "ordinary", "name": None, "capacity": 300, "route_idx": 3},
    
    # Eastern Line Trains
    {"train_number": "281", "train_type": "rapid", "name": "Eastern Rapid", "capacity": 400, "route_idx": 4},
    {"train_number": "283", "train_type": "ordinary", "name": None, "capacity": 300, "route_idx": 4},
]


def upgrade() -> None:
    """Insert seed data for Thailand Railway."""
    conn = op.get_bind()
    
    # Insert stations
    station_ids = {}
    for station in STATIONS:
        result = conn.execute(
            sa.text("""
                INSERT INTO stations (name, name_th, code, location, city, province, facilities)
                VALUES (:name, :name_th, :code, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), :city, :province, :facilities)
                RETURNING id
            """),
            {
                "name": station["name"],
                "name_th": station["name_th"],
                "code": station["code"],
                "lon": station["lon"],
                "lat": station["lat"],
                "city": station["city"],
                "province": station["province"],
                "facilities": '{"parking": true, "toilet": true, "wifi": false}',
            },
        )
        station_ids[station["code"]] = result.fetchone()[0]
    
    # Insert routes with line geometry
    route_ids = []
    for route in ROUTES:
        # Build line geometry from station coordinates
        coords = []
        for code in route["stations"]:
            station = next(s for s in STATIONS if s["code"] == code)
            coords.append(f"{station['lon']} {station['lat']}")
        linestring = f"LINESTRING({', '.join(coords)})"
        
        result = conn.execute(
            sa.text("""
                INSERT INTO routes (name, name_th, route_type, distance_km, color, line_geometry)
                VALUES (:name, :name_th, :route_type, :distance_km, :color, ST_SetSRID(ST_GeomFromText(:geom), 4326))
                RETURNING id
            """),
            {
                "name": route["name"],
                "name_th": route["name_th"],
                "route_type": route["route_type"],
                "distance_km": route["distance_km"],
                "color": route["color"],
                "geom": linestring,
            },
        )
        route_id = result.fetchone()[0]
        route_ids.append(route_id)
        
        # Insert route_stations
        total_distance = route["distance_km"]
        num_stations = len(route["stations"])
        for seq, code in enumerate(route["stations"]):
            distance = (total_distance / (num_stations - 1)) * seq if num_stations > 1 else 0
            conn.execute(
                sa.text("""
                    INSERT INTO route_stations (route_id, station_id, sequence, distance_from_start)
                    VALUES (:route_id, :station_id, :sequence, :distance)
                """),
                {
                    "route_id": route_id,
                    "station_id": station_ids[code],
                    "sequence": seq,
                    "distance": round(distance, 2),
                },
            )
    
    # Insert trains
    train_ids = []
    for train in TRAINS:
        result = conn.execute(
            sa.text("""
                INSERT INTO trains (train_number, train_type, name, capacity, current_route_id)
                VALUES (:number, :type, :name, :capacity, :route_id)
                RETURNING id
            """),
            {
                "number": train["train_number"],
                "type": train["train_type"],
                "name": train["name"],
                "capacity": train["capacity"],
                "route_id": route_ids[train["route_idx"]],
            },
        )
        train_ids.append((result.fetchone()[0], train["route_idx"]))
    
    # Insert schedules (simplified schedule generation)
    # For each train, create schedule entries for each station on its route
    base_times = {
        "special_express": [
            ("06:00", "06:05"),
            ("18:00", "18:05"),
        ],
        "rapid": [
            ("07:30", "07:40"),
            ("14:00", "14:10"),
        ],
        "ordinary": [
            ("05:00", "05:15"),
            ("10:00", "10:15"),
        ],
    }
    
    for train_id, route_idx in train_ids:
        route = ROUTES[route_idx]
        route_id = route_ids[route_idx]
        train = next(t for t in TRAINS if route_ids[t["route_idx"]] == route_id)
        
        # Get departure times for this train type
        times = base_times.get(train["train_type"], base_times["ordinary"])
        
        for base_dep, _ in times[:1]:  # Use first departure time
            hour, minute = map(int, base_dep.split(":"))
            stations_on_route = route["stations"]
            
            # Calculate time between stations (simplified)
            total_minutes = 60 * 10  # Assume 10 hours for full journey
            minutes_per_station = total_minutes // (len(stations_on_route) - 1) if len(stations_on_route) > 1 else 0
            
            for seq, code in enumerate(stations_on_route):
                arr_minutes = hour * 60 + minute + (seq * minutes_per_station)
                dep_minutes = arr_minutes + 5  # 5 minute stop
                
                arr_hour = (arr_minutes // 60) % 24
                arr_min = arr_minutes % 60
                dep_hour = (dep_minutes // 60) % 24
                dep_min = dep_minutes % 60
                
                conn.execute(
                    sa.text("""
                        INSERT INTO schedules (train_id, station_id, arrival_time, departure_time, day_of_week, platform, sequence)
                        VALUES (:train_id, :station_id, :arrival, :departure, :days, :platform, :seq)
                    """),
                    {
                        "train_id": train_id,
                        "station_id": station_ids[code],
                        "arrival": f"{arr_hour:02d}:{arr_min:02d}:00" if seq > 0 else None,
                        "departure": f"{dep_hour:02d}:{dep_min:02d}:00" if seq < len(stations_on_route) - 1 else None,
                        "days": [0, 1, 2, 3, 4, 5, 6],  # All days
                        "platform": str((seq % 4) + 1),
                        "seq": seq,
                    },
                )


def downgrade() -> None:
    """Remove seed data."""
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM schedules"))
    conn.execute(sa.text("DELETE FROM train_positions"))
    conn.execute(sa.text("DELETE FROM trains"))
    conn.execute(sa.text("DELETE FROM route_stations"))
    conn.execute(sa.text("DELETE FROM routes"))
    conn.execute(sa.text("DELETE FROM stations"))
