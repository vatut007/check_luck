import { apiFetch, ApiError } from "./api.js";

const VALIDATED_FIELDS = ["fn", "fd", "fp", "purchased_at", "amount"];
const DIGIT_FIELDS = ["fn", "fd", "fp"];

function formatDate(isoDate) {
  const [year, month, day] = isoDate.split("-");
  return `${day}.${month}.${year}`;
}

function validateFn(value, promo) {
  const trimmed = value.trim();
  const pattern = new RegExp(`^\\d{${promo.fn_length}}$`);
  if (!pattern.test(trimmed)) return `ФН должен содержать ровно ${promo.fn_length} цифр.`;
  return null;
}

function validateFd(value, promo) {
  const trimmed = value.trim();
  const pattern = new RegExp(`^\\d{1,${promo.fd_max_length}}$`);
  if (!pattern.test(trimmed)) return `ФД должен содержать от 1 до ${promo.fd_max_length} цифр.`;
  return null;
}

function validateFp(value, promo) {
  const trimmed = value.trim();
  const pattern = new RegExp(`^\\d{1,${promo.fp_max_length}}$`);
  if (!pattern.test(trimmed)) return `ФП должен содержать от 1 до ${promo.fp_max_length} цифр.`;
  return null;
}

function validateAmount(value, promo) {
  const normalized = value.trim().replace(",", ".");
  if (!normalized) return "Некорректная сумма.";
  const amount = Number(normalized);
  if (Number.isNaN(amount)) return "Некорректная сумма.";
  if (amount <= 0) return "Сумма должна быть положительной.";
  const decimals = normalized.split(".")[1];
  if (decimals && decimals.length > 2) return "Сумма — не более двух знаков после запятой.";
  if (amount < Number(promo.min_amount)) {
    return `Сумма чека должна быть не меньше ${promo.min_amount} ₽.`;
  }
  return null;
}

function validatePurchasedAt(value, promo) {
  if (!value) return "Введите дату покупки.";
  const datePart = value.slice(0, 10);
  if (datePart < promo.start_date || datePart > promo.end_date) {
    return `Акция проходит с ${formatDate(promo.start_date)} по ${formatDate(promo.end_date)}.`;
  }
  return null;
}

const VALIDATORS = {
  fn: validateFn,
  fd: validateFd,
  fp: validateFp,
  amount: validateAmount,
  purchased_at: validatePurchasedAt,
};

function setFieldError(input, message, config) {
  const field = input.closest(".field");
  const errorId = `${input.name}-error`;
  let errorEl = document.getElementById(errorId);

  if (message) {
    field.classList.add("field--error");
    input.setAttribute("aria-invalid", "true");
    input.setAttribute("aria-describedby", errorId);
    if (!errorEl) {
      errorEl = document.createElement("span");
      errorEl.id = errorId;
      errorEl.className = "field__error";
      field.appendChild(errorEl);
    }
    errorEl.innerHTML = "";
    const icon = document.createElement("img");
    icon.src = config.dangerIconUrl;
    icon.alt = "";
    icon.className = "icon";
    errorEl.append(icon, document.createTextNode(message));
  } else {
    field.classList.remove("field--error");
    input.setAttribute("aria-invalid", "false");
    input.removeAttribute("aria-describedby");
    if (errorEl) errorEl.remove();
  }
}

function validateField(name, input, promo, config) {
  const validator = VALIDATORS[name];
  const message = validator(input.value, promo);
  setFieldError(input, message, config);
  return !message;
}

function showGeneralError(form, message, status) {
  let banner = form.querySelector("[data-general-error]");
  if (!banner) {
    banner = document.createElement("div");
    banner.setAttribute("data-general-error", "");
    form.prepend(banner);
  }
  banner.className = status === 409 ? "form-error form-error--warning" : "form-error";
  banner.textContent = message;
}

function clearGeneralError(form) {
  const banner = form.querySelector("[data-general-error]");
  if (banner) banner.remove();
}

function filterDigits(event) {
  event.target.value = event.target.value.replace(/\D/g, "");
}

