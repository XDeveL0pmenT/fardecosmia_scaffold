(function () {
    "use strict";

    var fields = Array.from(document.querySelectorAll("[data-reflection-connectors]")).map(function (layer) {
        return layer.closest("[data-radial-layout]");
    }).filter(Boolean);
    if (!fields.length) {
        return;
    }

    var desktopQuery = window.matchMedia("(min-width: 761px)");
    var pendingFields = new Set();
    var connectorFrame = null;
    var CORE_CLEARANCE = 8;
    var NODE_CLEARANCE = 13;
    var CORE_EXTENT_FACTOR = 0.72;
    var NODE_EXTENT_FACTOR = 0.82;

    var CORE_CLEARANCE = 4;
    var NODE_CLEARANCE = 3;
    var TARGETS = [
        { key: "party", selector: ".workspace-module--party" },
        { key: "map", selector: ".workspace-module--map" },
        { key: "life", selector: ".workspace-module--life" },
        { key: "tiamana", selector: ".workspace-module--tiamana" },
        { key: "quests", selector: ".workspace-module--quests" },
        { key: "notes", selector: ".workspace-module--notes" },
        { key: "apotheosis", selector: ".workspace-module--apotheosis" },
        { key: "inventory", selector: ".workspace-inventory" }
    ];

    function projectedHalfExtent(rect, unitX, unitY) {
        var horizontal = Math.abs(unitX) < 0.0001 ? Number.POSITIVE_INFINITY : rect.width / 2 / Math.abs(unitX);
        var vertical = Math.abs(unitY) < 0.0001 ? Number.POSITIVE_INFINITY : rect.height / 2 / Math.abs(unitY);
        return Math.min(horizontal, vertical);
    }

    function createConnector(layer, asset, target) {
        var connector = document.createElement("span");
        var texture = document.createElement("img");
        connector.className = "reflection-connector";
        connector.dataset.connectorFor = target.key;
        connector.dataset.connectorTarget = target.selector;
        texture.className = "reflection-connector__texture";
        texture.src = asset;
        texture.alt = "";
        texture.setAttribute("aria-hidden", "true");
        texture.draggable = false;
        texture.addEventListener("load", function () {
            scheduleField(layer.closest("[data-radial-layout]"));
        }, { once: true });
        connector.appendChild(texture);
        layer.appendChild(connector);
        return connector;
    }

    function connectorRecords(field) {
        var layer = field.querySelector("[data-reflection-connectors]");
        if (!layer) {
            return [];
        }
        var asset = layer.dataset.connectorAsset;
        return TARGETS.map(function (target) {
            var connector = layer.querySelector('[data-connector-for="' + target.key + '"]');
            if (!connector && asset) {
                connector = createConnector(layer, asset, target);
            }
            return {
                connector: connector,
                target: field.querySelector(target.selector)
            };
        }).filter(function (record) {
            return record.connector && record.target;
        });
    }

    function clearGeometry(field) {
        field.removeAttribute("data-connectors-ready");
        delete field.dataset.connectorGeometry;
        field.querySelectorAll("[data-connector-for]").forEach(function (connector) {
            connector.style.removeProperty("--connector-left");
            connector.style.removeProperty("--connector-top");
            connector.style.removeProperty("--connector-length");
            connector.style.removeProperty("--connector-angle");
            connector.hidden = true;
        });
    }

    function updateGeometry(field) {
        if (!desktopQuery.matches) {
            clearGeometry(field);
            return;
        }
        if (!field.matches('[data-radial-layout-ready="true"]')) {
            return;
        }

        var core = field.querySelector(".character-core");
        var coreVisual =
            field.querySelector(".character-core__portrait") ||
            field.querySelector(".character-core__aura") ||
            core;
        var records = connectorRecords(field);
        if (!core || !coreVisual || records.length !== TARGETS.length) {
            return;
        }

        var fieldRect = field.getBoundingClientRect();
        var coreRect = core.getBoundingClientRect();
        var coreVisualRect = coreVisual.getBoundingClientRect();
        var coreX = coreRect.left + coreRect.width / 2;
        var coreY = coreRect.top + coreRect.height / 2;
        var geometry = records.map(function (record) {
            var targetRect = record.target.getBoundingClientRect();
            var targetX = targetRect.left + targetRect.width / 2;
            var targetY = targetRect.top + targetRect.height / 2;
            var deltaX = targetX - coreX;
            var deltaY = targetY - coreY;
            var distance = Math.sqrt(deltaX * deltaX + deltaY * deltaY);
            if (distance < 1) {
                return null;
            }
            var unitX = deltaX / distance;
            var unitY = deltaY / distance;
            var startTrim =
                projectedHalfExtent(coreVisualRect, unitX, unitY) *
                CORE_EXTENT_FACTOR +
                CORE_CLEARANCE;

            var endTrim =
                projectedHalfExtent(targetRect, unitX, unitY) *
                NODE_EXTENT_FACTOR +
                NODE_CLEARANCE;
            var length = Math.max(0, distance - startTrim - endTrim);
            return {
                connector: record.connector,
                left: coreX - fieldRect.left + unitX * startTrim,
                top: coreY - fieldRect.top + unitY * startTrim,
                length: length,
                angle: Math.atan2(deltaY, deltaX) * 180 / Math.PI - 90
            };
        }).filter(Boolean);
        var geometryKey = geometry.map(function (item) {
            return [item.left, item.top, item.length, item.angle].map(Math.round).join(":");
        }).join("|");
        if (field.dataset.connectorGeometry === geometryKey) {
            return;
        }
        field.dataset.connectorGeometry = geometryKey;
        geometry.forEach(function (item) {
            item.connector.hidden = item.length < 12;
            item.connector.style.setProperty("--connector-left", item.left.toFixed(1) + "px");
            item.connector.style.setProperty("--connector-top", item.top.toFixed(1) + "px");
            item.connector.style.setProperty("--connector-length", item.length.toFixed(1) + "px");
            item.connector.style.setProperty("--connector-angle", item.angle.toFixed(2) + "deg");
        });
        field.setAttribute("data-connectors-ready", "true");
    }

    function syncFocus(field, node) {
        var coreFocused = Boolean(node && node.matches(".character-core"));
        field.classList.toggle("has-core-connector-focus", coreFocused);
        field.querySelectorAll("[data-connector-for]").forEach(function (connector) {
            var target = field.querySelector(connector.dataset.connectorTarget);
            connector.classList.toggle("is-focus-linked", Boolean(node && node === target));
        });
    }

    function flushConnectors() {
        connectorFrame = null;
        var batch = Array.from(pendingFields);
        pendingFields.clear();
        batch.forEach(updateGeometry);
    }

    function scheduleField(field) {
        if (!field) {
            return;
        }
        pendingFields.add(field);
        if (connectorFrame === null) {
            connectorFrame = window.requestAnimationFrame(flushConnectors);
        }
    }

    function scheduleAll() {
        fields.forEach(scheduleField);
    }

    fields.forEach(function (field) {
        var focusField = field.closest("[data-reflection-focus-field]");
        connectorRecords(field);
        field.addEventListener("reflectiongeometrychange", function () {
            scheduleField(field);
        });
        if (focusField) {
            focusField.addEventListener("reflectionfocuschange", function (event) {
                syncFocus(field, event.detail ? event.detail.node : null);
            });
        }
        scheduleField(field);
    });

    window.addEventListener("resize", scheduleAll, { passive: true });
    desktopQuery.addEventListener("change", function () {
        fields.forEach(function (field) {
            syncFocus(field, null);
        });
        scheduleAll();
    });
}());
