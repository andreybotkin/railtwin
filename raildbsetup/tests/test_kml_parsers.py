from pathlib import Path

from app.infrastructure.parsers.kml_parser import parse_kml_routes
from app.infrastructure.parsers.kml_station_parser import parse_stations_kml


def test_chuk_samet_route_is_classified_as_eastern() -> None:
    payload = b"""<?xml version='1.0'?>
    <kml xmlns='http://www.opengis.net/kml/2.2'><Document><Folder>
      <name>Thailand Railways</name><Placemark><name>Chuk Samet</name>
      <LineString><coordinates>100.0,13.0 101.0,12.0</coordinates></LineString>
      </Placemark></Folder></Document></kml>"""

    routes = parse_kml_routes(payload)

    assert len(routes) == 1
    assert routes[0].route_type == "eastern"


def test_station_parser_keeps_latest_duplicate_coordinate(tmp_path: Path) -> None:
    source = tmp_path / "stations.kml"
    source.write_text(
        """<?xml version='1.0'?>
        <kml xmlns='http://www.opengis.net/kml/2.2'><Document><Folder>
          <name>Southern</name>
          <Placemark><name>Huai Rong</name><ExtendedData>
            <Data name='name_en'><value>Huai Rong</value></Data>
            <Data name='lat'><value>17.0</value></Data>
            <Data name='lon'><value>102.0</value></Data>
          </ExtendedData></Placemark>
          <Placemark><name>Huai Rong</name><ExtendedData>
            <Data name='name_en'><value>Huai Rong</value></Data>
            <Data name='lat'><value>13.3374</value></Data>
            <Data name='lon'><value>99.84836</value></Data>
          </ExtendedData></Placemark>
        </Folder></Document></kml>""",
        encoding="utf-8",
    )

    parsed = parse_stations_kml(source)

    assert len(parsed.stations) == 1
    assert parsed.stations[0].lat == 13.3374
    assert parsed.stations[0].lon == 99.84836


def test_canonical_bang_chak_is_the_southern_railway_station() -> None:
    source = Path(__file__).parents[1] / "railroad/20260428Thai_railway_stations.kml"

    parsed = parse_stations_kml(source)
    station = next(item for item in parsed.stations if item.name == "Bang Chak")

    # This must not regress to the identically named Bangkok BTS station.
    assert station.lat == 13.16
    assert station.lon == 99.8994444


def test_schedule_stations_do_not_collapse_to_distant_namesakes() -> None:
    source = Path(__file__).parents[1] / "railroad/20260428Thai_railway_stations.kml"

    parsed = parse_stations_kml(source)
    by_name = {station.name: station for station in parsed.stations}

    expected_coordinates = {
        "Noen Sawat": (15.62418, 102.45952),
        "Khlong Yan": (9.05793, 99.024327),
        "Ban Nong Sua": (13.971937, 99.693045),
        "Nong Suea": (14.052196, 101.570486),
    }
    for name, (expected_lat, expected_lon) in expected_coordinates.items():
        assert by_name[name].lat == expected_lat
        assert by_name[name].lon == expected_lon

    assert by_name["Noen Sawat"].lat != by_name["Non Sa-at"].lat
    assert by_name["Khlong Yan"].lat != by_name["Khlong Ya"].lat
    assert by_name["Nong Suea"].lon != by_name["Ban Nong Sua"].lon


def test_ban_phai_na_bun_connectors_join_both_mainline_directions() -> None:
    source = Path(__file__).parents[1] / "railroad/route_extensions.kml"

    routes = parse_kml_routes(source.read_bytes())
    by_name = {route.name: route for route in routes}
    toward_nong_bua = by_name["Ban Phai Na Bun - Nong Bua Junction connector"]
    toward_kaeng_khoi = by_name["Ban Phai Na Bun - Kaeng Khoi Junction connector"]

    ban_phai = (100.9830144, 14.5487424)
    mainline_join = (100.972549, 14.565411)
    nong_bua = (100.9627994, 14.5557708)
    kaeng_khoi = (101.0053349, 14.5874804)

    for route in (toward_nong_bua, toward_kaeng_khoi):
        assert abs(route.coords[0][0] - ban_phai[0]) < 0.0001
        assert abs(route.coords[0][1] - ban_phai[1]) < 0.0001
        assert mainline_join in route.coords
        assert route.route_type == "northeastern"

    assert toward_nong_bua.coords[-1] == nong_bua
    assert toward_kaeng_khoi.coords[-1] == kaeng_khoi
