from django.test import SimpleTestCase, TestCase

from campaigns.models import Campaign
from world.biomes import Biome
from world.models import GlobalWorldMapLayer, Region
from world.services.world_data import (
    MAP_GRID_HEIGHT,
    MAP_GRID_WIDTH,
    SurfaceType,
    WorldData,
    WorldDataUnavailable,
    coordinates_to_grid,
    load_average_temperature_grid,
    load_elevation_grid,
    load_land_mask,
)


def coordinates_for_index(index):
    x = index % MAP_GRID_WIDTH
    y = index // MAP_GRID_WIDTH
    longitude = -180 + (x + 0.5) * 360 / MAP_GRID_WIDTH
    latitude = 90 - (y + 0.5) * 180 / MAP_GRID_HEIGHT
    return latitude, longitude


class CoordinateConversionTests(SimpleTestCase):
    def test_longitude_wraps_across_the_dateline(self):
        self.assertEqual(
            coordinates_to_grid(12, 181),
            coordinates_to_grid(12, -179),
        )
        self.assertEqual(
            coordinates_to_grid(12, -541),
            coordinates_to_grid(12, 179),
        )

    def test_latitude_clamps_at_north_and_south_poles(self):
        self.assertEqual(coordinates_to_grid(999, 0)[1], 0)
        self.assertEqual(coordinates_to_grid(-999, 0)[1], MAP_GRID_HEIGHT - 1)

    def test_world_centre_maps_to_central_cell(self):
        self.assertEqual(coordinates_to_grid(0, 0), (180, 90, 32580))

    def test_invalid_non_finite_coordinate_is_rejected(self):
        with self.assertRaises(ValueError):
            coordinates_to_grid(float("nan"), 0)


class WorldDataStaticTests(TestCase):
    def setUp(self):
        mask = load_land_mask()["values"]
        self.land_index = mask.index(1)
        self.ocean_index = mask.index(0)
        self.land_coordinates = coordinates_for_index(self.land_index)
        self.ocean_coordinates = coordinates_for_index(self.ocean_index)

    def test_api_reads_static_surface_temperature_and_elevation(self):
        data = WorldData()
        land_lat, land_lon = self.land_coordinates
        ocean_lat, ocean_lon = self.ocean_coordinates

        self.assertEqual(data.surface_at(land_lat, land_lon), SurfaceType.LAND)
        self.assertEqual(data.surface_at(ocean_lat, ocean_lon), SurfaceType.OCEAN)
        self.assertEqual(
            data.mean_temperature_at(land_lat, land_lon),
            float(load_average_temperature_grid()["values"][self.land_index]),
        )
        reference_elevation = load_elevation_grid()["values"][self.land_index]
        self.assertEqual(
            data.elevation_at(land_lat, land_lon),
            None if reference_elevation is None else float(reference_elevation),
        )

    def test_authored_global_values_override_raster_but_regions_do_not(self):
        GlobalWorldMapLayer.objects.create(
            biome_cells={str(self.land_index): Biome.RED_PLATEAUS},
            elevation_cells={str(self.land_index): 4321.5},
        )
        campaign = Campaign.objects.create(name="Независимый API")
        Region.objects.create(
            campaign=campaign,
            name="Конфликтующий снимок региона",
            biome=Biome.FOREST,
            base_temperature=-123,
            elevation=-999,
            map_latitude=self.land_coordinates[0],
            map_longitude=self.land_coordinates[1],
        )

        data = WorldData()
        latitude, longitude = self.land_coordinates
        self.assertEqual(data.biome_at(latitude, longitude), Biome.RED_PLATEAUS)
        self.assertEqual(data.elevation_at(latitude, longitude), 4321.5)
        self.assertNotEqual(data.mean_temperature_at(latitude, longitude), -123)

    def test_elevation_is_bilinear_between_valid_raster_cell_centres(self):
        elevations = load_elevation_grid()["values"]
        candidate = next(
            (x, y)
            for y in range(MAP_GRID_HEIGHT - 1)
            for x in range(MAP_GRID_WIDTH - 1)
            if all(
                elevations[(y + dy) * MAP_GRID_WIDTH + x + dx] is not None
                for dy in (0, 1)
                for dx in (0, 1)
            )
            and len(
                {
                    elevations[(y + dy) * MAP_GRID_WIDTH + x + dx]
                    for dy in (0, 1)
                    for dx in (0, 1)
                }
            )
            > 1
        )
        x, y = candidate
        # This coordinate is halfway between the four raster cell centres.
        longitude = -180.0 + (x + 1.0) * 360.0 / MAP_GRID_WIDTH
        latitude = 90.0 - (y + 1.0) * 180.0 / MAP_GRID_HEIGHT
        expected = sum(
            elevations[(y + dy) * MAP_GRID_WIDTH + x + dx]
            for dy in (0, 1)
            for dx in (0, 1)
        ) / 4.0

        self.assertAlmostEqual(
            WorldData().elevation_at(latitude, longitude),
            expected,
        )
        # Surface type deliberately keeps nearest/discrete semantics.
        _, _, nearest_index = coordinates_to_grid(latitude, longitude)
        expected_surface = (
            SurfaceType.LAND
            if load_land_mask()["values"][nearest_index]
            else SurfaceType.OCEAN
        )
        self.assertEqual(WorldData().surface_at(latitude, longitude), expected_surface)

    def test_ocean_baseline_uses_mean_temperature_map_before_fallback(self):
        latitude, longitude = self.ocean_coordinates
        data = WorldData()
        expected = data.mean_temperature_at(latitude, longitude)
        self.assertEqual(data.ocean_temperature_at(latitude, longitude), expected)
        self.assertEqual(
            data.ocean_temperature_at(
                latitude,
                longitude,
                configured_temperature=38,
            ),
            expected,
        )

    def test_unimplemented_spatial_fields_still_fail_explicitly(self):
        latitude, longitude = self.ocean_coordinates
        with self.assertRaises(WorldDataUnavailable):
            WorldData().distance_to_ocean(latitude, longitude)
