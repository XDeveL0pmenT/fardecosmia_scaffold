(function () {
    "use strict";

    var root = document.documentElement;
    var fields = Array.from(document.querySelectorAll("[data-reflection-focus-field]"));
    if (!fields.length) {
        return;
    }

    var reducedQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    var pointerQuery = window.matchMedia("(hover: hover) and (pointer: fine)");
    var controllers = [];
    var motionFrame = null;
    var previousFrameTime = 0;
    var activePointerNode = null;
    var activeKeyboardNode = null;
    var activeNode = null;
    var pointerSuppressedUntil = 0;
    var pointerNeedsMovement = false;
    var lastPointerPosition = { x: null, y: null };

    function clamp(value) {
        return Math.max(0, Math.min(1, value));
    }

    function near(a, b) {
        return Math.abs(a - b) < 0.0008;
    }

    function response(deltaMs, durationMs) {
        return 1 - Math.exp(-Math.max(1, deltaMs) / durationMs);
    }

    function suppressPointerFor(durationMs) {
        pointerSuppressedUntil = window.performance.now() + durationMs;
    }

    function pointerIsSuppressed() {
        return window.performance.now() < pointerSuppressedUntil;
    }

    function suppressPointerUntilMovement() {
        pointerNeedsMovement = true;
    }

    function pointerEventIsAllowed(event) {
        if (reducedQuery.matches || !pointerQuery.matches || pointerIsSuppressed()) {
            return false;
        }
        if (pointerNeedsMovement) {
            var didMove = lastPointerPosition.x === null ||
                Math.abs(event.clientX - lastPointerPosition.x) > 1 ||
                Math.abs(event.clientY - lastPointerPosition.y) > 1;
            if (!didMove) {
                return false;
            }
            pointerNeedsMovement = false;
        }
        lastPointerPosition.x = event.clientX;
        lastPointerPosition.y = event.clientY;
        return true;
    }

    function nodeOwnsPointerPosition(node, event) {
        var hit = document.elementFromPoint(event.clientX, event.clientY);
        return Boolean(hit && node.contains(hit));
    }

    function controllerFor(element) {
        var field = element && element.closest("[data-reflection-focus-field]");
        return controllers.find(function (controller) {
            return controller.field === field;
        }) || null;
    }

    function writeScene(controller) {
        var sceneDx = controller.scene.x - 0.5;
        var sceneDy = controller.scene.y - 0.5;
        var nodeDx = controller.node.x - 0.5;
        var nodeDy = controller.node.y - 0.5;
        var values = {
            "--focus-x": (controller.scene.x * 100).toFixed(2) + "%",
            "--focus-y": (controller.scene.y * 100).toFixed(2) + "%",
            "--focus-bg-x": (sceneDx * -22).toFixed(2) + "px",
            "--focus-bg-y": (sceneDy * -16).toFixed(2) + "px",
            "--focus-node-x": (nodeDx * -7).toFixed(2) + "px",
            "--focus-node-y": (nodeDy * -5).toFixed(2) + "px"
        };
        Object.keys(values).forEach(function (name) {
            controller.field.style.setProperty(name, values[name]);
        });
    }

    function writeLocalLight(controller) {
        if (!activeNode || controllerFor(activeNode) !== controller) {
            return;
        }
        activeNode.style.setProperty("--node-focus-x", (controller.light.x * 100).toFixed(1) + "%");
        activeNode.style.setProperty("--node-focus-y", (controller.light.y * 100).toFixed(1) + "%");
    }

    function animate(frameTime) {
        var deltaMs = previousFrameTime ? Math.min(48, frameTime - previousFrameTime) : 16;
        var sceneFactor = response(deltaMs, 210);
        var nodeFactor = response(deltaMs, 118);
        var lightFactor = response(deltaMs, 58);
        var unsettled = false;
        previousFrameTime = frameTime;

        controllers.forEach(function (controller) {
            controller.scene.x += (controller.target.x - controller.scene.x) * sceneFactor;
            controller.scene.y += (controller.target.y - controller.scene.y) * sceneFactor;
            controller.node.x += (controller.target.x - controller.node.x) * nodeFactor;
            controller.node.y += (controller.target.y - controller.node.y) * nodeFactor;
            controller.light.x += (controller.lightTarget.x - controller.light.x) * lightFactor;
            controller.light.y += (controller.lightTarget.y - controller.light.y) * lightFactor;
            writeScene(controller);
            writeLocalLight(controller);

            if (
                !near(controller.scene.x, controller.target.x) ||
                !near(controller.scene.y, controller.target.y) ||
                !near(controller.node.x, controller.target.x) ||
                !near(controller.node.y, controller.target.y) ||
                !near(controller.light.x, controller.lightTarget.x) ||
                !near(controller.light.y, controller.lightTarget.y)
            ) {
                unsettled = true;
            }
        });

        if (unsettled && !document.hidden && pointerQuery.matches && !reducedQuery.matches) {
            motionFrame = window.requestAnimationFrame(animate);
            return;
        }
        controllers.forEach(function (controller) {
            controller.scene.x = controller.target.x;
            controller.scene.y = controller.target.y;
            controller.node.x = controller.target.x;
            controller.node.y = controller.target.y;
            controller.light.x = controller.lightTarget.x;
            controller.light.y = controller.lightTarget.y;
            writeScene(controller);
            writeLocalLight(controller);
        });
        motionFrame = null;
        previousFrameTime = 0;
    }

    function requestMotion() {
        if (motionFrame === null && !document.hidden && pointerQuery.matches && !reducedQuery.matches) {
            motionFrame = window.requestAnimationFrame(animate);
        }
    }

    function announceFocusChange(controller, node) {
        if (!controller) {
            return;
        }
        controller.field.dispatchEvent(new CustomEvent("reflectionfocuschange", {
            detail: { node: node || null }
        }));
    }

    function removeActiveNode() {
        if (!activeNode) {
            return;
        }
        var previous = activeNode;
        var controller = controllerFor(previous);
        previous.classList.remove("is-focus-target", "is-node-light-active");
        previous.style.setProperty("--node-focus-x", "50%");
        previous.style.setProperty("--node-focus-y", "50%");
        activeNode = null;
        if (controller) {
            controller.light.x = 0.5;
            controller.light.y = 0.5;
            controller.lightTarget.x = 0.5;
            controller.lightTarget.y = 0.5;
            controller.field.classList.remove("has-node-focus");
            announceFocusChange(controller, null);
        }
    }

    function setActiveNode(node, mode, event) {
        if (!node) {
            removeActiveNode();
            return;
        }
        if (activeNode !== node) {
            removeActiveNode();
            activeNode = node;
            node.classList.add("is-focus-target");
            var nextController = controllerFor(node);
            if (nextController) {
                nextController.field.classList.add("has-node-focus");
                announceFocusChange(nextController, node);
            }
        }
        node.classList.toggle("is-node-light-active", mode === "pointer");
        if (mode === "pointer" && event) {
            var controller = controllerFor(node);
            var bounds = node.getBoundingClientRect();
            controller.lightTarget.x = clamp((event.clientX - bounds.left) / Math.max(bounds.width, 1));
            controller.lightTarget.y = clamp((event.clientY - bounds.top) / Math.max(bounds.height, 1));
            if (!node.dataset.pointerLightPrimed) {
                controller.light.x = controller.lightTarget.x;
                controller.light.y = controller.lightTarget.y;
                node.dataset.pointerLightPrimed = "true";
            }
            requestMotion();
        }
    }

    function clearPointerFocus(options) {
        var restoreKeyboard = !options || options.restoreKeyboard !== false;
        if (activePointerNode) {
            delete activePointerNode.dataset.pointerLightPrimed;
        }
        activePointerNode = null;
        if (restoreKeyboard && activeKeyboardNode && activeKeyboardNode.isConnected && activeKeyboardNode.matches(":focus-within")) {
            setActiveNode(activeKeyboardNode, "keyboard", null);
        } else {
            removeActiveNode();
        }
    }

    function resetController(controller, immediate) {
        controller.bounds = null;
        controller.target.x = 0.5;
        controller.target.y = 0.5;
        controller.lightTarget.x = 0.5;
        controller.lightTarget.y = 0.5;
        controller.field.classList.remove("has-pointer-focus", "has-node-focus");
        if (immediate) {
            controller.scene.x = 0.5;
            controller.scene.y = 0.5;
            controller.node.x = 0.5;
            controller.node.y = 0.5;
            controller.light.x = 0.5;
            controller.light.y = 0.5;
            writeScene(controller);
        }
    }

    function resetMotion(immediate) {
        if (motionFrame !== null && immediate) {
            window.cancelAnimationFrame(motionFrame);
            motionFrame = null;
            previousFrameTime = 0;
        }
        activeKeyboardNode = null;
        clearPointerFocus({ restoreKeyboard: false });
        controllers.forEach(function (controller) {
            resetController(controller, immediate);
        });
        if (!immediate) {
            requestMotion();
        }
    }

    fields.forEach(function (field) {
        var controller = {
            field: field,
            bounds: null,
            scene: { x: 0.5, y: 0.5 },
            node: { x: 0.5, y: 0.5 },
            light: { x: 0.5, y: 0.5 },
            target: { x: 0.5, y: 0.5 },
            lightTarget: { x: 0.5, y: 0.5 }
        };
        controllers.push(controller);
        writeScene(controller);

        field.addEventListener("pointerenter", function (event) {
            if (!pointerEventIsAllowed(event)) {
                return;
            }
            controller.bounds = field.getBoundingClientRect();
            field.classList.add("has-pointer-focus");
        }, { passive: true });

        field.addEventListener("pointermove", function (event) {
            if (!pointerEventIsAllowed(event)) {
                return;
            }
            if (!controller.bounds) {
                controller.bounds = field.getBoundingClientRect();
            }
            controller.target.x = clamp((event.clientX - controller.bounds.left) / Math.max(controller.bounds.width, 1));
            controller.target.y = clamp((event.clientY - controller.bounds.top) / Math.max(controller.bounds.height, 1));
            if (activePointerNode && controllerFor(activePointerNode) === controller) {
                if (!nodeOwnsPointerPosition(activePointerNode, event)) {
                    clearPointerFocus({ restoreKeyboard: false });
                    requestMotion();
                    return;
                }
                var nodeBounds = activePointerNode.getBoundingClientRect();
                controller.lightTarget.x = clamp((event.clientX - nodeBounds.left) / Math.max(nodeBounds.width, 1));
                controller.lightTarget.y = clamp((event.clientY - nodeBounds.top) / Math.max(nodeBounds.height, 1));
            }
            requestMotion();
        }, { passive: true });

        field.addEventListener("pointerleave", function () {
            clearPointerFocus();
            resetController(controller, false);
            requestMotion();
        }, { passive: true });

        field.addEventListener("pointercancel", function () {
            resetMotion(true);
        }, { passive: true });

        field.addEventListener("reflectiongeometrychange", function () {
            controller.bounds = null;
            clearPointerFocus({ restoreKeyboard: true });
        });

        field.querySelectorAll("[data-reflection-node]").forEach(function (node) {
            node.addEventListener("pointerenter", function (event) {
                if (!pointerEventIsAllowed(event)) {
                    return;
                }
                if (!nodeOwnsPointerPosition(node, event)) {
                    return;
                }
                if (activePointerNode && activePointerNode !== node) {
                    delete activePointerNode.dataset.pointerLightPrimed;
                }
                activePointerNode = node;
                setActiveNode(node, "pointer", event);
            }, { passive: true });

            node.addEventListener("pointerleave", function () {
                if (activePointerNode !== node) {
                    return;
                }
                clearPointerFocus();
            }, { passive: true });
        });

        field.addEventListener("focusin", function (event) {
            var node = event.target.closest("[data-reflection-node]");
            if (!node || !field.contains(node)) {
                return;
            }
            activeKeyboardNode = node;
            if (!activePointerNode) {
                setActiveNode(node, "keyboard", null);
            }
        });

        field.addEventListener("focusout", function (event) {
            var node = event.target.closest("[data-reflection-node]");
            if (!node || node.contains(event.relatedTarget)) {
                return;
            }
            window.requestAnimationFrame(function () {
                activeKeyboardNode = field.querySelector("[data-reflection-node]:focus-within");
                if (!activePointerNode) {
                    setActiveNode(activeKeyboardNode, "keyboard", null);
                }
            });
        });
    });

    document.addEventListener("pointerout", function (event) {
        if (!event.relatedTarget) {
            suppressPointerUntilMovement();
            resetMotion(false);
        }
    }, { passive: true });
    window.addEventListener("blur", function () {
        suppressPointerFor(180);
        suppressPointerUntilMovement();
        resetMotion(true);
    });
    function resetPointerForViewportMotion() {
        suppressPointerFor(140);
        suppressPointerUntilMovement();
        clearPointerFocus({ restoreKeyboard: false });
        controllers.forEach(function (controller) {
            controller.bounds = null;
        });
    }
    document.addEventListener("wheel", resetPointerForViewportMotion, { passive: true, capture: true });
    document.addEventListener("scroll", resetPointerForViewportMotion, { passive: true, capture: true });
    window.addEventListener("scroll", resetPointerForViewportMotion, { passive: true });
    window.addEventListener("resize", resetPointerForViewportMotion, { passive: true });
    document.addEventListener("visibilitychange", function () {
        if (document.hidden) {
            suppressPointerFor(180);
            suppressPointerUntilMovement();
            resetMotion(true);
        }
    });
    reducedQuery.addEventListener("change", function () {
        resetMotion(true);
    });
    pointerQuery.addEventListener("change", function () {
        resetMotion(true);
    });

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
            resetMotion(true);
            var thought = link.closest("[data-memory-thought]");
            if (thought) {
                thought.classList.add("is-opening");
                root.classList.add("memory-focus-is-opening");
            }
            root.classList.add("character-surface-is-leaving");
            window.setTimeout(function () {
                window.location.assign(destination.href);
            }, 210);
        });
    });

    window.addEventListener("pageshow", function () {
        suppressPointerFor(180);
        suppressPointerUntilMovement();
        resetMotion(true);
        root.classList.remove("character-surface-is-leaving", "memory-focus-is-opening");
        root.classList.add("character-surface-is-arriving");
        window.setTimeout(function () {
            root.classList.remove("character-surface-is-arriving");
        }, 280);
    });
}());
