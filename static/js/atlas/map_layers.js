function tileOptions(layer, pane, maxZoom) {
    return {
        pane,
        tileSize: 256,
        minZoom: 0,
        maxZoom,
        maxNativeZoom: layer.native_zoom,
        noWrap: false,
        keepBuffer: 2,
        updateWhenIdle: false,
        attribution: "Карта Фардекосмии",
    };
}

export function createRasterLayer(layer, pane, maxZoom, onError) {
    if (!layer?.available) return null;
    const result = L.tileLayer(layer.url, tileOptions(layer, pane, maxZoom));
    result.on("tileerror", event => onError?.(event));
    return result;
}

function createLightBandLayer(bands, field, color, pane) {
    const Layer = L.GridLayer.extend({
        createTile(coords) {
            const canvas = document.createElement("canvas");
            const size = this.getTileSize();
            canvas.width = size.x;
            canvas.height = size.y;
            const context = canvas.getContext("2d");
            const worldWidth = 512 * (2 ** coords.z);
            const tileStart = coords.x * size.x;
            for (const band of bands) {
                const opacity = Math.max(0, Math.min(1, Number(band[field])));
                if (!opacity) continue;
                const start = band.x * worldWidth - tileStart;
                const width = band.width * worldWidth + 1;
                if (start + width < 0 || start > size.x) continue;
                context.fillStyle = `rgba(${color[0]}, ${color[1]}, ${color[2]}, ${opacity})`;
                context.fillRect(start, 0, width, size.y);
            }
            return canvas;
        },
    });
    return new Layer({pane, tileSize: 256, noWrap: false, updateWhenIdle: false});
}

function celestialLayers(celestial, pane) {
    if (!celestial) return [];
    const layers = [];
    const definitions = [
        ["star_longitude", "Звезда · пик света", "star"],
        ["ympha_longitude", "Ympha · пик Лика", "ympha"],
    ];
    for (const [field, label, kind] of definitions) {
        for (const shift of [-360, 0, 360]) {
            const longitude = Number(celestial[field]) + shift;
            layers.push(L.polyline(
                [[-90, longitude], [90, longitude]],
                {pane, className: `atlas-celestial atlas-celestial--${kind}`, interactive: false},
            ));
            layers.push(L.marker([82, longitude], {
                pane,
                interactive: false,
                icon: L.divIcon({
                    className: `atlas-celestial-label atlas-celestial-label--${kind}`,
                    html: `<span aria-hidden="true"></span>${label}`,
                    iconSize: [150, 24],
                    iconAnchor: [8, 12],
                }),
            }));
        }
    }
    return layers;
}

export function createLightLayers(light) {
    const bands = light?.bands || [];
    return [
        createLightBandLayer(bands, "star_opacity", [255, 240, 173], "lightStar"),
        createLightBandLayer(bands, "darkness_opacity", [0, 1, 6], "lightDarkness"),
        createLightBandLayer(bands, "ympha_opacity", [181, 31, 77], "lightYmpha"),
        ...celestialLayers(light?.celestial, "labels"),
    ];
}

export class BiomeGridLayer extends L.GridLayer {
    constructor(cells, palette, options = {}) {
        super({tileSize: 256, noWrap: false, updateWhenIdle: false, ...options});
        this.cells = {...(cells || {})};
        this.colors = Object.fromEntries((palette || []).map(item => [item.value, item.color]));
        this.gridWidth = options.gridWidth || 360;
        this.gridHeight = options.gridHeight || 180;
        this.alpha = options.alpha ?? 0.78;
    }

    setCells(cells) {
        this.cells = {...(cells || {})};
        this.redraw();
    }

    createTile(coords) {
        const canvas = document.createElement("canvas");
        const size = this.getTileSize();
        canvas.width = size.x;
        canvas.height = size.y;
        const context = canvas.getContext("2d");
        const worldWidth = 512 * (2 ** coords.z);
        const worldHeight = 256 * (2 ** coords.z);
        const tileX = coords.x * size.x;
        const tileY = coords.y * size.y;
        const firstX = Math.max(0, Math.floor(tileX / worldWidth * this.gridWidth));
        const lastX = Math.min(this.gridWidth - 1, Math.ceil((tileX + size.x) / worldWidth * this.gridWidth));
        const firstY = Math.max(0, Math.floor(tileY / worldHeight * this.gridHeight));
        const lastY = Math.min(this.gridHeight - 1, Math.ceil((tileY + size.y) / worldHeight * this.gridHeight));
        context.globalAlpha = this.alpha;
        for (let y = firstY; y <= lastY; y += 1) {
            for (let x = firstX; x <= lastX; x += 1) {
                const biome = this.cells[String(y * this.gridWidth + x)];
                const color = this.colors[biome];
                if (!color) continue;
                const left = Math.floor(x / this.gridWidth * worldWidth - tileX);
                const top = Math.floor(y / this.gridHeight * worldHeight - tileY);
                const right = Math.ceil((x + 1) / this.gridWidth * worldWidth - tileX);
                const bottom = Math.ceil((y + 1) / this.gridHeight * worldHeight - tileY);
                context.fillStyle = color;
                context.fillRect(left, top, Math.max(1, right - left), Math.max(1, bottom - top));
            }
        }
        return canvas;
    }
}

export function createLayerRegistry(map, config, onError) {
    const maxZoom = config.view.max_zoom;
    const base = createRasterLayer(config.layers.base, "baseRaster", maxZoom, onError);
    const temperature = createRasterLayer(config.layers.temperature, "staticClimate", maxZoom, onError);
    const elevation = createRasterLayer(config.layers.elevation, "staticClimate", maxZoom, onError);
    const globalBiomeTile = createRasterLayer(config.layers.biome, "staticClimate", maxZoom, onError);
    const globalBiomeGrid = globalBiomeTile ? null : new BiomeGridLayer(
        config.biomes.global_cells,
        config.biomes.palette,
        {
            pane: "staticClimate",
            gridWidth: config.biomes.grid_width,
            gridHeight: config.biomes.grid_height,
        },
    );
    const campaignBiomeGrid = new BiomeGridLayer(
        config.biomes.campaign_cells,
        config.biomes.palette,
        {
            pane: "campaignOverrides",
            gridWidth: config.biomes.grid_width,
            gridHeight: config.biomes.grid_height,
            alpha: 0.92,
        },
    );
    const light = createLightLayers(config.light);
    const modes = {
        base: [base],
        light: [base, ...light],
        temperature: [temperature],
        elevation: [elevation],
        biome: [base, globalBiomeTile || globalBiomeGrid, campaignBiomeGrid],
    };
    let active = [];

    return {
        campaignBiomeGrid,
        available(mode) {
            return Boolean(modes[mode]?.filter(Boolean).length);
        },
        setMode(mode) {
            active.forEach(layer => map.removeLayer(layer));
            active = (modes[mode] || modes.base).filter(Boolean);
            active.forEach(layer => layer.addTo(map));
        },
    };
}
