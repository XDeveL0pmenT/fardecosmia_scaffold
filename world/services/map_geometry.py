import math

from django.core.exceptions import ValidationError


MAX_POLYGON_POINTS = 512


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


def polygon_svg_points(points, width=1000, height=500):
    if not points:
        return ""
    return " ".join(
        f"{point[0] * width:.3f},{point[1] * height:.3f}" for point in points
    )
