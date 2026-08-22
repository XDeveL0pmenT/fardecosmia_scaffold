import {formatCoordinates, normalizeLongitude} from "./fardecosmia_crs.js?v=m1-leaflet-atlas";

function appendDefinition(list, label, value) {
    const term = document.createElement("dt");
    term.textContent = label;
    const description = document.createElement("dd");
    description.textContent = value;
    list.append(term, description);
}

function cellIndex(latlng, width, height) {
    const longitude = normalizeLongitude(latlng.lng);
    const latitude = Math.max(-90, Math.min(90, latlng.lat));
    const x = Math.max(0, Math.min(width - 1, Math.floor((longitude + 180) / 360 * width)));
    const y = Math.max(0, Math.min(height - 1, Math.floor((90 - latitude) / 180 * height)));
    return y * width + x;
}

export class MapPointInspector {
    constructor(map, config, elements, options = {}) {
        this.map = map;
        this.config = config;
        this.elements = elements;
        this.options = options;
        this.enabled = false;
        this.pending = null;
        this.marker = null;
        this.grids = {};
        this.biomeLabels = Object.fromEntries(config.biomes.palette.map(item => [item.value, item.label]));
        this.effectiveBiomes = {
            ...config.biomes.global_cells,
            ...config.biomes.campaign_cells,
        };
        this.loadGrids();
        this.bind();
    }

    async loadGrids() {
        const sources = this.config.static_data;
        try {
            const [temperature, elevation, land] = await Promise.all([
                fetch(sources.temperature_url).then(response => response.ok ? response.json() : Promise.reject()),
                fetch(sources.elevation_url).then(response => response.ok ? response.json() : Promise.reject()),
                fetch(sources.land_mask_url).then(response => response.ok ? response.json() : Promise.reject()),
            ]);
            this.grids = {temperature, elevation, land};
        } catch (_) {
            this.options.onError?.("Не удалось загрузить данные для подсказок карты.");
        }
    }

    bind() {
        this.elements.toggle?.addEventListener("click", () => this.setEnabled(!this.enabled));
        this.elements.close?.addEventListener("click", () => {
            if (this.elements.panel) this.elements.panel.hidden = true;
        });
        this.map.on("mousemove", event => this.onMouseMove(event));
        this.map.on("mouseout", () => {
            if (this.elements.tooltip) this.elements.tooltip.hidden = true;
        });
        this.map.on("click", event => {
            if (!this.enabled || this.options.interactionBlocked?.()) return;
            this.inspect(event.latlng);
        });
    }

    setEnabled(enabled) {
        this.enabled = Boolean(enabled);
        this.elements.toggle?.classList.toggle("is-active", this.enabled);
        this.elements.toggle?.setAttribute("aria-pressed", String(this.enabled));
        this.map.getContainer().classList.toggle("atlas-map--inspect", this.enabled);
        this.options.onModeChange?.(this.enabled ? "inspect" : "view");
    }

    onMouseMove(event) {
        if (this.elements.coordinates) {
            this.elements.coordinates.textContent = formatCoordinates(event.latlng);
        }
        const tooltip = this.elements.tooltip;
        if (!tooltip || this.options.interactionBlocked?.()) {
            if (tooltip) tooltip.hidden = true;
            return;
        }
        const mode = this.options.activeMode?.() || "base";
        let value = null;
        if (mode === "temperature" && this.grids.temperature) {
            const grid = this.grids.temperature;
            value = `${Number(grid.values[cellIndex(event.latlng, grid.width, grid.height)]).toFixed(1)}°C`;
        } else if (mode === "elevation" && this.grids.elevation) {
            const grid = this.grids.elevation;
            const index = cellIndex(event.latlng, grid.width, grid.height);
            const sample = grid.values[index];
            value = sample === null
                ? (this.grids.land?.values[index] ? "Высота неизвестна" : "Океан")
                : `${sample} м`;
        } else if (mode === "biome") {
            const index = cellIndex(
                event.latlng,
                this.config.biomes.grid_width,
                this.config.biomes.grid_height,
            );
            const biome = this.effectiveBiomes[String(index)];
            value = this.biomeLabels[biome] || "Биом не задан";
        }
        if (!value) {
            tooltip.hidden = true;
            return;
        }
        const point = this.map.latLngToContainerPoint(event.latlng);
        tooltip.replaceChildren();
        const strong = document.createElement("strong");
        strong.textContent = value;
        const coordinates = document.createElement("span");
        coordinates.textContent = formatCoordinates(event.latlng, 2);
        tooltip.append(strong, coordinates);
        tooltip.style.left = `${point.x + 14}px`;
        tooltip.style.top = `${point.y + 14}px`;
        tooltip.hidden = false;
    }

