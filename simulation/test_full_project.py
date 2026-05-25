import asyncio
import json

import redis.asyncio as redis

from app.core.config import settings
from app.services import geo_utils
from app.services.reference_data import RedisReferenceReader


async def main():
    redis_client = redis.Redis(host='redis', port=6379, db=0)
    reader = RedisReferenceReader(redis_client)
    route_data = await reader._redis.get(f"{settings.reference_data_namespace}:route_geometry:by_route:1")
    route_data = json.loads(route_data)
    coords = route_data["coords"]

    polyline = [[float(p[0]), float(p[1])] for p in coords]

    point_lon, point_lat = 100.541605, 13.803726 # Bangkok
    dist, frac = geo_utils.project_onto_polyline(polyline, point_lon, point_lat)

asyncio.run(main())
