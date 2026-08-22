import {
    latLngsToNormalizedRing,
    normalizedRingToLatLngs,
    shiftRingNearLongitude,
} from "./fardecosmia_crs.js?v=m1-leaflet-atlas";

function regionPopup(region) {
    const root = document.createElement("div");
    root.className = "atlas-region-popup";
    const title = document.createElement("strong");
    title.textContent = region.name;
    root.append(title);
    const summary = document.createElement("p");
    summary.textContent = region.area_summary || "Физическое состояние территории пока недоступно.";
    root.append(summary);
    if (region.area_weather) {
        const meta = document.createElement("small");
        const freshness = region.area_weather.is_stale ? "устарел" : "актуален";
        meta.textContent = `Снимок: ${region.area_weather.world_minutes} мин. · возраст ${region.area_weather.age_minutes} мин. · ${freshness} · ${region.area_weather.sampling_mode}`;
        root.append(meta);
    }
    const link = document.createElement("a");
    link.href = region.detail_url;
    link.textContent = "Открыть регион";
    root.append(link);
    return root;
}

export class RegionContourController {
    constructor(map, regions, elements, callbacks = {}) {
        this.map = map;
        this.regions = regions || [];
        this.elements = elements;
        this.callbacks = callbacks;
        this.regionLayers = new Map();
        this.mode = "view";
        this.regionId = null;
        this.points = [];
        this.handles = [];
        this.completed = false;
        this.draft = L.polygon([], {
            pane: "editHandles",
            className: "atlas-region-draft",
            interactive: false,
        }).addTo(map);
        this.renderRegions();
        this.bindControls();
        this.map.on("moveend", () => this.refreshDisplayCopies());
        this.map.on("click", event => this.onMapClick(event));
        document.addEventListener("keydown", event => {
            if (event.key === "Escape" && this.isActive()) this.cancel();
        });
    }

    isActive() {
        return this.mode === "draw" || this.mode === "edit";
    }

    renderRegions() {
        this.regions.forEach(region => {
            const canonical = normalizedRingToLatLngs(region.polygon);
            const display = shiftRingNearLongitude(canonical, this.map.getCenter().lng);
            const layer = L.polygon(display, {
                pane: "regionBorders",
                className: "atlas-region-contour",
                color: region.temperature_color || "#ffffff",
                weight: 1.5,
                fillColor: region.temperature_color || "#a26eff",
                fillOpacity: 0.1,
            });
            layer.bindTooltip(region.name, {sticky: true, direction: "top"});
            layer.bindPopup(regionPopup(region), {maxWidth: 340});
            layer.on("click", event => {
                L.DomEvent.stopPropagation(event.originalEvent);
                this.callbacks.onRegionSelected?.(region);
            });
            layer.addTo(this.map);
            this.regionLayers.set(Number(region.id), {region, layer, canonical});
        });
    }

    refreshDisplayCopies() {
        for (const [id, entry] of this.regionLayers.entries()) {
            if (this.isActive() && id === Number(this.regionId)) continue;
            entry.layer.setLatLngs(
                shiftRingNearLongitude(entry.canonical, this.map.getCenter().lng),
            );
        }
    }

    bindControls() {
        this.elements.newButton?.addEventListener("click", () => this.startNew());
        this.elements.finishButton?.addEventListener("click", () => this.finish());
        this.elements.undoButton?.addEventListener("click", () => this.undo());
        this.elements.clearButton?.addEventListener("click", () => this.clear());
        this.elements.cancelButton?.addEventListener("click", () => this.cancel());
    }

    startNew() {
        this.start([], {mode: "draw", regionId: null});
    }

    startEdit(regionId) {
        const entry = this.regionLayers.get(Number(regionId));
        const ring = entry ? entry.canonical : [];
        this.start(ring, {mode: "edit", regionId: Number(regionId)});
    }

