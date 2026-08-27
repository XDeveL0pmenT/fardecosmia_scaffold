(function () {
    "use strict";

    var fields = Array.from(document.querySelectorAll("[data-radial-layout]"));
    if (!fields.length) {
        return;
    }

    var desktopQuery = window.matchMedia("(min-width: 761px)");
    var pendingFields = new Set();
    var layoutFrame = null;
    var EDGE_PADDING = 24;
    var NODE_GAP = 20;
    var CORE_GAP = 46;
    var MAX_SOLVE_STEPS = 80;
    var BASE_RADIUS_X_FACTOR = 0.34;
    var TARGET_RADIUS_Y_RATIO = 1.05;
    var X_GROWTH = 1.018;
    var Y_GROWTH = 1.025;

    /*
     * Optical radial ring rather than a strict mathematical ellipse.
     *
     * The Reflection nodes have very different widths. With a strict 45°
     * ellipse, the wide Party/Inventory shards collide with the diagonal
     * shards while Quests/Tiamana already cap the global X radius at the
     * viewport edge. The old solver then had no choice but to grow Y, which
     * produced a tall/narrow ring (for example 554 x 817 at 1540px field
     * width).
     *
     * Stable semantic sectors remain, but diagonal nodes are allowed to sit
     * farther outward horizontally than a cos(45°) projection would permit.
     * This matches the visual mass of wide Dark Glass shards and keeps the
     * composition ring-like while preserving elastic ResizeObserver-driven
     * growth for future bounded content.
     */
    var ANCHORS = [
        { selector: ".workspace-module--party", x: 0.00, y: -1.00 },

        { selector: ".workspace-module--life", x: 0.92, y: -0.58 },

        { selector: ".workspace-module--quests", x: 1.3, y: 0.00 },

        { selector: ".workspace-module--apotheosis", x: 0.92, y: 0.58 },

        { selector: ".workspace-inventory", x: 0.00, y: 1.00 },

        { selector: ".workspace-module--notes", x: -0.92, y: 0.58 },

        { selector: ".workspace-module--tiamana", x: -1.3, y: 0.00 },

        { selector: ".workspace-module--map", x: -0.92, y: -0.58 }
    ];

    function bounded(value, minimum, maximum) {
        return Math.max(minimum, Math.min(maximum, value));
    }

    function clearPosition(element) {
        element.style.removeProperty("--radial-node-left");
        element.style.removeProperty("--radial-node-top");
    }

    function clearElasticGeometry(field) {
        field.style.removeProperty("--radial-field-height");
        field.style.removeProperty("--radial-center-x");
        field.style.removeProperty("--radial-center-y");
        field.style.removeProperty("--radial-radius-x");
        field.style.removeProperty("--radial-radius-y");
        field.querySelectorAll("[data-reflection-node]").forEach(clearPosition);
        field.removeAttribute("data-radial-layout-ready");
        delete field.dataset.radialGeometry;
    }

    function dimensions(element) {
        return {
            width: element.offsetWidth,
            height: Math.max(element.offsetHeight, element.scrollHeight)
        };
    }

    function resolveAnchors(field) {
        return ANCHORS.map(function (anchor) {
            var element = field.querySelector(anchor.selector);
            if (!element) {
                return null;
            }
            var size = dimensions(element);
            return {
                element: element,
                x: anchor.x,
                y: anchor.y,
                width: size.width,
                height: size.height
            };
        }).filter(Boolean);
    }

    function maximumHorizontalRadius(nodes, fieldWidth, edgePadding) {
        var centerX = fieldWidth / 2;
        return nodes.reduce(function (limit, node) {
            var direction = Math.abs(node.x);
            if (direction < 0.001) {
                return limit;
            }
            var available = centerX - edgePadding - node.width / 2;
            return Math.min(limit, Math.max(0, available / direction));
        }, Number.POSITIVE_INFINITY);
    }

    function rectangleFor(node, radiusX, radiusY) {
        return {
            x: radiusX * node.x,
            y: radiusY * node.y,
            halfWidth: node.width / 2,
            halfHeight: node.height / 2
        };
    }

    function rectanglesOverlap(a, b, gap) {
        return (
            Math.abs(a.x - b.x) < a.halfWidth + b.halfWidth + gap &&
            Math.abs(a.y - b.y) < a.halfHeight + b.halfHeight + gap
        );
    }

    function overlappingPairs(nodes, radiusX, radiusY) {
        var result = [];
        for (var first = 0; first < nodes.length; first += 1) {
            for (var second = first + 1; second < nodes.length; second += 1) {
                var gap = first === 0 ? CORE_GAP : NODE_GAP;
                if (rectanglesOverlap(
                    rectangleFor(nodes[first], radiusX, radiusY),
                    rectangleFor(nodes[second], radiusX, radiusY),
                    gap
                )) {
                    result.push([first, second]);
                }
            }
        }
        return result;
    }

    function solveRing(nodes, coreSize, fieldWidth) {
        var edgePadding = bounded(fieldWidth * 0.018, 18, EDGE_PADDING);
        var maxRadiusX = maximumHorizontalRadius(nodes, fieldWidth, edgePadding);
        var horizontalHalfWidth = nodes.reduce(function (value, node) {
            if (Math.abs(node.x) < 0.9) {
                return value;
            }
            return Math.max(value, node.width / 2);
        }, 0);
        var verticalHalfHeight = nodes.reduce(function (value, node) {
            if (Math.abs(node.y) < 0.9) {
                return value;
            }
            return Math.max(value, node.height / 2);
        }, 0);

        var radiusX = Math.min(
            maxRadiusX,
            Math.max(
                fieldWidth * BASE_RADIUS_X_FACTOR,
                coreSize.width / 2 + horizontalHalfWidth + CORE_GAP
            )
        );
        var radiusY = Math.max(
            radiusX * TARGET_RADIUS_Y_RATIO,
            coreSize.height / 2 + verticalHalfHeight + CORE_GAP
        );
        var coreNode = {
            x: 0,
            y: 0,
            width: coreSize.width,
            height: coreSize.height
        };
        var solveNodes = [coreNode].concat(nodes);

        /*
         * Prefer horizontal breathing while there is actual viewport room.
         * This is the key difference from the previous global ellipse: the
         * diagonal anchors already use x=±0.96, so a small X increase rapidly
         * clears Party/Inventory without forcing the whole scene taller.
         * Only after X reaches the real edge may Y grow independently.
         */
        for (var step = 0; step < MAX_SOLVE_STEPS; step += 1) {
            var overlaps = overlappingPairs(solveNodes, radiusX, radiusY);
            if (!overlaps.length) {
                break;
            }

            if (radiusX < maxRadiusX - 0.5) {
                radiusX = Math.min(maxRadiusX, radiusX * X_GROWTH + 2);
                radiusY = Math.max(radiusY, radiusX * TARGET_RADIUS_Y_RATIO);
            } else {
                radiusY = radiusY * Y_GROWTH + 2;
            }
        }

        return {
            radiusX: Math.round(Math.min(radiusX, maxRadiusX)),
            radiusY: Math.round(radiusY),
            edgePadding: edgePadding
        };
    }

    function positionField(field) {
        if (!desktopQuery.matches) {
            clearElasticGeometry(field);
            return;
        }

        var fieldWidth = field.clientWidth;
        var core = field.querySelector(".character-core");
        var nodes = resolveAnchors(field);
        if (!fieldWidth || !core || nodes.length !== ANCHORS.length) {
            return;
        }

        var coreSize = dimensions(core);
        var ring = solveRing(nodes, coreSize, fieldWidth);
        var relativeBounds = nodes.map(function (node) {
            var centerX = ring.radiusX * node.x;
            var centerY = ring.radiusY * node.y;
            return {
                node: node,
                centerX: centerX,
                centerY: centerY,
                top: centerY - node.height / 2,
                bottom: centerY + node.height / 2
            };
        });
        var minimumY = Math.min.apply(Math, [-(coreSize.height / 2)].concat(relativeBounds.map(function (item) {
            return item.top;
        })));
        var maximumY = Math.max.apply(Math, [coreSize.height / 2].concat(relativeBounds.map(function (item) {
            return item.bottom;
        })));
        var verticalPadding = bounded(fieldWidth * 0.018, 20, 32);
        var centerX = fieldWidth / 2;
        var centerY = verticalPadding - minimumY;
        var fieldHeight = maximumY - minimumY + verticalPadding * 2;
        var positions = relativeBounds.map(function (item) {
            return {
                element: item.node.element,
                left: centerX + item.centerX - item.node.width / 2,
                top: centerY + item.centerY - item.node.height / 2
            };
        });
        var coreLeft = centerX - coreSize.width / 2;
        var coreTop = centerY - coreSize.height / 2;
        var geometryKey = [
            Math.round(fieldWidth),
            ring.radiusX,
            ring.radiusY,
            Math.round(centerY),
            Math.round(fieldHeight)
        ].concat(nodes.map(function (node) {
            return node.width + "x" + node.height;
        })).join(":");

        if (field.dataset.radialGeometry === geometryKey) {
            return;
        }

        field.dataset.radialGeometry = geometryKey;
        field.style.setProperty("--radial-field-height", Math.ceil(fieldHeight) + "px");
        field.style.setProperty("--radial-center-x", Math.round(centerX) + "px");
        field.style.setProperty("--radial-center-y", Math.round(centerY) + "px");
        field.style.setProperty("--radial-radius-x", ring.radiusX + "px");
        field.style.setProperty("--radial-radius-y", ring.radiusY + "px");
        core.style.setProperty("--radial-node-left", Math.round(coreLeft) + "px");
        core.style.setProperty("--radial-node-top", Math.round(coreTop) + "px");
        positions.forEach(function (position) {
            position.element.style.setProperty("--radial-node-left", Math.round(position.left) + "px");
            position.element.style.setProperty("--radial-node-top", Math.round(position.top) + "px");
        });
        field.setAttribute("data-radial-layout-ready", "true");
        field.dispatchEvent(new CustomEvent("reflectiongeometrychange"));
    }

    function flushLayout() {
        layoutFrame = null;
        var batch = Array.from(pendingFields);
        pendingFields.clear();
        batch.forEach(positionField);
    }

    function scheduleField(field) {
        pendingFields.add(field);
        if (layoutFrame === null) {
            layoutFrame = window.requestAnimationFrame(flushLayout);
        }
    }

    var observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(function (entries) {
        entries.forEach(function (entry) {
            var field = entry.target.matches("[data-radial-layout]") ?
                entry.target : entry.target.closest("[data-radial-layout]");
            if (field) {
                scheduleField(field);
            }
        });
    });

    fields.forEach(function (field) {
        scheduleField(field);
        if (observer) {
            observer.observe(field);
            field.querySelectorAll("[data-reflection-node]").forEach(function (node) {
                observer.observe(node);
            });
        }
    });

    function scheduleAllFields() {
        fields.forEach(scheduleField);
    }

    window.addEventListener("resize", scheduleAllFields, { passive: true });
    desktopQuery.addEventListener("change", scheduleAllFields);
}());
