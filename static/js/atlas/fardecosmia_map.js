import {
    createFardecosmiaCRS,
    normalizeLongitude,
    normalizedRingToLatLngs,
} from "./fardecosmia_crs.js?v=m1-leaflet-atlas";
import {createLayerRegistry} from "./map_layers.js?v=m1-leaflet-atlas";
import {MapPointInspector} from "./map_point_inspector.js?v=m1-leaflet-atlas";
import {RegionContourController} from "./region_contour_editor.js?v=m1-leaflet-atlas";

const root = document.querySelector("[data-fardecosmia-atlas]");
const configNode = document.getElementById("fardecosmia-atlas-config");

if (root && configNode && window.L) {
    const config = JSON.parse(configNode.textContent);
    const stage = root.querySelector("[data-map-stage]");
    const mapElement = root.querySelector("[data-leaflet-map]");
    const status = root.querySelector("[data-draw-status]");
    const errorBox = root.querySelector("[data-map-error]");
    const setStatus = message => { if (status) status.textContent = message; };
    const showError = message => {
        if (!errorBox) return;
        errorBox.textContent = message || "Слой карты недоступен";
        errorBox.hidden = false;
    };

    const crs = createFardecosmiaCRS(config.crs.circumference_km);
    const map = L.map(mapElement, {
        crs,
        center: config.view.center,
        zoom: config.view.initial_zoom,
        minZoom: config.view.min_zoom,
        maxZoom: config.view.max_zoom,
        zoomControl: false,
        attributionControl: false,
        worldCopyJump: false,
        maxBounds: [[-90, -1000000], [90, 1000000]],
        maxBoundsViscosity: 0.92,
        preferCanvas: true,
    });

    const panes = {
        baseRaster: 200,
        staticClimate: 220,
        campaignOverrides: 235,
        lightStar: 250,
        lightDarkness: 260,
        lightYmpha: 270,
        regionFills: 390,
        regionBorders: 400,
        featureMarkers: 500,
        labels: 550,
        editHandles: 600,
        gmDebug: 650,
    };
    Object.entries(panes).forEach(([name, zIndex]) => {
        const pane = map.createPane(name);
        pane.style.zIndex = String(zIndex);
    });
    map.getPane("lightStar").style.mixBlendMode = "screen";
    map.getPane("lightDarkness").style.mixBlendMode = "multiply";
    map.getPane("lightYmpha").style.mixBlendMode = "screen";

    L.control.zoom({position: "topright"}).addTo(map);
    L.control.scale({position: "bottomleft", imperial: false, metric: true, maxWidth: 150}).addTo(map);

    const registry = createLayerRegistry(map, config, () => showError("Слой карты недоступен: один или несколько тайлов не загрузились."));
    let activeMode = "";
    const modeTitles = {
        base: "Поверхность",
        light: "Свет сейчас",
        temperature: "Средняя температура",
        elevation: "Высота",
        biome: "Биомы",
    };
    const modeNotes = {
        base: "Общая географическая основа мира.",
        light: "Тень Звезды и красный свет Ympha рассчитаны серверной моделью для текущей минуты.",
        temperature: "Baseline-климатология World Data, а не температура сейчас.",
        elevation: "Высота из объективного World Data; растровая легенда остаётся частью исходного изображения.",
        biome: "Общий атлас биомов с локальными заменами этой кампании.",
    };
    const setMode = requested => {
        const fallback = config.campaign ? "light" : "base";
        const mode = modeTitles[requested] && registry.available(requested) ? requested : fallback;
        if (painting) stopPainting(true);
        activeMode = mode;
        registry.setMode(mode);
        stage.dataset.mapModeActive = mode;
        root.querySelector("[data-mode-title]").textContent = modeTitles[mode];
        root.querySelector("[data-mode-note]").textContent = modeNotes[mode];
        root.querySelectorAll("[data-map-mode]").forEach(button => {
            const selected = button.dataset.mapMode === mode;
            button.classList.toggle("is-active", selected);
            button.setAttribute("aria-selected", String(selected));
        });
        root.querySelectorAll("[data-legend-mode]").forEach(item => {
            item.hidden = item.dataset.legendMode !== mode;
        });
        const editLayer = root.querySelector("[data-edit-layer]");
        if (editLayer) editLayer.hidden = mode !== "biome";
    };
    root.querySelectorAll("[data-map-mode]").forEach(button => {
        const layer = config.layers[button.dataset.mapMode];
        if (layer && layer.available === false && button.dataset.mapMode !== "biome") {
            button.disabled = true;
            button.title = "Слой карты недоступен: запустите build_planet_tiles.";
        }
        button.addEventListener("click", () => setMode(button.dataset.mapMode));
    });

    let inspector;
    const editor = new RegionContourController(
        map,
        config.regions,
        {
            status,
            newButton: root.querySelector("[data-draw-new]"),
            finishButton: root.querySelector("[data-draw-finish]"),
            undoButton: root.querySelector("[data-draw-undo]"),
            clearButton: root.querySelector("[data-draw-reset]"),
            cancelButton: root.querySelector("[data-draw-cancel]"),
        },
        {
            onModeChange(mode, regionId) {
                if (mode !== "view") inspector?.setEnabled(false);
                const placementRegion = document.querySelector("[name='placement-region_id']");
                if (placementRegion && regionId) placementRegion.value = String(regionId);
                root.querySelectorAll("[data-atlas-interaction-mode]").forEach(button => {
                    button.classList.toggle("is-active", button.dataset.atlasInteractionMode === mode);
                });
            },
            onChange(ring, mode) {
                syncContourFields(ring, mode);
                if (mode === "draw") scheduleClimatePreview(ring);
            },
        },
    );

    inspector = new MapPointInspector(
        map,
        config,
        {
            toggle: root.querySelector("[data-inspect-toggle]"),
            coordinates: root.querySelector("[data-cursor-coordinates]"),
            tooltip: root.querySelector("[data-map-tooltip]"),
            panel: root.querySelector("[data-point-inspector]"),
            content: root.querySelector("[data-point-inspector-content]"),
            close: root.querySelector("[data-point-inspector-close]"),
        },
        {
            activeMode: () => activeMode,
            interactionBlocked: () => editor.isActive() || painting,
            onError: showError,
            onModeChange(mode) {
                root.querySelectorAll("[data-atlas-interaction-mode]").forEach(button => {
                    button.classList.toggle("is-active", button.dataset.atlasInteractionMode === mode);
                });
                if (mode === "inspect") setStatus("Инспекция точки: нажмите на любое место карты.");
            },
        },
    );

    const createPolygon = document.querySelector("[name='create-map_polygon']");
    const placementPolygon = document.querySelector("[name='placement-map_polygon']");
    const placementRegion = document.querySelector("[name='placement-region_id']");
    const savePlacement = document.querySelector("[data-save-placement]");
    const createTemperature = document.querySelector("[name='create-base_temperature']");
    const createHumidity = document.querySelector("[name='create-humidity']");
    const createElevation = document.querySelector("[name='create-elevation']");
    const createBiome = document.querySelector("[name='create-biome']");
    const manualClimateToggle = document.querySelector("[name='create-use_manual_climate_overrides']");
    const manualClimateSettings = document.querySelector("[data-manual-climate-settings]");
    const autoFillStatus = document.querySelector("[data-auto-fill-status]");
    let previewTimer = null;
    let previewRequest = 0;

    function syncContourFields(ring, mode) {
        const serialized = ring.length >= 3 ? JSON.stringify(ring) : "";
        if (mode === "edit") {
            if (placementPolygon) placementPolygon.value = serialized;
            if (savePlacement) savePlacement.disabled = ring.length < 3;
        } else {
            if (createPolygon) createPolygon.value = serialized;
        }
    }

    function scheduleClimatePreview(ring) {
        clearTimeout(previewTimer);
        if (!ring || ring.length < 3 || !autoFillStatus || !config.campaign) return;
        previewTimer = setTimeout(() => applyClimatePreview(ring), 180);
    }

    async function applyClimatePreview(ring) {
        const requestId = ++previewRequest;
        autoFillStatus.textContent = "Читаю климатические данные World Data…";
        const previewUrl = root.dataset.climatePreviewUrl;
        if (!previewUrl) return;
        const query = new URLSearchParams({polygon: JSON.stringify(ring)});
        try {
            const response = await fetch(`${previewUrl}?${query}`, {headers: {"X-Requested-With": "XMLHttpRequest"}});
            const data = await response.json();
            if (requestId !== previewRequest) return;
            if (!response.ok) throw new Error(data.error || "preview failed");
            if (!manualClimateToggle?.checked) {
                if (createTemperature) createTemperature.value = data.base_temperature;
                if (createHumidity) createHumidity.value = data.humidity;
                if (createElevation) createElevation.value = data.elevation ?? "";
                if (createBiome) createBiome.value = data.biome || "";
            }
            const source = data.biome_source === "campaign_override"
                ? "локальная замена кампании"
                : (data.biome_source === "global_atlas" ? "общий атлас" : "не задан");
            const elevation = data.elevation === null ? "неизвестна" : `${data.elevation} м`;
            const prefix = manualClimateToggle?.checked ? "World Data для сравнения" : "Автоматически заполнено";
            autoFillStatus.textContent = `${prefix}: ${data.surface_label}; биом — ${data.biome_label} (${source}); температура ${data.base_temperature}°C; влажность ${data.humidity}%; высота ${elevation}.`;
        } catch (_) {
            if (requestId === previewRequest) autoFillStatus.textContent = "Не удалось получить климатические данные от сервера.";
        }
    }

    function syncManualClimateMode() {
        const manual = Boolean(manualClimateToggle?.checked);
        if (createBiome) createBiome.disabled = !manual;
        [createTemperature, createHumidity, createElevation].forEach(field => {
            if (field) field.readOnly = !manual;
        });
        if (manualClimateSettings) {
            manualClimateSettings.hidden = !manual;
            manualClimateSettings.querySelectorAll("input, select").forEach(field => { field.disabled = !manual; });
        }
        document.querySelector("[data-world-data-fields]")?.classList.toggle("is-manual", manual);
    }
    manualClimateToggle?.addEventListener("change", () => {
        syncManualClimateMode();
        try {
            const ring = JSON.parse(createPolygon?.value || "[]");
            scheduleClimatePreview(ring);
        } catch (_) {}
    });
    syncManualClimateMode();

    try {
        const placementRing = JSON.parse(placementPolygon?.value || "[]");
        const createRing = JSON.parse(createPolygon?.value || "[]");
        if (placementRing.length >= 3 && placementRegion?.value) {
            editor.start(normalizedRingToLatLngs(placementRing), {
                mode: "edit",
                regionId: Number(placementRegion.value),
            });
        } else if (createRing.length >= 3) {
            editor.start(normalizedRingToLatLngs(createRing), {mode: "draw", regionId: null});
            scheduleClimatePreview(createRing);
        }
    } catch (_) {}

    document.querySelectorAll("[data-place-region]").forEach(button => {
        button.addEventListener("click", () => {
            const regionId = Number(button.dataset.placeRegion);
            if (placementRegion) placementRegion.value = String(regionId);
            editor.startEdit(regionId);
            setStatus(`Редактируется контур: ${button.dataset.regionName || "регион"}.`);
        });
    });
    root.querySelector("[data-draw-new]")?.addEventListener("click", () => {
        if (placementRegion) placementRegion.value = "";
    });

    [document.querySelector("[data-create-region-form]"), document.querySelector("[data-placement-form]")].forEach(form => {
        form?.addEventListener("submit", event => {
            const field = form.matches("[data-placement-form]") ? placementPolygon : createPolygon;
            try {
                const ring = JSON.parse(field?.value || "[]");
                if (ring.length >= 3) return;
            } catch (_) {}
            event.preventDefault();
            setStatus("Нужно завершить контур минимум из трёх точек.");
            stage.scrollIntoView({behavior: "smooth", block: "center"});
        });
    });

    let painting = false;
    let paintDown = false;
    let erasing = false;
    let biomeOverrides = {...config.biomes.campaign_cells};
    const originalBiomeOverrides = {...biomeOverrides};
    let landMask = null;
    const layerEditor = root.querySelector("[data-layer-editor]");
    const layerForm = root.querySelector("[data-layer-form]");
    const layerCellsField = root.querySelector("[name='layer-layer_cells']");
    const biomeBrush = root.querySelector("[data-biome-brush]");
    const brushSize = root.querySelector("[data-brush-size]");
    const eraserButton = root.querySelector("[data-eraser]");

    async function ensureLandMask() {
        if (landMask) return landMask;
        const response = await fetch(config.static_data.land_mask_url);
        if (!response.ok) throw new Error("land mask unavailable");
        landMask = (await response.json()).values;
        return landMask;
    }

    function paintAt(event) {
        if (!painting || !landMask) return;
        const latlng = map.mouseEventToLatLng(event);
        const longitude = normalizeLongitude(latlng.lng);
        const latitude = Math.max(-90, Math.min(90, latlng.lat));
        const centerX = Math.max(0, Math.min(359, Math.floor((longitude + 180) / 360 * 360)));
        const centerY = Math.max(0, Math.min(179, Math.floor((90 - latitude) / 180 * 180)));
        const radius = Math.max(0, Number(brushSize?.value || 1) - 1);
        for (let y = centerY - radius; y <= centerY + radius; y += 1) {
            for (let x = centerX - radius; x <= centerX + radius; x += 1) {
                if (y < 0 || y >= 180) continue;
                const wrappedX = ((x % 360) + 360) % 360;
                if ((x - centerX) ** 2 + (y - centerY) ** 2 > radius ** 2 + 0.5) continue;
                const key = String(y * 360 + wrappedX);
                if (!landMask[Number(key)]) continue;
                if (erasing) delete biomeOverrides[key];
                else biomeOverrides[key] = biomeBrush.value;
            }
        }
        registry.campaignBiomeGrid.setCells(biomeOverrides);
        inspector.effectiveBiomes = {...config.biomes.global_cells, ...biomeOverrides};
    }

    async function startPainting() {
        if (editor.isActive()) {
            setStatus("Сначала завершите или отмените редактирование контура региона.");
            return;
        }
        try {
            await ensureLandMask();
        } catch (_) {
            showError("Маска суши недоступна; редактирование биомов выключено.");
            return;
        }
        inspector.setEnabled(false);
        painting = true;
        map.dragging.disable();
        mapElement.classList.add("atlas-map--painting");
        if (layerEditor) layerEditor.hidden = false;
        setStatus("Редактирование биомов: ведите кистью только по суше.");
    }

    function stopPainting(restore = false) {
        if (restore && painting) biomeOverrides = {...originalBiomeOverrides};
        registry.campaignBiomeGrid.setCells(biomeOverrides);
        inspector.effectiveBiomes = {...config.biomes.global_cells, ...biomeOverrides};
        painting = false;
        paintDown = false;
        erasing = false;
        map.dragging.enable();
        mapElement.classList.remove("atlas-map--painting");
        eraserButton?.classList.remove("is-active");
        if (layerEditor) layerEditor.hidden = true;
    }

    root.querySelector("[data-edit-layer]")?.addEventListener("click", startPainting);
    root.querySelector("[data-layer-cancel]")?.addEventListener("click", () => {
        stopPainting(true);
        setStatus("Изменения слоя отменены.");
    });
    eraserButton?.addEventListener("click", () => {
        erasing = !erasing;
        eraserButton.classList.toggle("is-active", erasing);
    });
    layerForm?.addEventListener("submit", () => {
        if (layerCellsField) layerCellsField.value = JSON.stringify(biomeOverrides);
    });
    mapElement.addEventListener("pointerdown", event => {
        if (!painting) return;
        paintDown = true;
        mapElement.setPointerCapture(event.pointerId);
        paintAt(event);
    });
    mapElement.addEventListener("pointermove", event => {
        if (painting && paintDown) paintAt(event);
    });
    const releasePaint = () => { paintDown = false; };
    mapElement.addEventListener("pointerup", releasePaint);
    mapElement.addEventListener("pointercancel", releasePaint);

    root.querySelector("[data-zoom-reset]")?.addEventListener("click", () => {
        map.setView(config.view.center, config.view.initial_zoom);
    });
    const zoomLabel = root.querySelector("[data-zoom-label]");
    const updateZoomLabel = () => { if (zoomLabel) zoomLabel.textContent = `z${map.getZoom()}`; };
    map.on("zoomend", updateZoomLabel);
    updateZoomLabel();

    const fullscreenButton = root.querySelector("[data-fullscreen]");
    fullscreenButton?.addEventListener("click", async () => {
        try {
            if (!document.fullscreenElement) await root.requestFullscreen();
            else await document.exitFullscreen();
        } catch (_) {
            showError("Браузер не разрешил полноэкранный режим.");
        }
    });
    document.addEventListener("fullscreenchange", () => {
        if (fullscreenButton) fullscreenButton.textContent = document.fullscreenElement ? "Выйти" : "На весь экран";
        window.setTimeout(() => map.invalidateSize({pan: false}), 50);
    });
    const resizeObserver = new ResizeObserver(() => map.invalidateSize({pan: false}));
    resizeObserver.observe(mapElement);

    if (!config.manifest.available) showError("Слои карты не собраны. Запустите manage.py build_planet_tiles.");
    setMode(config.active_layer);
    setStatus("Режим просмотра. Перетаскивайте карту; колесо меняет масштаб.");
    window.fardecosmiaAtlas = {map, config, registry, editor, inspector};
}
