from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from world.models import Region
from world.services.map_layers import (
    MAP_GRID_HEIGHT,
    MAP_GRID_WIDTH,
    load_elevation_grid,
    load_land_mask,
    validate_layer_cells,
)


class WorldReferenceLayerTests(SimpleTestCase):
    def test_reference_grids_share_the_editor_resolution(self):
        elevation = load_elevation_grid()
        land = load_land_mask()

        self.assertEqual((elevation["width"], elevation["height"]), (360, 180))
        self.assertEqual((land["width"], land["height"]), (360, 180))
        self.assertEqual((MAP_GRID_WIDTH, MAP_GRID_HEIGHT), (360, 180))

    def test_temperature_grid_records_chroma_aware_sampling(self):
        from world.services.map_layers import load_average_temperature_grid

        temperature = load_average_temperature_grid()

        self.assertEqual(temperature["sampling_method"], "legend-lab-chroma-v2")
        self.assertEqual(len(temperature["values"]), 360 * 180)

    def test_ocean_has_no_invented_elevation(self):
        elevation = load_elevation_grid()["values"]
        land = load_land_mask()["values"]
        ocean_index = land.index(0)

        self.assertIsNone(elevation[ocean_index])

    def test_biome_validation_rejects_ocean(self):
        ocean_index = load_land_mask()["values"].index(0)

        with self.assertRaisesMessage(
            ValidationError,
            "Биом нельзя рисовать за пределами суши.",
        ):
            validate_layer_cells(
                {str(ocean_index): Region.Biome.LEGACY_COAST},
                "biome",
            )
