function initMobileSort() {
  const form = document.querySelector("[data-mobile-sort]");
  if (!form) return;

  const select = form.querySelector("select[name=ordering]");
  select.addEventListener("change", () => form.submit());
}

initMobileSort();