    start(latlngs, {mode, regionId}) {
        this.cancel(false);
        this.mode = mode;
        this.regionId = regionId;
        this.completed = false;
        this.points = shiftRingNearLongitude(latlngs, this.map.getCenter().lng);
        this.map.dragging.disable();
        this.map.getContainer().classList.add("atlas-map--editing");
        const entry = this.regionLayers.get(Number(regionId));
        entry?.layer.setStyle({opacity: 0, fillOpacity: 0});
        this.renderDraft();
        this.setStatus(
            mode === "edit"
                ? "Редактирование контура: перетаскивайте вершины или добавляйте новые."
                : "Новый контур: ставьте вершины на карте; замкните через первую точку или кнопку «Завершить»."
        );
        this.callbacks.onModeChange?.(this.mode, this.regionId);
    }

    onMapClick(event) {
        if (!this.isActive() || this.completed) return;
        this.points.push(L.latLng(event.latlng.lat, event.latlng.lng));
        this.renderDraft();
        this.emitChange();
    }

    createHandle(point, index) {
        const marker = L.marker(point, {
            pane: "editHandles",
            draggable: true,
            keyboard: true,
            zIndexOffset: 1000,
            icon: L.divIcon({
                className: `atlas-edit-handle${index === 0 ? " atlas-edit-handle--first" : ""}`,
                html: "<span></span>",
                iconSize: [14, 14],
                iconAnchor: [7, 7],
            }),
            title: index === 0 ? "Первая вершина — нажмите, чтобы замкнуть контур" : `Вершина ${index + 1}`,
        }).addTo(this.map);
        marker.on("drag", () => {
            this.points[index] = marker.getLatLng();
            this.completed = false;
            this.draft.setLatLngs(this.points);
            this.emitChange();
        });
        marker.on("click", event => {
            L.DomEvent.stopPropagation(event.originalEvent);
            if (index === 0 && this.points.length >= 3) this.finish();
        });
        return marker;
    }

    renderDraft() {
        this.handles.forEach(marker => marker.remove());
        this.handles = this.points.map((point, index) => this.createHandle(point, index));
        this.draft.setLatLngs(this.points);
        const hasPoints = this.points.length > 0;
        if (this.elements.undoButton) this.elements.undoButton.disabled = !hasPoints;
        if (this.elements.clearButton) this.elements.clearButton.disabled = !hasPoints;
        if (this.elements.finishButton) this.elements.finishButton.disabled = this.points.length < 3;
        this.setStatus(
            `Точек: ${this.points.length}. ${this.points.length < 3 ? "Нужно минимум три." : "Контур можно завершить."}`,
        );
    }

    emitChange() {
        this.callbacks.onChange?.(
            this.points.length >= 3 ? latLngsToNormalizedRing(this.points) : [],
            this.mode,
            this.regionId,
        );
    }

    finish() {
        if (!this.isActive() || this.points.length < 3) {
            this.setStatus("Нужно поставить минимум три точки контура.");
            return false;
        }
        this.completed = true;
        this.draft.setLatLngs(this.points);
        this.setStatus("Контур замкнут. Проверьте форму и сохраните изменения.");
        this.emitChange();
        this.callbacks.onFinish?.(latLngsToNormalizedRing(this.points), this.mode, this.regionId);
        return true;
    }

    undo() {
        if (!this.points.length) return;
        this.points.pop();
        this.completed = false;
        this.renderDraft();
        this.emitChange();
    }

    clear() {
        this.points = [];
        this.completed = false;
        this.renderDraft();
        this.emitChange();
    }

    cancel(announce = true) {
        const entry = this.regionLayers.get(Number(this.regionId));
        entry?.layer.setStyle({opacity: 1, fillOpacity: 0.1});
        this.points = [];
        this.completed = false;
        this.handles.forEach(marker => marker.remove());
        this.handles = [];
        this.draft.setLatLngs([]);
        this.mode = "view";
        this.regionId = null;
        this.map.dragging.enable();
        this.map.getContainer().classList.remove("atlas-map--editing");
        if (announce) this.setStatus("Режим просмотра. Перетаскивайте карту или выберите действие.");
        this.callbacks.onModeChange?.("view", null);
        this.refreshDisplayCopies();
    }

    setStatus(message) {
        if (this.elements.status) this.elements.status.textContent = message;
    }
}
