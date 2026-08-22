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
