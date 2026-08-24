import {
    createFardecosmiaCRS,
    formatCoordinates,
    normalizeLongitude,
} from "./fardecosmia_crs.js?v=m1-leaflet-atlas";
import {createRasterLayer} from "./map_layers.js?v=m1-leaflet-atlas";

const root = document.querySelector("[data-character-placement-atlas]");
const configNode = document.getElementById("fardecosmia-atlas-config");

if (root && configNode && window.L) {
    const config = JSON.parse(configNode.textContent);
    const mapElement = root.querySelector("[data-leaflet-map]");
    const status = root.querySelector("[data-draw-status]");
    const errorBox = root.querySelector("[data-map-error]");
    const coordinates = root.querySelector("[data-cursor-coordinates]");
    const preview = root.querySelector("[data-location-preview] p");
    const form = root.querySelector("[data-location-placement-form]");
    const latitudeField = form?.querySelector("[name='latitude']");
    const longitudeField = form?.querySelector("[name='longitude']");
    const confirmedField = form?.querySelector("[name='confirmed']");
    const submitButton = form?.querySelector("[data-location-submit]");
    const setStatus = message => { if (status) status.textContent = message; };
    const showError = message => {
        if (!errorBox) return;
        errorBox.textContent = message;
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
    const basePane = map.createPane("baseRaster");
    basePane.style.zIndex = "200";
    const markerPane = map.createPane("featureMarkers");
    markerPane.style.zIndex = "500";
    L.control.zoom({position: "topright"}).addTo(map);

    const baseLayer = createRasterLayer(
        config.layers.base,
        "baseRaster",
        config.view.max_zoom,
        () => showError("Не удалось загрузить один или несколько тайлов атласа."),
    );
    if (baseLayer) baseLayer.addTo(map);
    else showError("Физическая карта недоступна. Соберите локальные тайлы атласа.");

    let marker = null;
    const hasPoint = () => latitudeField?.value !== "" && longitudeField?.value !== "";
    const syncSubmit = () => {
        if (submitButton) submitButton.disabled = !(hasPoint() && confirmedField?.checked);
    };
    const showPoint = (latitude, longitude, {move = false} = {}) => {
        const canonicalLongitude = normalizeLongitude(longitude);
        const canonicalLatitude = Math.max(-90, Math.min(90, Number(latitude)));
        const latlng = L.latLng(canonicalLatitude, canonicalLongitude);
        if (!marker) {
            marker = L.marker(latlng, {
                pane: "featureMarkers",
                icon: L.divIcon({
                    className: "character-location-marker",
                    html: "<span aria-hidden='true'>⌖</span>",
                    iconSize: [38, 38],
                    iconAnchor: [19, 19],
                }),
            }).addTo(map);
        } else {
            marker.setLatLng(latlng);
        }
        latitudeField.value = canonicalLatitude.toFixed(6);
        longitudeField.value = canonicalLongitude.toFixed(6);
        const label = formatCoordinates(latlng, 6);
        if (preview) preview.textContent = `Выбрано: ${label}`;
        if (coordinates) coordinates.textContent = label;
        if (confirmedField) {
            confirmedField.disabled = false;
            if (move) confirmedField.checked = false;
        }
        setStatus("Точка отмечена. Проверьте её и подтвердите выбор справа.");
        syncSubmit();
    };

    map.on("click", event => showPoint(event.latlng.lat, event.latlng.lng, {move: true}));
    root.querySelector("[data-zoom-reset]")?.addEventListener("click", () => {
        map.setView(config.view.center, config.view.initial_zoom);
    });
    const zoomLabel = root.querySelector("[data-zoom-label]");
    const updateZoomLabel = () => { if (zoomLabel) zoomLabel.textContent = `z${map.getZoom()}`; };
    map.on("zoomend", updateZoomLabel);
    updateZoomLabel();

    confirmedField?.addEventListener("change", syncSubmit);
    form?.addEventListener("submit", event => {
        if (hasPoint() && confirmedField?.checked) return;
        event.preventDefault();
        setStatus("Сначала выберите точку и подтвердите, что проверили её.");
    });

    const initialLatitude = Number(latitudeField?.value);
    const initialLongitude = Number(longitudeField?.value);
    if (hasPoint() && Number.isFinite(initialLatitude) && Number.isFinite(initialLongitude)) {
        showPoint(initialLatitude, initialLongitude);
    } else {
        if (confirmedField) confirmedField.disabled = true;
        setStatus("Нажмите на карту, чтобы отметить исходное положение.");
        syncSubmit();
    }

    const resizeObserver = new ResizeObserver(() => map.invalidateSize({pan: false}));
    resizeObserver.observe(mapElement);
    window.fardecosmiaCharacterPlacement = {map};
}
