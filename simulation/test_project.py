from app.services.geo_utils import project_onto_polyline

coords = [[100.541605, 13.803726], [100.541678, 13.803905], [100.541686804, 13.803926692]]
point_lon, point_lat = 100.5416, 13.8038

dist, frac = project_onto_polyline(coords, point_lon, point_lat)
print(dist, frac)