function showSuccessScreen(form, config) {
  const card = form.closest(".card");
  card.innerHTML = `
    <div class="success-screen">
      <img src="${config.checkIconUrl}" alt="" class="success-screen__icon">
      <h1>Чек отправлен на проверку</h1>
      <p class="success-screen__text">
        Проверка чека может занять до 5 рабочих дней. Мы сообщим о результате в личном кабинете.
      </p>
      <div class="success-screen__actions">
        <a href="${config.cabinetUrl}" class="button button--primary button--full">В личный кабинет</a>
        <a href="${config.formUrl}" class="button button--secondary button--full">Зарегистрировать ещё</a>
      </div>
    </div>
  `;
}

function handleApiError(error, form, config) {
  const data = error.data || {};
  const fieldErrors = data.errors || {};
  let firstInvalid = null;

  for (const [name, messages] of Object.entries(fieldErrors)) {
    const input = form.elements.namedItem(name);
    if (!input) continue;
    const message = Array.isArray(messages) ? messages[0] : messages;
    setFieldError(input, message, config);
    if (!firstInvalid) firstInvalid = input;
  }

  if (firstInvalid) {
    firstInvalid.focus();
  } else if (data.detail) {
    showGeneralError(form, data.detail, error.status);
  }
}

async function handleSubmit(event, form, promo, config) {
  event.preventDefault();

  let firstInvalid = null;
  for (const name of VALIDATED_FIELDS) {
    const input = form.elements.namedItem(name);
    const valid = validateField(name, input, promo, config);
    if (!valid && !firstInvalid) firstInvalid = input;
  }
  if (firstInvalid) {
    firstInvalid.focus();
    return;
  }

  clearGeneralError(form);
  const submitButton = form.querySelector("button[type=submit]");
  submitButton.disabled = true;

  try {
    const photoInput = form.elements.namedItem("photo");
    const hasPhoto = photoInput && photoInput.files.length > 0;
    let response;

    if (hasPhoto) {
      response = await apiFetch(config.receiptsUrl, {
        method: "POST",
        body: new FormData(form),
      });
    } else {
      const payload = {
        fn: form.elements.namedItem("fn").value.trim(),
        fd: form.elements.namedItem("fd").value.trim(),
        fp: form.elements.namedItem("fp").value.trim(),
        purchased_at: form.elements.namedItem("purchased_at").value,
        amount: form.elements.namedItem("amount").value.trim(),
      };
      response = await apiFetch(config.receiptsUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    }

    void response;
    showSuccessScreen(form, config);
  } catch (error) {
    if (error instanceof ApiError) {
      handleApiError(error, form, config);
    }
  } finally {
    submitButton.disabled = false;
  }
}

function highlightField(input) {
  const field = input.closest(".field");
  field.classList.add("field--highlight");
  setTimeout(() => field.classList.remove("field--highlight"), 1000);
}

async function handleQrFill(form, config) {
  const qrInput = document.getElementById("qr-input");
  const qrError = document.getElementById("qr-error");
  qrError.textContent = "";

  const raw = qrInput.value.trim();
  if (!raw) return;

  try {
    const data = await apiFetch(config.parseQrUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ raw }),
    });

    for (const name of VALIDATED_FIELDS) {
      const input = form.elements.namedItem(name);
      input.value = data[name];
      highlightField(input);
    }
  } catch (error) {
    if (error instanceof ApiError) {
      const data = error.data || {};
      const fieldErrors = data.errors || {};
      const rawErrors = fieldErrors.raw;
      qrError.textContent =
        (rawErrors && rawErrors[0]) || data.detail || "Не удалось разобрать строку из QR-кода.";
    }
  }
}

async function initReceiptForm() {
  const form = document.querySelector("[data-receipt-form]");
  if (!form) return;

  const configEl = document.getElementById("receipt-form-config");
  const config = JSON.parse(configEl.textContent);

  let promo;
  try {
    promo = await apiFetch(config.promoUrl);
  } catch {
    // Без правил акции с сервера JS-валидацию включать нельзя — форма
    // продолжает работать как обычная отправка (см. шаг 8).
    return;
  }

  DIGIT_FIELDS.forEach((name) => {
    form.elements.namedItem(name).addEventListener("input", filterDigits);
  });

  VALIDATED_FIELDS.forEach((name) => {
    const input = form.elements.namedItem(name);
    input.addEventListener("blur", () => validateField(name, input, promo, config));
  });

  form.addEventListener("submit", (event) => handleSubmit(event, form, promo, config));

  const qrButton = document.getElementById("qr-fill-button");
  if (qrButton) {
    qrButton.addEventListener("click", () => handleQrFill(form, config));
  }
}

initReceiptForm();
