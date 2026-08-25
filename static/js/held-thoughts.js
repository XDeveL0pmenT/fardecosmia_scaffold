(function () {
    "use strict";

    document.querySelectorAll("[data-held-thought-form]").forEach(function (form) {
        var steps = Array.from(form.querySelectorAll("[data-thought-step]"));
        var memo = form.querySelector("[name='memo']");
        var body = form.querySelector("[name='body']");

        function showStep(name, focusTarget) {
            steps.forEach(function (step) {
                var active = step.dataset.thoughtStep === name;
                step.classList.toggle("is-active", active);
                step.setAttribute("aria-hidden", active ? "false" : "true");
            });
            if (focusTarget) {
                focusTarget.focus({ preventScroll: true });
            }
        }

        form.classList.add("is-enhanced");
        showStep(form.dataset.initialStep === "body" ? "body" : "memo", null);

        var next = form.querySelector("[data-thought-next]");
        if (next) {
            next.addEventListener("click", function () {
                showStep("body", body);
            });
        }

        var skip = form.querySelector("[data-thought-skip]");
        if (skip) {
            skip.addEventListener("click", function (event) {
                event.preventDefault();
                memo.value = "";
                showStep("body", body);
            });
        }

        var back = form.querySelector("[data-thought-back]");
        if (back) {
            back.addEventListener("click", function () {
                showStep("memo", memo);
            });
        }
    });
}());

