import math


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def apply_orography_and_precipitation(grid, static, settings):
    threshold = settings.value("precipitation_humidity_threshold")
    cloud_threshold = settings.value("cloud_threshold_humidity")
    cloud_response = settings.value("cloud_response")
    base_rate = settings.value("base_condensation_rate")
    precipitation_scale = settings.value("precipitation_rate_scale")
    humidity_loss = settings.value("condensation_humidity_loss")
    lift_rate = settings.value("orographic_lift_per_1000m")
    shadow_drying = settings.value("rain_shadow_drying_per_1000m")

    for y in range(grid.height):
        for x in range(grid.width):
            index = grid.index(x, y)
            u = grid.fields["wind_u"][index]
            v = grid.fields["wind_v"][index]
            upwind_x = x - (1 if u > 0 else -1 if u < 0 else 0)
            upwind_y = y + (1 if v > 0 else -1 if v < 0 else 0)
            upwind = static.neighbor_index(upwind_x, upwind_y)
            climb = max(0.0, static.elevation[index] - static.elevation[upwind])
            descent = max(0.0, static.elevation[upwind] - static.elevation[index])
            humidity = grid.fields["relative_humidity"][index]
            speed_factor = min(1.0, math.hypot(u, v) / 10.0)

            condensation = max(0.0, humidity - threshold) / 100.0 * base_rate
            condensation += (
                climb / 1000.0 * lift_rate * humidity / 100.0 * speed_factor
            )
            precipitation = max(0.0, condensation * precipitation_scale)
            humidity -= condensation * humidity_loss
            humidity -= descent / 1000.0 * shadow_drying * speed_factor
            humidity = clamp(humidity, 0.0, 100.0)
            cloud = clamp(
                (humidity - cloud_threshold) / max(1.0, 100.0 - cloud_threshold)
                * cloud_response
                + condensation,
                0.0,
                1.0,
            )
            grid.fields["relative_humidity"][index] = humidity
            grid.fields["water_content"][index] = humidity / 100.0
            grid.fields["precipitation_rate"][index] = precipitation
            grid.fields["cloud_cover"][index] = cloud
