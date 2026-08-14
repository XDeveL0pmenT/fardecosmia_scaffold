from django import forms

from world.models import AtmosphericConfig, Region
from world.services.map_geometry import validate_map_polygon
from world.services.map_layers import validate_layer_cells


class RegionMapForm(forms.ModelForm):
    map_polygon = forms.JSONField(widget=forms.HiddenInput)

    class Meta:
        model = Region
        fields = (
            "name",
            "use_manual_climate_overrides",
            "biome",
            "base_temperature",
            "seasonal_amplitude",
            "humidity",
            "elevation",
            "weather_volatility",
            "precipitation_bias",
            "map_polygon",
        )
        labels = {
            "name": "Название",
            "use_manual_climate_overrides": "Использовать ручные климатические поправки",
            "biome": "Биом",
            "base_temperature": "Климатическая средняя температура, °C",
            "seasonal_amplitude": "Отклик на орбитальную аномалию, °C",
            "humidity": "Средняя влажность, %",
            "elevation": "Высота",
            "weather_volatility": "Изменчивость погоды",
            "precipitation_bias": "Поправка осадков",
        }
        help_texts = {
            "biome": (
                "Автоматически берётся из общего атласа или локальной замены кампании."
            ),
            "base_temperature": (
                "Среднее значение карты, не текущая температура AtmosphericGrid."
            ),
            "seasonal_amplitude": (
                "Только legacy weather-v2. AtmosphericGrid v5 уже считает орбиту C1 "
                "и не применяет это поле повторно."
            ),
            "humidity": (
                "Начальная климатическая RH из той же baseline-логики, что и AtmosphericGrid. "
                "Текущая влажность всегда рассчитывается из qᵥ/T/p."
            ),
            "elevation": (
                "Автоматически считывается с общей карты высот."
            ),
            "weather_volatility": (
                "Только legacy weather-v2; AtmosphericGrid не создаёт из него второй "
                "случайный климатический слой."
            ),
            "precipitation_bias": (
                "Только legacy weather-v2. Осадки C3 возникают из qᵥ/q_c, переноса, "
                "охлаждения и рельефа."
            ),
            "use_manual_climate_overrides": (
                "По умолчанию выключено. Включайте только для намеренного GM-override; "
                "обычный регион полностью настраивается по выбранной точке карты."
            ),
        }

    def __init__(self, *args, campaign, **kwargs):
        super().__init__(*args, **kwargs)
        self.campaign = campaign
        for field_name in (
            "biome",
            "base_temperature",
            "seasonal_amplitude",
            "humidity",
            "elevation",
            "weather_volatility",
            "precipitation_bias",
        ):
            self.fields[field_name].required = False

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if Region.objects.filter(campaign=self.campaign, name__iexact=name).exists():
            raise forms.ValidationError("Регион с таким названием уже существует.")
        return name

    def clean_map_polygon(self):
        return validate_map_polygon(
            self.cleaned_data.get("map_polygon"),
            require_polygon=True,
        )

    def clean_precipitation_bias(self):
        value = self.cleaned_data.get("precipitation_bias")
        return Region._meta.get_field("precipitation_bias").get_default() if value is None else value

    def clean_seasonal_amplitude(self):
        value = self.cleaned_data.get("seasonal_amplitude")
        return Region._meta.get_field("seasonal_amplitude").get_default() if value is None else value

    def clean_weather_volatility(self):
        value = self.cleaned_data.get("weather_volatility")
        return Region._meta.get_field("weather_volatility").get_default() if value is None else value

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("use_manual_climate_overrides"):
            labels = {
                "biome": "Укажите биом для ручного override.",
                "base_temperature": "Укажите климатическую среднюю температуру.",
                "humidity": "Укажите климатическую среднюю влажность.",
                "elevation": "Укажите высоту для ручного override.",
            }
            for field_name, message in labels.items():
                value = cleaned.get(field_name)
                if value is None or value == "":
                    self.add_error(field_name, message)
        return cleaned


class RegionPlacementForm(forms.Form):
    region_id = forms.IntegerField(min_value=1)
    map_polygon = forms.JSONField(widget=forms.HiddenInput)

    def clean_map_polygon(self):
        return validate_map_polygon(
            self.cleaned_data.get("map_polygon"),
            require_polygon=True,
        )


class MapLayerPaintForm(forms.Form):
    layer_type = forms.ChoiceField(
        choices=(("biome", "Локальные замены биомов"),),
    )
    layer_cells = forms.JSONField(widget=forms.HiddenInput)

    def clean(self):
        cleaned = super().clean()
        if "layer_type" in cleaned and "layer_cells" in cleaned:
            cleaned["layer_cells"] = validate_layer_cells(
                cleaned["layer_cells"],
                cleaned["layer_type"],
            )
        return cleaned


class AtmosphericConfigForm(forms.ModelForm):
    class Meta:
        model = AtmosphericConfig
        fields = (
            "enabled",
            "ocean_temperature_c",
            "oxygen_fraction",
            "grid_width",
            "grid_height",
            "step_minutes",
            "world_seed",
            "checkpoint_interval_minutes",
            "checkpoint_retention_count",
        )
        labels = {
            "enabled": "Использовать глобальную атмосферу",
            "ocean_temperature_c": "Fallback температуры океана, °C",
            "oxygen_fraction": "Доля кислорода (если канонически известна)",
            "grid_width": "Ширина сетки",
            "grid_height": "Высота сетки",
            "step_minutes": "Шаг расчёта, игровых минут",
            "world_seed": "Seed мира",
            "checkpoint_interval_minutes": "Интервал checkpoint, минут",
            "checkpoint_retention_count": "Хранить checkpoints",
        }
        help_texts = {
            "enabled": (
                "Включает новую сетку для размещённых на карте регионов. "
                "Неразмещённые регионы останутся на weather-v2."
            ),
            "ocean_temperature_c": (
                "Используется только если карта средней температуры не содержит "
                "значения океана. Обычно оставьте пустым: SST берёт baseline с карты."
            ),
            "oxygen_fraction": (
                "Оставьте пустым, пока состав атмосферы не закреплён каноном. "
                "Без этого значения интерфейс не делает выводов о гипоксии."
            ),
            "grid_width": "По умолчанию 180; после первого снимка размер фиксируется.",
            "grid_height": "По умолчанию 90; после первого снимка размер фиксируется.",
            "step_minutes": "По умолчанию 360 минут — один последовательный шаг атмосферы.",
            "world_seed": "Обеспечивает повторяемость симуляции при одинаковом состоянии.",
            "checkpoint_interval_minutes": (
                "Оставьте пустым для одного checkpoint на Виток. Промежуточные "
                "360-минутные состояния рассчитываются в памяти."
            ),
            "checkpoint_retention_count": (
                "Оставьте пустым, чтобы не удалять исторические checkpoints автоматически. "
                "Региональная история погоды от pruning не зависит."
            ),
        }

    def clean(self):
        cleaned = super().clean()
        if self.instance.pk and self.instance.campaign.atmospheric_snapshots.exists():
            immutable = ("grid_width", "grid_height", "step_minutes", "world_seed")
            changed = [self.fields[name].label for name in immutable if name in self.changed_data]
            if changed:
                raise forms.ValidationError(
                    "После первого снимка нельзя неявно менять: " + ", ".join(changed) + "."
                )
        return cleaned
