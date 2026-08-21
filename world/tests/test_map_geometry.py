from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from world.services.map_geometry import (
    FARDECOSMIA_CIRCUMFERENCE_KM,
    latlon_ring_to_normalized,
    latlon_to_normalized_point,
    leaflet_latlon_from_pixel,
    leaflet_pixel_from_latlon,
    normalized_point_to_latlon,
    normalized_ring_to_latlon,
    planetary_distance_km,
    polygon_center,
    unwrap_latlon_ring,
    validate_map_polygon,
)


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

    def test_normalized_geographic_round_trip(self):
        for latitude, longitude in ((0, 0), (89.5, -179.75), (-90, 179.99)):
            normalized = latlon_to_normalized_point(latitude, longitude)
            restored = normalized_point_to_latlon(normalized)
            # Region storage is intentionally rounded to six normalized
            # decimals (sub-20 metre precision on Fardecosmia).
            self.assertAlmostEqual(restored[0], latitude, places=3)
            self.assertAlmostEqual(restored[1], longitude, places=3)

    def test_leaflet_projection_is_512_by_256_at_zoom_zero(self):
        self.assertEqual(leaflet_pixel_from_latlon(90, -180), (0.0, 0.0))
        self.assertEqual(leaflet_pixel_from_latlon(-90, 180), (512.0, 256.0))
        latitude, longitude = leaflet_latlon_from_pixel(256, 128)
        self.assertEqual((latitude, longitude), (0.0, 0.0))

    def test_longitude_seam_ring_uses_short_arc(self):
        ring = [[10, 179], [11, -179], [9, -178]]
        unwrapped = unwrap_latlon_ring(ring)
        self.assertLess(max(point[1] for point in unwrapped) - min(point[1] for point in unwrapped), 5)
        restored = normalized_ring_to_latlon(latlon_ring_to_normalized(ring))
        for actual, expected in zip(restored, ring, strict=True):
            self.assertAlmostEqual(actual[0], expected[0], places=3)
            self.assertAlmostEqual(actual[1], expected[1], places=3)

    def test_latitude_does_not_wrap_at_poles(self):
        with self.assertRaises(ValidationError):
            latlon_to_normalized_point(90.01, 0)
        with self.assertRaises(ValidationError):
            latlon_to_normalized_point(-90.01, 0)

    def test_distance_uses_canonical_planet_circumference(self):
        one_degree = planetary_distance_km(0, 0, 0, 1)
        quarter_equator = planetary_distance_km(0, 0, 0, 90)
        self.assertAlmostEqual(
            one_degree,
            FARDECOSMIA_CIRCUMFERENCE_KM / 360,
            places=6,
        )
        self.assertAlmostEqual(
            quarter_equator,
            FARDECOSMIA_CIRCUMFERENCE_KM / 4,
            places=6,
        )
        self.assertLess(planetary_distance_km(0, 179, 0, -179), 500)

    def test_irregular_and_polar_contours_keep_server_center_authoritative(self):
        for ring in (
            [[0.15, 0.25], [0.31, 0.28], [0.28, 0.41], [0.19, 0.38]],
            [[0.42, 0.0], [0.48, 0.0], [0.46, 0.025]],
        ):
            latitude_longitude_ring = normalized_ring_to_latlon(ring)
            restored = latlon_ring_to_normalized(latitude_longitude_ring)
            for actual, expected in zip(restored, ring, strict=True):
                self.assertAlmostEqual(actual[0], expected[0], places=5)
                self.assertAlmostEqual(actual[1], expected[1], places=5)
            self.assertEqual(polygon_center(restored), polygon_center(ring))
