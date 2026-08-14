import math
from dataclasses import dataclass

from world.atmosphere_defaults import default_atmospheric_parameters


@dataclass(frozen=True)
class AtmosphericSettings:
    width: int = 180
    height: int = 90
    step_minutes: int = 360
    world_seed: int = 0
    world_circumference_km: float = 72_500.0
    ocean_temperature_c: float | None = None
    parameters: dict | None = None

    def __post_init__(self):
        if not isinstance(self.width, int) or isinstance(self.width, bool) or self.width < 4:
            raise ValueError("Ширина атмосферной сетки должна быть целым числом не меньше 4.")
        if not isinstance(self.height, int) or isinstance(self.height, bool) or self.height < 2:
            raise ValueError("Высота атмосферной сетки должна быть целым числом не меньше 2.")
        if (
            not isinstance(self.step_minutes, int)
            or isinstance(self.step_minutes, bool)
            or self.step_minutes <= 0
        ):
            raise ValueError("Шаг атмосферы должен быть положительным целым числом минут.")
        if not math.isfinite(float(self.world_circumference_km)) or self.world_circumference_km <= 0:
            raise ValueError("Длина мира должна быть положительным конечным числом.")
        if self.ocean_temperature_c is not None and not math.isfinite(
            float(self.ocean_temperature_c)
        ):
            raise ValueError("Температура океана должна быть конечным числом.")

        merged = default_atmospheric_parameters()
        if self.parameters is not None:
            if not isinstance(self.parameters, dict):
                raise ValueError("Параметры атмосферы должны быть JSON-объектом.")
            merged.update(self.parameters)
        for key, value in merged.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"Параметр атмосферы {key} должен быть числом.")
            if not math.isfinite(float(value)):
                raise ValueError(f"Параметр атмосферы {key} должен быть конечным.")
        object.__setattr__(self, "parameters", merged)

    @classmethod
    def from_model(cls, config, campaign):
        return cls(
            width=config.grid_width,
            height=config.grid_height,
            step_minutes=config.step_minutes,
            world_seed=config.world_seed,
            world_circumference_km=campaign.world_circumference_km,
            ocean_temperature_c=config.ocean_temperature_c,
            parameters=config.parameters,
        )

    def require_ocean_temperature(self):
        if self.ocean_temperature_c is None:
            raise ValueError(
                "Температура горячего океана не задана. Укажите её в AtmosphericConfig."
            )
        return float(self.ocean_temperature_c)

    def value(self, name):
        return float(self.parameters[name])