    async inspect(latlng) {
        if (!this.config.inspect_url) return;
        this.pending?.abort();
        this.pending = new AbortController();
        const latitude = Math.max(-90, Math.min(90, Number(latlng.lat)));
        const longitude = normalizeLongitude(latlng.lng);
        this.showLoading(latitude, longitude);
        const query = new URLSearchParams({latitude: String(latitude), longitude: String(longitude)});
        try {
            const response = await fetch(`${this.config.inspect_url}?${query}`, {
                signal: this.pending.signal,
                headers: {"X-Requested-With": "XMLHttpRequest"},
            });
            const payload = await response.json();
            if (!response.ok) throw new Error(payload.error || "Inspection failed");
            this.render(payload);
            this.marker?.remove();
            this.marker = L.marker([payload.latitude, payload.longitude], {
                pane: "featureMarkers",
                icon: L.divIcon({
                    className: "atlas-point-marker",
                    html: "<span></span>",
                    iconSize: [18, 18],
                    iconAnchor: [9, 9],
                }),
            }).addTo(this.map);
        } catch (error) {
            if (error.name === "AbortError") return;
            this.showError("Не удалось прочитать эту точку карты.");
        }
    }

    showLoading(latitude, longitude) {
        if (!this.elements.panel || !this.elements.content) return;
        this.elements.panel.hidden = false;
        this.elements.content.textContent = `Читаю ${formatCoordinates({lat: latitude, lng: longitude})}…`;
    }

    showError(message) {
        if (!this.elements.panel || !this.elements.content) return;
        this.elements.panel.hidden = false;
        this.elements.content.textContent = message;
    }

    render(payload) {
        const content = this.elements.content;
        if (!this.elements.panel || !content) return;
        content.replaceChildren();
        const heading = document.createElement("h3");
        heading.textContent = formatCoordinates({lat: payload.latitude, lng: payload.longitude});
        content.append(heading);
        const staticHeading = document.createElement("h4");
        staticHeading.textContent = "World Data";
        const staticList = document.createElement("dl");
        appendDefinition(staticList, "Поверхность", payload.static.surface_label);
        appendDefinition(staticList, "Высота", payload.static.elevation === null ? "неизвестна" : `${payload.static.elevation.toFixed(1)} м`);
        appendDefinition(staticList, "Биом", payload.static.biome_label);
        appendDefinition(staticList, "Средняя температура", `${payload.static.base_temperature.toFixed(1)}°C`);
        appendDefinition(staticList, "Климатическая влажность", `${payload.static.humidity.toFixed(0)}%`);
        content.append(staticHeading, staticList);
        const weatherHeading = document.createElement("h4");
        weatherHeading.textContent = "Атмосфера сейчас";
        content.append(weatherHeading);
        if (!payload.weather_available) {
            const unavailable = document.createElement("p");
            unavailable.textContent = "Совместимое физическое состояние атмосферы недоступно.";
            content.append(unavailable);
        } else {
            const weather = payload.weather;
            const weatherList = document.createElement("dl");
            appendDefinition(weatherList, "Состояние", weather.condition_label);
            appendDefinition(weatherList, "Температура", `${weather.temperature_c.toFixed(1)}°C`);
            appendDefinition(weatherList, "Влажность", `${weather.relative_humidity_percent.toFixed(1)}%`);
            appendDefinition(weatherList, "Давление", `${weather.surface_pressure_hpa.toFixed(1)} гПа`);
            appendDefinition(weatherList, "Ветер", `${weather.wind_speed_m_s.toFixed(1)} м/с`);
            appendDefinition(weatherList, "Облачность", `${(weather.cloud_cover * 100).toFixed(0)}%`);
            appendDefinition(weatherList, "Осадки сейчас", `${weather.precipitation_rate_mm_h.toFixed(2)} мм/ч`);
            appendDefinition(weatherList, "Снимок", `${weather.snapshot_world_minutes} мин. · возраст ${weather.age_minutes} мин.`);
            content.append(weatherList);
        }
        this.elements.panel.hidden = false;
    }
}
