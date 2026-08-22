from django import forms

from campaigns.time_controls import TIME_ADVANCE_UNITS
from world.models import AtmosphericConfig, Region, WorldEntry
from world.services.calendar import minutes_for_time_step
from world.services.map_geometry import validate_map_polygon
from world.services.map_layers import validate_layer_cells


MAX_REGION_CONTOUR_JSON_BYTES = 64 * 1024
MAX_MAP_LAYER_JSON_BYTES = 4 * 1024 * 1024


class _WorldEventHumanForm(forms.Form):
    title = forms.CharField(label="Название", max_length=200)
    description = forms.CharField(
        label="Описание",
        required=False,
        widget=forms.Textarea(attrs={"rows": 5}),
        help_text="Что должно произойти или что уже произошло в объективной истории кампании.",
    )
    region = forms.ModelChoiceField(
        label="Место",
        required=False,
        queryset=Region.objects.none(),
        empty_label="Без конкретного региона",
    )

    def __init__(self, *args, campaign, **kwargs):
        self.campaign = campaign
        super().__init__(*args, **kwargs)
        self.fields["region"].queryset = campaign.regions.order_by("name")


class WorldEventScheduleForm(_WorldEventHumanForm):
    amount = forms.IntegerField(label="Через", min_value=1, initial=1)
    unit = forms.ChoiceField(
        label="Единица времени",
        choices=[
            (item["value"], item["label"])
            for item in TIME_ADVANCE_UNITS
        ],
        initial="turns",
        help_text="Событие будет привязано к точному мировому времени.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.order_fields(("title", "description", "amount", "unit", "region"))

    def clean(self):
        cleaned = super().clean()
        amount = cleaned.get("amount")
        unit = cleaned.get("unit")
        if amount and unit:
            try:
                delta = minutes_for_time_step(self.campaign, amount, unit)
            except ValueError as error:
                raise forms.ValidationError(str(error)) from error
            cleaned["scheduled_world_minutes"] = self.campaign.world_minutes + delta
        return cleaned


class WorldEventNowForm(_WorldEventHumanForm):
    pass


class WorldEventDefinitionEditForm(_WorldEventHumanForm):
    pass


class BoundedJSONField(forms.JSONField):
    def __init__(self, *args, max_bytes, **kwargs):
        self.max_bytes = max_bytes
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        if isinstance(value, str) and len(value.encode("utf-8")) > self.max_bytes:
            raise forms.ValidationError("Переданные данные карты слишком велики.")
        return super().to_python(value)


class RegionMapForm(forms.ModelForm):
    map_polygon = BoundedJSONField(
        max_bytes=MAX_REGION_CONTOUR_JSON_BYTES,
        widget=forms.HiddenInput,
    )

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
    map_polygon = BoundedJSONField(
        max_bytes=MAX_REGION_CONTOUR_JSON_BYTES,
        widget=forms.HiddenInput,
    )

    def clean_map_polygon(self):
        return validate_map_polygon(
            self.cleaned_data.get("map_polygon"),
            require_polygon=True,
        )


class MapLayerPaintForm(forms.Form):
    layer_type = forms.ChoiceField(
        choices=(("biome", "Локальные замены биомов"),),
    )
    layer_cells = BoundedJSONField(
        max_bytes=MAX_MAP_LAYER_JSON_BYTES,
        widget=forms.HiddenInput,
    )

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


class WorldEntryForm(forms.ModelForm):
    class Meta:
        model = WorldEntry
        fields = ("kind", "slug", "title", "summary", "body")
        labels = {
            "kind": "Тип записи",
            "slug": "Стабильный идентификатор",
            "title": "Название",
            "summary": "Краткое описание",
            "body": "Полное описание",
        }
        widgets = {
            "summary": forms.Textarea(attrs={"rows": 3}),
            "body": forms.Textarea(attrs={"rows": 10}),
        }


class CampaignOverrideForm(forms.Form):
    title = forms.CharField(
        label="Название в кампании",
        required=False,
        max_length=240,
        help_text="Оставьте пустым, чтобы наследовать глобальное название.",
    )
    summary = forms.CharField(
        label="Краткое описание в кампании",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Оставьте пустым, чтобы наследовать глобальное описание.",
    )
    body = forms.CharField(
        label="Полное описание в кампании",
        required=False,
        widget=forms.Textarea(attrs={"rows": 10}),
        help_text="Оставьте пустым, чтобы наследовать глобальный текст.",
    )

    def patch(self):
        return {
            name: value
            for name, value in self.cleaned_data.items()
            if value != ""
        }
