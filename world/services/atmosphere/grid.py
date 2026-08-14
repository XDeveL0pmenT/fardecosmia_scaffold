import math
import zlib

import numpy as np


ATMOSPHERIC_FIELDS = (
    "temperature",
    "water_vapor_specific_humidity",
    "cloud_condensate_specific_humidity",
    "circulation_pressure_hpa",
    "pressure_hpa",
    "wind_u",
    "wind_v",
    "cloud_cover",
    "precipitation_rate",
    "condensation_rate_kg_m2_s",
    "latent_heating_rate_w_m2",
    "surface_temperature",
    "sea_surface_temperature_c",
    "evaporation_flux_kg_m2_s",
)
MAGIC = b"FATM4"
FLOAT_BYTES = 4
FLOAT_DTYPE = np.dtype("<f4")


class AtmosphericGrid:
    def __init__(self, width, height, fields):
        self.width = int(width)
        self.height = int(height)
        self.size = self.width * self.height
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Размер атмосферной сетки должен быть положительным.")
        if set(fields) != set(ATMOSPHERIC_FIELDS):
            raise ValueError("Набор полей атмосферной сетки не соответствует версии формата.")
        self.fields = {}
        for name in ATMOSPHERIC_FIELDS:
            values = np.asarray(fields[name], dtype=FLOAT_DTYPE)
            if values.size != self.size:
                raise ValueError(f"Поле {name} имеет неверный размер или тип.")
            self.fields[name] = np.ascontiguousarray(values.reshape(self.size))

    @classmethod
    def empty(cls, width, height):
        size = width * height
        return cls(
            width,
            height,
            {name: np.zeros(size, dtype=FLOAT_DTYPE) for name in ATMOSPHERIC_FIELDS},
        )

    @property
    def uncompressed_size_bytes(self):
        return self.size * len(ATMOSPHERIC_FIELDS) * FLOAT_BYTES

    def clone(self):
        return AtmosphericGrid(
            self.width,
            self.height,
            {name: values.copy() for name, values in self.fields.items()},
        )

    def index(self, x, y):
        return int(y) * self.width + (int(x) % self.width)

    def neighbor_index(self, x, y):
        y = max(0, min(self.height - 1, int(y)))
        return self.index(x, y)

    def serialize(self):
        raw = bytearray(MAGIC)
        for name in ATMOSPHERIC_FIELDS:
            raw.extend(self.fields[name].astype(FLOAT_DTYPE, copy=False).tobytes())
        # Level 1 is materially faster for frequent simulation checkpoints;
        # payloads remain version-compatible and are still substantially
        # smaller than the uncompressed float grid.
        return zlib.compress(bytes(raw), level=1)

    @classmethod
    def deserialize(cls, width, height, payload):
        raw = zlib.decompress(bytes(payload))
        if not raw.startswith(MAGIC):
            raise ValueError("Неизвестный формат атмосферного снимка.")
        expected = len(MAGIC) + width * height * len(ATMOSPHERIC_FIELDS) * FLOAT_BYTES
        if len(raw) != expected:
            raise ValueError("Размер атмосферного снимка не совпадает с сеткой.")
        fields = {}
        offset = len(MAGIC)
        byte_count = width * height * FLOAT_BYTES
        for name in ATMOSPHERIC_FIELDS:
            fields[name] = np.frombuffer(
                raw,
                dtype=FLOAT_DTYPE,
                count=width * height,
                offset=offset,
            ).copy()
            offset += byte_count
        return cls(width, height, fields)

    def field_2d(self, field):
        return self.fields[field].reshape(self.height, self.width)

    def bilinear_sample(self, field, x, y):
        values = self.fields[field]
        x %= self.width
        y = max(0.0, min(self.height - 1.0, y))
        x0 = math.floor(x)
        y0 = math.floor(y)
        x1 = (x0 + 1) % self.width
        y1 = min(self.height - 1, y0 + 1)
        tx = x - x0
        ty = y - y0
        top = values[self.index(x0, y0)] * (1 - tx) + values[self.index(x1, y0)] * tx
        bottom = values[self.index(x0, y1)] * (1 - tx) + values[self.index(x1, y1)] * tx
        return top * (1 - ty) + bottom * ty


def wind_speed_and_direction(wind_u, wind_v):
    speed = math.hypot(wind_u, wind_v)
    if speed < 1e-9:
        return 0.0, None
    # Meteorological direction: where the wind comes from, clockwise from north.
    direction = (math.degrees(math.atan2(-wind_u, -wind_v)) + 360.0) % 360.0
    return speed, direction
