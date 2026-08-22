export const WORLD_WIDTH_Z0 = 512;
export const WORLD_HEIGHT_Z0 = 256;

export function normalizeLongitude(longitude) {
    const value = Number(longitude);
    if (!Number.isFinite(value)) throw new TypeError("Longitude must be finite.");
    return ((value + 180) % 360 + 360) % 360 - 180;
}

export function clampLatitude(latitude) {
    const value = Number(latitude);
    if (!Number.isFinite(value)) throw new TypeError("Latitude must be finite.");
    return Math.max(-90, Math.min(90, value));
}

export function normalizedPointToLatLng(point) {
    const x = Number(point[0]);
    const y = Number(point[1]);
    if (!Number.isFinite(x) || !Number.isFinite(y) || x < 0 || x > 1 || y < 0 || y > 1) {
        throw new TypeError("Normalized map point is invalid.");
    }
    return L.latLng(90 - y * 180, x * 360 - 180);
}

export function latLngToNormalizedPoint(latlng) {
    const latitude = clampLatitude(latlng.lat);
    const longitude = normalizeLongitude(latlng.lng);
    return [
        Number(((longitude + 180) / 360).toFixed(6)),
        Number(((90 - latitude) / 180).toFixed(6)),
    ];
}

export function unwrapLatLngs(latlngs) {
    if (!latlngs.length) return [];
    const result = [L.latLng(latlngs[0].lat, normalizeLongitude(latlngs[0].lng))];
    for (let index = 1; index < latlngs.length; index += 1) {
        const previous = result[result.length - 1].lng;
        let longitude = normalizeLongitude(latlngs[index].lng);
        longitude += Math.round((previous - longitude) / 360) * 360;
        result.push(L.latLng(clampLatitude(latlngs[index].lat), longitude));
    }
    return result;
}

export function normalizedRingToLatLngs(points) {
    return unwrapLatLngs(points.map(normalizedPointToLatLng));
}

export function latLngsToNormalizedRing(latlngs) {
    return latlngs.map(latLngToNormalizedPoint);
}

export function shiftRingNearLongitude(latlngs, targetLongitude) {
    if (!latlngs.length) return [];
    const meanLongitude = latlngs.reduce((sum, point) => sum + point.lng, 0) / latlngs.length;
    const shift = Math.round((targetLongitude - meanLongitude) / 360) * 360;
    return latlngs.map(point => L.latLng(point.lat, point.lng + shift));
}

export function planetaryDistanceMeters(a, b, circumferenceKm) {
    const radiusMeters = Number(circumferenceKm) * 1000 / (2 * Math.PI);
    const latitudeA = Number(a.lat) * Math.PI / 180;
    const latitudeB = Number(b.lat) * Math.PI / 180;
    const deltaLatitude = latitudeB - latitudeA;
    const deltaLongitude = normalizeLongitude(Number(b.lng) - Number(a.lng)) * Math.PI / 180;
    const haversine = Math.sin(deltaLatitude / 2) ** 2
        + Math.cos(latitudeA) * Math.cos(latitudeB) * Math.sin(deltaLongitude / 2) ** 2;
    const angle = 2 * Math.atan2(Math.sqrt(haversine), Math.sqrt(Math.max(0, 1 - haversine)));
    return radiusMeters * angle;
}

export function createFardecosmiaCRS(circumferenceKm) {
    return L.Util.extend({}, L.CRS.EPSG4326, {
        code: "FARDECOSMIA:EQUIRECTANGULAR",
        wrapLng: [-180, 180],
        wrapLat: undefined,
        distance(a, b) {
            return planetaryDistanceMeters(a, b, circumferenceKm);
        },
    });
}

export function formatCoordinates(latlng, digits = 3) {
    const latitude = clampLatitude(latlng.lat);
    const longitude = normalizeLongitude(latlng.lng);
    const latitudeSuffix = latitude < 0 ? "S" : "N";
    const longitudeSuffix = longitude < 0 ? "W" : "E";
    return `${Math.abs(latitude).toFixed(digits)}°${latitudeSuffix} · ${Math.abs(longitude).toFixed(digits)}°${longitudeSuffix}`;
}
