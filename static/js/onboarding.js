(() => {
    const button = document.querySelector("[data-copy-button]");
    const source = document.querySelector("[data-copy-source]");
    if (!button || !source) return;
    button.addEventListener("click", async () => {
        try {
            await navigator.clipboard.writeText(source.value);
            button.textContent = "Скопировано";
        } catch (_error) {
            source.focus();
            source.select();
            button.textContent = "Выделено";
        }
    });
})();

(() => {
    const countdown = document.querySelector("[data-resend-countdown]");
    const button = countdown?.querySelector("[data-resend-button]");
    const help = countdown?.querySelector("[data-resend-help]");
    if (!countdown || !button) return;

    const serverRemaining = Number.parseInt(countdown.dataset.remainingSeconds, 10);
    if (!Number.isFinite(serverRemaining) || serverRemaining <= 0) return;

    // Recalculate from a deadline on every tick so suspended/background tabs
    // resume at the correct visible value instead of replaying missed seconds.
    const deadline = Date.now() + serverRemaining * 1000;
    let timerId = null;

    const render = () => {
        const remaining = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
        if (remaining <= 0) {
            button.disabled = false;
            button.textContent = "Отправить код повторно";
            if (help) help.textContent = "Не получили письмо? Запросите новый код.";
            if (timerId !== null) window.clearInterval(timerId);
            return;
        }
        const minutes = Math.floor(remaining / 60);
        const seconds = remaining % 60;
        button.disabled = true;
        button.textContent = `Отправить код повторно через ${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
    };

    render();
    if (button.disabled) timerId = window.setInterval(render, 1000);
})();
