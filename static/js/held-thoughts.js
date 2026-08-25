(function () {
    "use strict";

    document.querySelectorAll("[data-held-thought-form]").forEach(function (form) {
        var steps = Array.from(form.querySelectorAll("[data-thought-step]"));
        var memo = form.querySelector("[name='memo']");
        var body = form.querySelector("[name='body']");
        var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        var transitionTimer = null;
        var manifestationTimer = null;

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
            if (!transition || reducedMotion) {
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
            if (reducedMotion || event.isComposing) {
                return;
            }
            body.classList.remove("is-manifesting");
            void body.offsetWidth;
            body.classList.add("is-manifesting");
            window.clearTimeout(manifestationTimer);
            manifestationTimer = window.setTimeout(function () {
                body.classList.remove("is-manifesting");
            }, 180);
        }

        form.classList.add("is-enhanced");
        showStep(form.dataset.initialStep === "body" ? "body" : "memo", null, false);
        body.addEventListener("input", manifestWriting);
        body.addEventListener("compositionend", manifestWriting);

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
}());
