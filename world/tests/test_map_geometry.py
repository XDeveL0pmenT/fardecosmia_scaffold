from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from world.services.map_geometry import polygon_center, validate_map_polygon


class MapGeometryTests(SimpleTestCase):
    def test_polygon_center_becomes_longitude_and_latitude(self):
        longitude, latitude = polygon_center(
            [[0.49, 0.49], [0.51, 0.49], [0.50, 0.52]]
        )

        self.assertAlmostEqual(longitude, 0, places=5)
        self.assertAlmostEqual(latitude, 0, places=5)

    def test_polygon_rejects_coordinates_outside_map(self):
        with self.assertRaises(ValidationError):
            validate_map_polygon([[0, 0], [1.1, 0.5], [0.5, 1]])

    def test_polygon_requires_three_points(self):
        with self.assertRaises(ValidationError):
            validate_map_polygon([[0, 0], [1, 1]])
