import math

from django.core.exceptions import ValidationError


MAX_POLYGON_POINTS = 512
FARDECOSMIA_CIRCUMFERENCE_KM = 72_500.0
WORLD_PIXEL_WIDTH_ZOOM_ZERO = 512.0
WORLD_PIXEL_HEIGHT_ZOOM_ZERO = 256.0


def validate_map_polygon(points, *, require_polygon=True):
    if not points:
        if require_polygon:
            raise ValidationError("Нарисуйте контур региона минимум из трёх точек.")
        return []
    if not isinstance(points, list) or not 3 <= len(points) <= MAX_POLYGON_POINTS:
        raise ValidationError(
            f"Контур должен содержать от 3 до {MAX_POLYGON_POINTS} точек."
        )

    normalized = []
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValidationError("Каждая точка контура должна содержать x и y.")
        x, y = point
        if (
            isinstance(x, bool)
            or isinstance(y, bool)
            or not isinstance(x, (int, float))
            or not isinstance(y, (int, float))
            or not 0 <= x <= 1
            or not 0 <= y <= 1
        ):
            raise ValidationError("Координаты точек должны находиться между 0 и 1.")
        normalized.append([round(float(x), 6), round(float(y), 6)])
    return normalized


def polygon_center(points):
    points = validate_map_polygon(points)
    angles = [point[0] * 2 * math.pi for point in points]
    mean_sin = sum(math.sin(angle) for angle in angles) / len(angles)
    mean_cos = sum(math.cos(angle) for angle in angles) / len(angles)
    if abs(mean_sin) < 1e-9 and abs(mean_cos) < 1e-9:
        center_x = sum(point[0] for point in points) / len(points)
    else:
        center_x = (math.atan2(mean_sin, mean_cos) / (2 * math.pi)) % 1

    center_y = sum(point[1] for point in points) / len(points)
    longitude = center_x * 360 - 180
    latitude = 90 - center_y * 180
    return round(longitude, 6), round(latitude, 6)


def normalize_longitude(longitude):
    """Return a finite longitude in the canonical half-open interval."""

    if isinstance(longitude, bool) or not isinstance(longitude, (int, float)):
        raise ValidationError("Долгота должна быть числом.")
    longitude = float(longitude)
    if not math.isfinite(longitude):
        raise ValidationError("Долгота должна быть конечным числом.")
    return (longitude + 180.0) % 360.0 - 180.0


def validate_latitude(latitude):
    if isinstance(latitude, bool) or not isinstance(latitude, (int, float)):
        raise ValidationError("Широта должна быть числом.")
    latitude = float(latitude)
    if not math.isfinite(latitude) or not -90.0 <= latitude <= 90.0:
        raise ValidationError("Широта должна находиться между -90 и 90 градусами.")
    return latitude


def normalized_point_to_latlon(point):
    """Convert one stored normalized map point to canonical ``[lat, lon]``."""

    normalized = validate_map_polygon(
        [point, point, point],
        require_polygon=True,
    )[0]
    x, y = normalized
    return [round(90.0 - y * 180.0, 6), round(x * 360.0 - 180.0, 6)]


def latlon_to_normalized_point(latitude, longitude):
    """Convert a geographic point to the legacy normalized storage format."""

    latitude = validate_latitude(latitude)
    longitude = normalize_longitude(longitude)
    return [
        round((longitude + 180.0) / 360.0, 6),
        round((90.0 - latitude) / 180.0, 6),
    ]


def normalized_ring_to_latlon(points):
    """Convert a stored Region ring to canonical geographic coordinates."""

    return [normalized_point_to_latlon(point) for point in validate_map_polygon(points)]


def latlon_ring_to_normalized(points):
    if not isinstance(points, list) or not 3 <= len(points) <= MAX_POLYGON_POINTS:
        raise ValidationError(
            f"Контур должен содержать от 3 до {MAX_POLYGON_POINTS} точек."
        )
    normalized = []
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValidationError("Каждая точка контура должна содержать latitude и longitude.")
        normalized.append(latlon_to_normalized_point(point[0], point[1]))
    return validate_map_polygon(normalized)


def unwrap_latlon_ring(points):
    """Unwrap longitudes so a seam-crossing edge follows the short arc."""

    if not points:
        return []
    unwrapped = [[validate_latitude(points[0][0]), normalize_longitude(points[0][1])]]
    for latitude, longitude in points[1:]:
        latitude = validate_latitude(latitude)
        longitude = normalize_longitude(longitude)
        previous = unwrapped[-1][1]
        longitude += round((previous - longitude) / 360.0) * 360.0
        unwrapped.append([latitude, longitude])
    return unwrapped


def leaflet_pixel_from_latlon(latitude, longitude, zoom=0):
    """Project into the 512×256-at-z0 equirectangular Leaflet pixel plane."""

    latitude = validate_latitude(latitude)
    longitude = float(longitude)
    if not math.isfinite(longitude):
        raise ValidationError("Долгота должна быть конечным числом.")
    scale = 2.0 ** int(zoom)
    return (
        (longitude + 180.0) / 360.0 * WORLD_PIXEL_WIDTH_ZOOM_ZERO * scale,
        (90.0 - latitude) / 180.0 * WORLD_PIXEL_HEIGHT_ZOOM_ZERO * scale,
    )


def leaflet_latlon_from_pixel(x, y, zoom=0):
    scale = 2.0 ** int(zoom)
    width = WORLD_PIXEL_WIDTH_ZOOM_ZERO * scale
    height = WORLD_PIXEL_HEIGHT_ZOOM_ZERO * scale
    return (
        90.0 - float(y) / height * 180.0,
        float(x) / width * 360.0 - 180.0,
    )


def planetary_distance_km(
    latitude_a,
    longitude_a,
    latitude_b,
    longitude_b,
    *,
    circumference_km=FARDECOSMIA_CIRCUMFERENCE_KM,
):
    """Spherical haversine distance using Fardecosmia's canonical radius."""

    latitude_a = math.radians(validate_latitude(latitude_a))
    latitude_b = math.radians(validate_latitude(latitude_b))
    delta_latitude = latitude_b - latitude_a
    delta_longitude = math.radians(
        normalize_longitude(longitude_b - longitude_a)
    )
    haversine = (
        math.sin(delta_latitude / 2.0) ** 2
        + math.cos(latitude_a)
        * math.cos(latitude_b)
        * math.sin(delta_longitude / 2.0) ** 2
    )
    central_angle = 2.0 * math.atan2(
        math.sqrt(haversine),
        math.sqrt(max(0.0, 1.0 - haversine)),
    )
    radius_km = float(circumference_km) / (2.0 * math.pi)
    return radius_km * central_angle


def polygon_svg_points(points, width=1000, height=500):
    if not points:
        return ""
    return " ".join(
        f"{point[0] * width:.3f},{point[1] * height:.3f}" for point in points
    )
