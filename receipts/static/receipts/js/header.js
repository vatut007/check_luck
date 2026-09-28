function initHeaderDropdown() {
  const container = document.querySelector("[data-header-user]");
  if (!container) return;
  const dropdown = container.querySelector("[data-header-dropdown]");

  container.addEventListener("click", (event) => {
    event.stopPropagation();
    dropdown.hidden = !dropdown.hidden;
  });

  container.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      dropdown.hidden = !dropdown.hidden;
    }
  });

  document.addEventListener("click", () => {
    dropdown.hidden = true;
  });
}

function initBurgerMenu() {
  const burger = document.querySelector("[data-header-burger]");
  const header = document.querySelector(".header");
  if (!burger || !header) return;

  burger.addEventListener("click", () => {
    header.classList.toggle("header--menu-open");
  });
}

initHeaderDropdown();
initBurgerMenu();
