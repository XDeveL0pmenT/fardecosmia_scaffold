(() => {
    const names = {
        minutes: ["минута", "минуты", "минут"],
        hours: ["час", "часа", "часов"],
        phases: ["фаза Витка", "фазы Витка", "фаз Витка"],
        turns: ["Виток", "Витка", "Витков"],
        seasons: ["сезон", "сезона", "сезонов"],
        years: ["год", "года", "лет"],
    };
    const plural = (value, forms) => {
        const mod100 = value % 100;
        const mod10 = value % 10;
        if (mod100 >= 11 && mod100 <= 14) return forms[2];
        if (mod10 === 1) return forms[0];
        if (mod10 >= 2 && mod10 <= 4) return forms[1];
        return forms[2];
    };
    document.querySelectorAll("[data-time-control]").forEach(form => {
        const unit = form.querySelector("[data-time-unit]");
        const amount = form.querySelector("[data-time-amount]");
        const output = form.querySelector("[data-time-output]");
        const maxLabel = form.querySelector("[data-time-max]");
        if (!unit || !amount || !output) return;
        const storageKey = `fardecosmia:time-control:${form.action}`;
        const readStored = () => {
            try {
                return JSON.parse(window.localStorage.getItem(storageKey) || "null");
            } catch (_) {
                return null;
            }
        };
        const store = () => {
            try {
                window.localStorage.setItem(storageKey, JSON.stringify({
                    unit: unit.value,
                    amount: Number(amount.value),
                }));
            } catch (_) {}
        };
        const render = () => {
            const value = Number(amount.value);
            output.value = `${value} ${plural(value, names[unit.value])}`;
            const span = Number(amount.max) - Number(amount.min);
            const progress = span ? ((value - Number(amount.min)) / span) * 100 : 100;
            amount.style.setProperty("--range-progress", `${progress}%`);
        };
        const applyUnitLimits = () => {
            const option = unit.selectedOptions[0];
            amount.max = option.dataset.max;
            if (maxLabel) maxLabel.textContent = option.dataset.max;
        };
        const stored = readStored();
        if (stored && Array.from(unit.options).some(option => option.value === String(stored.unit))) {
            unit.value = stored.unit;
        }
        applyUnitLimits();
        if (stored && Number.isFinite(Number(stored.amount))) {
            amount.value = Math.max(Number(amount.min), Math.min(Number(amount.max), Number(stored.amount)));
        }
        unit.addEventListener("change", () => {
            const option = unit.selectedOptions[0];
            applyUnitLimits();
            amount.value = option.dataset.default;
            render();
            store();
        });
        amount.addEventListener("input", () => { render(); store(); });
        form.addEventListener("submit", store);
        render();
    });
})();
