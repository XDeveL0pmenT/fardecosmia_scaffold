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
    var MAX_SOLVE_STEPS = 60;
    var BASE_RADIUS_X_FACTOR = 0.29;
    var TARGET_RADIUS_Y_RATIO = 0.88;
    var ELLIPSE_GROWTH = 1.028;

    /*
     * Eight stable 45-degree anchors form a real ring.  Node dimensions are
     * allowed to change, but only the ellipse radii expand; semantic angles do
     * not drift.  This makes future bounded Inventory/Party/Quest previews
     * enlarge the Reflection without turning it back into rows or a tall tree.
     */
    var ANCHORS = [
        { selector: ".workspace-module--party", angle: -90 },
        { selector: ".workspace-module--life", angle: -45 },
        { selector: ".workspace-module--quests", angle: 0 },
        { selector: ".workspace-module--apotheosis", angle: 45 },
        { selector: ".workspace-inventory", angle: 90 },
        { selector: ".workspace-module--notes", angle: 135 },
        { selector: ".workspace-module--tiamana", angle: 180 },
        { selector: ".workspace-module--map", angle: 225 }
    ];

    function bounded(value, minimum, maximum) {
        return Math.max(minimum, Math.min(maximum, value));
    }

    function radians(degrees) {
        return degrees * Math.PI / 180;
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
            var angle = radians(anchor.angle);
            var size = dimensions(element);
            return {
                element: element,
                angle: anchor.angle,
                cos: Math.cos(angle),
                sin: Math.sin(angle),
                width: size.width,
                height: size.height
            };
        }).filter(Boolean);
    }

    function maximumHorizontalRadius(nodes, fieldWidth, edgePadding) {
        var centerX = fieldWidth / 2;
        return nodes.reduce(function (limit, node) {
            var direction = Math.abs(node.cos);
            if (direction < 0.001) {
                return limit;
            }
            var available = centerX - edgePadding - node.width / 2;
            return Math.min(limit, Math.max(0, available / direction));
        }, Number.POSITIVE_INFINITY);
    }

    function rectangleFor(node, radiusX, radiusY) {
        return {
            x: radiusX * node.cos,
            y: radiusY * node.sin,
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

    function hasOverlap(nodes, radiusX, radiusY) {
        for (var first = 0; first < nodes.length; first += 1) {
            for (var second = first + 1; second < nodes.length; second += 1) {
                var gap = first === 0 ? CORE_GAP : NODE_GAP;
                if (rectanglesOverlap(
                    rectangleFor(nodes[first], radiusX, radiusY),
                    rectangleFor(nodes[second], radiusX, radiusY),
                    gap
                )) {
                    return true;
                }
            }
        }
        return false;
    }

    function solveEllipse(nodes, coreSize, fieldWidth) {
        var edgePadding = bounded(fieldWidth * 0.018, 18, EDGE_PADDING);
        var maxRadiusX = maximumHorizontalRadius(nodes, fieldWidth, edgePadding);
        var horizontalHalfWidth = nodes.reduce(function (value, node) {
            if (Math.abs(node.cos) < 0.7) {
                return value;
            }
            return Math.max(value, node.width / 2);
        }, 0);
        var verticalHalfHeight = nodes.reduce(function (value, node) {
            if (Math.abs(node.sin) < 0.7) {
                return value;
            }
            return Math.max(value, node.height / 2);
        }, 0);

        var radiusX = Math.min(
            maxRadiusX,
            Math.max(fieldWidth * BASE_RADIUS_X_FACTOR, coreSize.width / 2 + horizontalHalfWidth + CORE_GAP)
        );
        var radiusY = Math.max(
            radiusX * TARGET_RADIUS_Y_RATIO,
            coreSize.height / 2 + verticalHalfHeight + CORE_GAP
        );
        var coreNode = {
            cos: 0,
            sin: 0,
            width: coreSize.width,
            height: coreSize.height
        };
        var solveNodes = [coreNode].concat(nodes);

        /*
         * Grow the ellipse as one shape instead of choosing a single axis per
         * collision.  The previous solver could feed a tall wrapped shard back
         * into radiusY repeatedly and create the giant vertical layout seen in
         * visual QA.  Horizontal growth stops only at the real viewport edge;
         * after that, Y alone may grow as a last resort.
         */
        for (var step = 0; step < MAX_SOLVE_STEPS; step += 1) {
            if (!hasOverlap(solveNodes, radiusX, radiusY)) {
                break;
            }
            if (radiusX < maxRadiusX - 1) {
                var grownRadiusX = Math.min(maxRadiusX, radiusX * ELLIPSE_GROWTH + 3);
                var growthRatio = grownRadiusX / Math.max(radiusX, 1);
                radiusX = grownRadiusX;
                radiusY = Math.max(
                    radiusY * growthRatio,
                    radiusX * TARGET_RADIUS_Y_RATIO
                );
            } else {
                radiusY = radiusY * ELLIPSE_GROWTH + 3;
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
        var ellipse = solveEllipse(nodes, coreSize, fieldWidth);
        var relativeBounds = nodes.map(function (node) {
            var centerX = ellipse.radiusX * node.cos;
            var centerY = ellipse.radiusY * node.sin;
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
            ellipse.radiusX,
            ellipse.radiusY,
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
        field.style.setProperty("--radial-radius-x", ellipse.radiusX + "px");
        field.style.setProperty("--radial-radius-y", ellipse.radiusY + "px");
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
