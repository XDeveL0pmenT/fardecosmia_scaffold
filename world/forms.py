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
            "biome": "Биом",
            "base_temperature": "Базовая температура, °C",
            "seasonal_amplitude": "Сезонная амплитуда, °C",
            "humidity": "Средняя влажность, %",
            "elevation": "Высота",
            "weather_volatility": "Изменчивость погоды",
            "precipitation_bias": "Поправка осадков",
        }
        help_texts = {
            "biome": (
                "Если под контуром нарисован слой биомов, карта предложит его автоматически. "
                "Иначе выберите значение вручную."
            ),
            "base_temperature": (
                "Среднее значение без текущего сезона и времени суток. Оно автоматически "
                "считывается с предоставленной карты температур."
            ),
            "seasonal_amplitude": (
                "Насколько температура отклоняется от средней между серединой Лета и Зимы. "
                "Точная величина не задана каноном и остаётся настройкой."
            ),
            "humidity": (
                "Климатическая влажность: низкое значение означает сухой регион, высокое — "
                "частые облака и больше шансов осадков."
            ),
            "elevation": (
                "Высота центра региона. Автоматически считывается с общей карты высот; GM может оставить поверх неё локальную поправку."
            ),
            "weather_volatility": (
                "Размах случайных колебаний: 0 — почти неизменная погода, 1 — обычная, "
                "3 — крайне резкая. Частоту пересчёта задаёт отдельный интервал региона."
            ),
            "precipitation_bias": (
                "От −1 для особенно сухих мест до +1 для особенно влажных. 0 не вносит поправку."
            ),
        }

    def __init__(self, *args, campaign, **kwargs):
        super().__init__(*args, **kwargs)
        self.campaign = campaign
        self.fields["precipitation_bias"].required = False

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
        return 0 if value is None else value


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
            "grid_width",
            "grid_height",
            "step_minutes",
            "world_seed",
        )
        labels = {
            "enabled": "Использовать глобальную атмосферу",
            "ocean_temperature_c": "Температура горячего океана, °C",
            "grid_width": "Ширина сетки",
            "grid_height": "Высота сетки",
            "step_minutes": "Шаг расчёта, игровых минут",
            "world_seed": "Seed мира",
        }
        help_texts = {
            "enabled": (
                "Включает новую сетку для размещённых на карте регионов. "
                "Неразмещённые регионы останутся на weather-v2."
            ),
            "ocean_temperature_c": (
                "Обязательная настройка при включении: точное каноническое "
                "значение пока неизвестно и не подставляется автоматически."
            ),
            "grid_width": "По умолчанию 180; после первого снимка размер фиксируется.",
            "grid_height": "По умолчанию 90; после первого снимка размер фиксируется.",
            "step_minutes": "По умолчанию 360 минут — один последовательный шаг атмосферы.",
            "world_seed": "Обеспечивает повторяемость симуляции при одинаковом состоянии.",
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
