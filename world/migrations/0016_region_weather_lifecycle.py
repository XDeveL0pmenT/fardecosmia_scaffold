from django.db import migrations, models
import django.db.models.deletion


def assign_initial_weather_revision(apps, schema_editor):
    WeatherState = apps.get_model("world", "WeatherState")
    # Existing numbers remain untouched.  Revision zero only records that
    # these rows belong to the geometry present when R1 was introduced.
    WeatherState.objects.filter(region_weather_revision__isnull=True).update(
        region_weather_revision=0
    )


class Migration(migrations.Migration):
    dependencies = [
        ("world", "0015_phase_c41_solver_version"),
    ]

    operations = [
        migrations.AddField(
            model_name="region",
            name="weather_geometry_revision",
            field=models.PositiveIntegerField(
                default=0,
                editable=False,
                help_text=(
                    "Ревизия контура и опорной точки, для которых рассчитывается "
                    "текущая погода региона."
                ),
            ),
        ),
        migrations.AddField(
            model_name="weatherstate",
            name="atmosphere_fingerprint",
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name="weatherstate",
            name="region_weather_revision",
            field=models.PositiveIntegerField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="weatherstate",
            name="sample_elevation_m",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="weatherstate",
            name="sample_latitude",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="weatherstate",
            name="sample_longitude",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="weatherstate",
            name="solver_version",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.RunPython(
            assign_initial_weather_revision,
            migrations.RunPython.noop,
        ),
        migrations.RemoveConstraint(
            model_name="weatherstate",
            name="unique_weather_state_per_region_time",
        ),
        migrations.AddConstraint(
            model_name="weatherstate",
            constraint=models.UniqueConstraint(
                fields=("region", "world_minutes", "region_weather_revision"),
                name="unique_weather_state_per_region_time_revision",
            ),
        ),
        migrations.AddIndex(
            model_name="weatherstate",
            index=models.Index(
                fields=["region", "region_weather_revision", "-world_minutes"],
                name="world_ws_current_idx",
            ),
        ),
        migrations.CreateModel(
            name="RegionAreaWeatherState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("world_minutes", models.BigIntegerField()),
                ("region_weather_revision", models.PositiveIntegerField(db_index=True)),
                ("sampling_mode", models.CharField(choices=[("area", "Контур области"), ("point_fallback", "Точечная оценка")], default="area", max_length=20)),
                ("grid_width", models.PositiveSmallIntegerField()),
                ("grid_height", models.PositiveSmallIntegerField()),
                ("covered_cell_count", models.PositiveIntegerField(default=0)),
                ("covered_area_m2", models.FloatField(default=0.0)),
                ("temperature_mean_c", models.FloatField()),
                ("temperature_min_c", models.FloatField()),
                ("temperature_max_c", models.FloatField()),
                ("temperature_p10_c", models.FloatField()),
                ("temperature_p90_c", models.FloatField()),
                ("humidity_mean_percent", models.FloatField()),
                ("humidity_p10_percent", models.FloatField()),
                ("humidity_p90_percent", models.FloatField()),
                ("surface_pressure_mean_hpa", models.FloatField()),
                ("cloud_cover_mean", models.FloatField()),
                ("cloudy_area_fraction", models.FloatField()),
                ("heavy_cloud_area_fraction", models.FloatField()),
                ("precipitating_area_fraction", models.FloatField()),
                ("rain_area_fraction", models.FloatField()),
                ("snow_area_fraction", models.FloatField()),
                ("area_mean_precipitation_rate_mm_h", models.FloatField()),
                ("wet_area_mean_precipitation_rate_mm_h", models.FloatField()),
                ("max_precipitation_rate_mm_h", models.FloatField()),
                ("wind_mean_u_m_s", models.FloatField()),
                ("wind_mean_v_m_s", models.FloatField()),
                ("prevailing_wind_direction_degrees", models.FloatField(blank=True, null=True)),
                ("wind_speed_mean_m_s", models.FloatField()),
                ("wind_speed_p90_m_s", models.FloatField()),
                ("wind_speed_max_m_s", models.FloatField()),
                ("strong_wind_area_fraction", models.FloatField()),
                ("fog_area_fraction", models.FloatField(default=0.0)),
                ("dangerous_heat_area_fraction", models.FloatField(default=0.0)),
                ("dangerous_cold_area_fraction", models.FloatField(default=0.0)),
                ("source", models.CharField(choices=[("legacy_v2", "Региональная weather-v2"), ("atmospheric_grid_v1", "Глобальная атмосферная сетка v1"), ("atmospheric_grid_v2", "Глобальная атмосферная сетка C3"), ("atmospheric_grid_v3", "Глобальная атмосферная сетка C4")], default="atmospheric_grid_v3", max_length=30)),
                ("solver_version", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("atmosphere_fingerprint", models.CharField(blank=True, max_length=64, null=True)),
                ("region", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="area_weather_history", to="world.region")),
            ],
            options={
                "ordering": ["-world_minutes"],
                "indexes": [models.Index(fields=["region", "region_weather_revision", "-world_minutes"], name="world_raw_current_idx")],
                "constraints": [models.UniqueConstraint(fields=("region", "world_minutes", "region_weather_revision"), name="unique_region_area_weather_time_revision")],
            },
        ),
    ]
