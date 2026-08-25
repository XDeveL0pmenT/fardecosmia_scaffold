(function () {
    "use strict";

    var root = document.documentElement;
    var fields = Array.from(document.querySelectorAll("[data-reflection-focus-field]"));
    if (!fields.length) {
        return;
    }

    var reducedQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    var pointerQuery = window.matchMedia("(hover: hover) and (pointer: fine)");
    var current = { x: 0.5, y: 0.5 };
    var target = { x: 0.5, y: 0.5 };
    var frame = null;

    function setFocusVariables(field) {
        var dx = current.x - 0.5;
        var dy = current.y - 0.5;
        var values = {
            "--focus-x": (current.x * 100).toFixed(2) + "%",
            "--focus-y": (current.y * 100).toFixed(2) + "%",
            "--focus-bg-x": (dx * -40).toFixed(2) + "px",
            "--focus-bg-y": (dy * -30).toFixed(2) + "px",
            "--focus-node-x": (dx * -13).toFixed(2) + "px",
            "--focus-node-y": (dy * -10).toFixed(2) + "px"
        };
        Object.keys(values).forEach(function (name) {
            root.style.setProperty(name, values[name]);
            field.style.setProperty(name, values[name]);
        });
    }

    function resetFocusVariables(field) {
        current.x = 0.5;
        current.y = 0.5;
        target.x = 0.5;
        target.y = 0.5;
        setFocusVariables(field);
    }

    function settle(field) {
        var distanceX = target.x - current.x;
        var distanceY = target.y - current.y;
        current.x += distanceX * 0.115;
        current.y += distanceY * 0.115;
        setFocusVariables(field);

        if (Math.abs(distanceX) > 0.001 || Math.abs(distanceY) > 0.001) {
            frame = window.requestAnimationFrame(function () {
                settle(field);
            });
            return;
        }
        current.x = target.x;
        current.y = target.y;
        setFocusVariables(field);
        frame = null;
    }

    function requestSettle(field) {
        if (frame === null && !document.hidden) {
            frame = window.requestAnimationFrame(function () {
                settle(field);
            });
        }
    }

    function clearNodeFocus(field, except) {
        field.querySelectorAll("[data-reflection-node].is-focus-target").forEach(function (node) {
            if (node !== except && !node.matches(":focus-within")) {
                node.classList.remove("is-focus-target");
            }
        });
        field.classList.toggle("has-node-focus", Boolean(except));
    }

    function focusNode(field, node, event) {
        if (!node) {
            clearNodeFocus(field, null);
            return;
        }
        clearNodeFocus(field, node);
        node.classList.add("is-focus-target");
        field.classList.add("has-node-focus");
        if (event && typeof event.clientX === "number") {
            var bounds = node.getBoundingClientRect();
            var localX = Math.max(0, Math.min(1, (event.clientX - bounds.left) / Math.max(bounds.width, 1)));
            var localY = Math.max(0, Math.min(1, (event.clientY - bounds.top) / Math.max(bounds.height, 1)));
            node.style.setProperty("--node-focus-x", (localX * 100).toFixed(1) + "%");
            node.style.setProperty("--node-focus-y", (localY * 100).toFixed(1) + "%");
        }
    }

    fields.forEach(function (field) {
        var bounds = null;
        resetFocusVariables(field);

        field.addEventListener("pointerenter", function () {
            if (!reducedQuery.matches && pointerQuery.matches) {
                bounds = field.getBoundingClientRect();
                field.classList.add("has-pointer-focus");
            }
        }, { passive: true });

        field.addEventListener("pointermove", function (event) {
            if (reducedQuery.matches || !pointerQuery.matches) {
                return;
            }
            if (!bounds) {
                bounds = field.getBoundingClientRect();
            }
            target.x = Math.max(0, Math.min(1, (event.clientX - bounds.left) / Math.max(bounds.width, 1)));
            target.y = Math.max(0, Math.min(1, (event.clientY - bounds.top) / Math.max(bounds.height, 1)));
            requestSettle(field);
            var node = event.target.closest("[data-reflection-node]");
            if (node && field.contains(node)) {
                focusNode(field, node, event);
            } else if (!field.querySelector("[data-reflection-node]:focus-within")) {
                clearNodeFocus(field, null);
            }
        }, { passive: true });

        field.addEventListener("pointerleave", function () {
            bounds = null;
            target.x = 0.5;
            target.y = 0.5;
            field.classList.remove("has-pointer-focus");
            clearNodeFocus(field, null);
            requestSettle(field);
        }, { passive: true });

        field.addEventListener("focusin", function (event) {
            var node = event.target.closest("[data-reflection-node]");
            if (node && field.contains(node)) {
                focusNode(field, node, null);
            }
        });

        field.addEventListener("focusout", function (event) {
            var node = event.target.closest("[data-reflection-node]");
            if (!node || node.contains(event.relatedTarget)) {
                return;
            }
            window.requestAnimationFrame(function () {
                var next = field.querySelector("[data-reflection-node]:focus-within");
                clearNodeFocus(field, next);
                if (next) {
                    next.classList.add("is-focus-target");
                }
            });
        });
    });

    function resetMotion() {
        if (frame !== null) {
            window.cancelAnimationFrame(frame);
            frame = null;
        }
        fields.forEach(function (field) {
            field.classList.remove("has-pointer-focus", "has-node-focus");
            field.querySelectorAll(".is-focus-target").forEach(function (node) {
                node.classList.remove("is-focus-target");
            });
            resetFocusVariables(field);
        });
    }

    document.addEventListener("visibilitychange", function () {
        if (document.hidden) {
            resetMotion();
        }
    });
    reducedQuery.addEventListener("change", resetMotion);
    pointerQuery.addEventListener("change", resetMotion);

    document.querySelectorAll("[data-character-transition]").forEach(function (link) {
        link.addEventListener("click", function (event) {
            if (
                reducedQuery.matches || event.defaultPrevented || event.button !== 0 ||
                event.metaKey || event.ctrlKey || event.shiftKey || event.altKey ||
                link.target === "_blank"
            ) {
                return;
            }
            var destination = new URL(link.href, window.location.href);
            if (destination.origin !== window.location.origin || destination.href === window.location.href) {
                return;
            }
            event.preventDefault();
            var thought = link.closest("[data-memory-thought]");
            if (thought) {
                thought.classList.add("is-opening");
                root.classList.add("memory-focus-is-opening");
            }
            root.classList.add("character-surface-is-leaving");
            window.setTimeout(function () {
                window.location.assign(destination.href);
            }, 170);
        });
    });

    window.addEventListener("pageshow", function () {
        root.classList.remove("character-surface-is-leaving", "memory-focus-is-opening");
        root.classList.add("character-surface-is-arriving");
        window.setTimeout(function () {
            root.classList.remove("character-surface-is-arriving");
        }, 320);
    });
}());
