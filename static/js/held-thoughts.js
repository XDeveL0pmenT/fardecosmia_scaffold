(function () {
    "use strict";

    var root = document.documentElement;
    var reducedQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    var operationStorageKey = "fardecosmia-memory-operation";
    var newThoughtStorageKey = "fardecosmia-memory-new-thought";

    function rememberOperation(operation) {
        try {
            window.sessionStorage.setItem(operationStorageKey, operation);
        } catch (_error) {
            // Storage is an enhancement only; native form navigation remains valid.
        }
    }

    function consumeOperation() {
        try {
            var operation = window.sessionStorage.getItem(operationStorageKey);
            window.sessionStorage.removeItem(operationStorageKey);
            return operation;
        } catch (_error) {
            return null;
        }
    }

    function rememberNewThought(pathname) {
        try {
            window.sessionStorage.setItem(newThoughtStorageKey, pathname);
        } catch (_error) {
            // Native navigation remains the fallback when storage is unavailable.
        }
    }

    function consumeNewThought() {
        try {
            var pathname = window.sessionStorage.getItem(newThoughtStorageKey);
            window.sessionStorage.removeItem(newThoughtStorageKey);
            return pathname;
        } catch (_error) {
            return null;
        }
    }

    document.querySelectorAll("[data-held-thought-form]").forEach(function (form) {
        var steps = Array.from(form.querySelectorAll("[data-thought-step]"));
        var memo = form.querySelector("[name='memo']");
        var body = form.querySelector("[name='body']");
        var transitionTimer = null;
        var manifestationTimer = null;
        var manifestationFrame = null;

        function applyStep(name, focusTarget) {
            steps.forEach(function (step) {
                var active = step.dataset.thoughtStep === name;
                step.classList.toggle("is-active", active);
                step.setAttribute("aria-hidden", active ? "false" : "true");
            });
            if (focusTarget) {
                focusTarget.focus({ preventScroll: true });
            }
        }

        function showStep(name, focusTarget, transition) {
            window.clearTimeout(transitionTimer);
            if (!transition || reducedQuery.matches) {
                form.classList.remove("is-transitioning");
                applyStep(name, focusTarget);
                return;
            }
            form.classList.add("is-transitioning");
            transitionTimer = window.setTimeout(function () {
                applyStep(name, focusTarget);
                form.classList.remove("is-transitioning");
            }, 140);
        }

        function manifestWriting(event) {
            if (reducedQuery.matches || event.isComposing) {
                return;
            }
            body.classList.remove("is-manifesting");
            window.cancelAnimationFrame(manifestationFrame);
            manifestationFrame = window.requestAnimationFrame(function () {
                body.classList.add("is-manifesting");
            });
            window.clearTimeout(manifestationTimer);
            manifestationTimer = window.setTimeout(function () {
                body.classList.remove("is-manifesting");
            }, 180);
        }

        form.classList.add("is-enhanced");
        showStep(form.dataset.initialStep === "body" ? "body" : "memo", null, false);
        body.addEventListener("input", manifestWriting);
        body.addEventListener("compositionend", manifestWriting);
        form.addEventListener("submit", function () {
            rememberOperation(form.dataset.memoryOperation || "hold");
            if (!reducedQuery.matches) {
                root.classList.add("memory-write-is-completing");
            }
        });

        var next = form.querySelector("[data-thought-next]");
        if (next) {
            next.addEventListener("click", function () {
                showStep("body", body, true);
            });
        }

        var skip = form.querySelector("[data-thought-skip]");
        if (skip) {
            skip.addEventListener("click", function (event) {
                event.preventDefault();
                memo.value = "";
                showStep("body", body, true);
            });
        }

        var back = form.querySelector("[data-thought-back]");
        if (back) {
            back.addEventListener("click", function () {
                showStep("memo", memo, true);
            });
        }
    });

    var focusedThought = document.querySelector("[data-memory-focused-thought]");
    if (focusedThought) {
        var operation = consumeOperation();
        if (operation === "hold" || operation === "edit") {
            var stateClass = operation === "hold" ? "is-newly-held" : "is-returned";
            focusedThought.classList.add(stateClass);
            if (!reducedQuery.matches) {
                root.classList.add("memory-thought-has-settled");
                window.setTimeout(function () {
                    focusedThought.classList.remove(stateClass);
                    root.classList.remove("memory-thought-has-settled");
                }, 760);
            }

            if (operation === "hold") {
                var closeLink = document.querySelector("[data-memory-close]");
                if (closeLink) {
                    var returnToMemoryField = function () {
                        rememberNewThought(window.location.pathname);
                        window.location.replace(closeLink.href);
                    };
                    if (reducedQuery.matches) {
                        returnToMemoryField();
                    } else {
                        window.setTimeout(function () {
                            root.classList.add("memory-thought-is-returning");
                            window.setTimeout(returnToMemoryField, 180);
                        }, 760);
                    }
                }
            }
        }
        window.requestAnimationFrame(function () {
            focusedThought.focus({ preventScroll: true });
        });
    }

    var memoryIndex = document.querySelector("[data-memory-index]");
    if (memoryIndex) {
        var newThoughtPath = consumeNewThought();
        if (newThoughtPath) {
            var newThought = Array.from(document.querySelectorAll("[data-memory-thought]")).find(function (thought) {
                return new URL(thought.href, window.location.href).pathname === newThoughtPath;
            });
            if (newThought) {
                root.classList.add("memory-field-is-settling");
                newThought.classList.add("is-newly-held-in-field");
                newThought.focus({ preventScroll: true });
                if (!reducedQuery.matches) {
                    window.setTimeout(function () {
                        newThought.classList.remove("is-newly-held-in-field");
                        root.classList.remove("memory-field-is-settling");
                    }, 1200);
                }
            }
        }
    }

    var releaseForm = document.querySelector("[data-memory-release-form]");
    if (releaseForm) {
        releaseForm.addEventListener("submit", function () {
            if (!reducedQuery.matches) {
                root.classList.add("memory-thought-is-releasing");
            }
        });
    }
}());
