(function () {
    "use strict";

    var root = document.documentElement;
    var surface = document.querySelector("[data-character-surface]");
    if (!surface) {
        return;
    }

    var reducedQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    var desktopQuery = window.matchMedia("(min-width: 761px)");
    var radialField = surface.querySelector("[data-radial-layout]");
    var entranceFrame = null;
    var entranceCleanupTimer = null;
    var exitTimer = null;
    var exitSafetyTimer = null;
    var EXIT_DELAY_MS = 180;
    var EXIT_SAFETY_MS = 1200;
    var ENTRANCE_CLEANUP_MS = 920;

    function clearEntrance() {
        if (entranceFrame !== null) {
            window.cancelAnimationFrame(entranceFrame);
            entranceFrame = null;
        }
        window.clearTimeout(entranceCleanupTimer);
        root.classList.remove(
            "has-reflection-motion",
            "character-surface-is-entering",
            "character-surface-has-entered"
        );
    }

    function clearExit() {
        window.clearTimeout(exitTimer);
        window.clearTimeout(exitSafetyTimer);
        root.classList.remove(
            "character-surface-is-leaving",
            "memory-focus-is-opening"
        );
        surface.querySelectorAll(".is-transition-source, .is-opening").forEach(function (element) {
            element.classList.remove("is-transition-source", "is-opening");
        });
    }

    function finishEntranceSoon() {
        entranceCleanupTimer = window.setTimeout(clearEntrance, ENTRANCE_CLEANUP_MS);
    }

    function startEntrance() {
        if (reducedQuery.matches || root.classList.contains("character-surface-has-entered")) {
            clearEntrance();
            return;
        }
        root.classList.add("character-surface-is-entering");
        entranceFrame = window.requestAnimationFrame(function () {
            entranceFrame = window.requestAnimationFrame(function () {
                entranceFrame = null;
                root.classList.add("character-surface-has-entered");
                finishEntranceSoon();
            });
        });
    }

    function armEntrance() {
        if (reducedQuery.matches) {
            clearEntrance();
            return;
        }
        root.classList.add("has-reflection-motion");
        if (!radialField || !desktopQuery.matches || radialField.matches('[data-radial-layout-ready="true"]')) {
            startEntrance();
            return;
        }
        radialField.addEventListener("reflectiongeometrychange", startEntrance, { once: true });
    }

    function eligibleLink(event, link) {
        if (
            event.defaultPrevented || event.button !== 0 ||
            event.metaKey || event.ctrlKey || event.shiftKey || event.altKey ||
            link.target === "_blank" || link.hasAttribute("download")
        ) {
            return null;
        }
        var destination = new URL(link.href, window.location.href);
        if (
            destination.origin !== window.location.origin ||
            destination.href === window.location.href
        ) {
            return null;
        }
        return destination;
    }

    document.querySelectorAll("a[data-character-transition]").forEach(function (link) {
        link.addEventListener("click", function (event) {
            var destination = eligibleLink(event, link);
            if (!destination || reducedQuery.matches) {
                return;
            }

            event.preventDefault();
            clearEntrance();
            clearExit();

            var source = link.closest("[data-reflection-node], [data-memory-focused-thought]");
            if (source) {
                source.classList.add("is-transition-source");
            }
            var thought = link.closest("[data-memory-thought]");
            if (thought) {
                thought.classList.add("is-opening");
                root.classList.add("memory-focus-is-opening");
            }
            root.classList.add("character-surface-is-leaving");

            exitTimer = window.setTimeout(function () {
                window.location.assign(destination.href);
            }, EXIT_DELAY_MS);
            exitSafetyTimer = window.setTimeout(clearExit, EXIT_SAFETY_MS);
        });
    });

    document.addEventListener("keydown", function (event) {
        if (
            event.defaultPrevented || event.key !== "Escape" ||
            event.metaKey || event.ctrlKey || event.altKey
        ) {
            return;
        }
        var closeLink = surface.querySelector("a[data-memory-close]");
        if (!closeLink) {
            return;
        }
        event.preventDefault();
        closeLink.click();
    });

    window.addEventListener("pageshow", function (event) {
        clearExit();
        if (event.persisted) {
            clearEntrance();
        }
    });
    window.addEventListener("pagehide", function () {
        window.clearTimeout(exitSafetyTimer);
    });
    reducedQuery.addEventListener("change", function () {
        clearExit();
        if (reducedQuery.matches) {
            clearEntrance();
        }
    });
    desktopQuery.addEventListener("change", function () {
        if (root.classList.contains("has-reflection-motion")) {
            clearEntrance();
        }
    });

    armEntrance();
}());
