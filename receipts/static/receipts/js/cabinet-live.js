const POLL_INTERVAL_MS = 15000;

const STATUS_BADGES = {
  pending: { label: "В обработке", modifier: "badge--pending" },
  accepted: { label: "Обработан", modifier: "badge--accepted" },
  rejected: { label: "Ошибка", modifier: "badge--rejected" },
  won: { label: "Вы выиграли", modifier: "badge--won" },
};

function infoText(receipt) {
  if (receipt.status === "pending") return "Чек в обработке";
  if (receipt.status === "rejected") return receipt.reject_reason;
  if (receipt.status === "won") {
    return `Поздравляем, ваш чек выиграл! ${receipt.prize_title}`.trim();
  }
  return "";
}

function updateBadge(row, receipt, config) {
  const badge = STATUS_BADGES[receipt.status];
  const badgeEl = row.querySelector(".badge");
  badgeEl.className = `badge ${badge.modifier}`;
  badgeEl.innerHTML = "";

  if (receipt.status === "won") {
    const icon = document.createElement("img");
    icon.src = config.giftIconUrl;
    icon.alt = "";
    icon.className = "icon icon--sm";
    badgeEl.appendChild(icon);
  } else {
    const dot = document.createElement("span");
    dot.className = "badge__dot";
    badgeEl.appendChild(dot);
  }
  badgeEl.appendChild(document.createTextNode(badge.label));
}

function updateInfo(row, receipt, config) {
  const infoCell = row.querySelector(".cell--info");
  infoCell.innerHTML = "";

  const text = infoText(receipt);
  if (!text) return;

  const icon = document.createElement("img");
  icon.src = config.infoIconUrl;
  icon.alt = "";
  icon.className = "icon icon--muted";
  infoCell.append(icon, document.createTextNode(text));
}

function applyUpdates(receipts, config) {
  let hasPending = false;

  receipts.forEach((receipt) => {
    if (receipt.status === "pending") hasPending = true;

    const row = document.querySelector(`tr[data-receipt-id="${receipt.id}"]`);
    if (!row || row.dataset.status === receipt.status) return;

    row.dataset.status = receipt.status;
    updateBadge(row, receipt, config);
    updateInfo(row, receipt, config);

    row.classList.add("row--flash");
    setTimeout(() => row.classList.remove("row--flash"), 1500);
  });

  return hasPending;
}

function buildUrl(config) {
  const params = new URLSearchParams({ page: config.page, ordering: config.ordering });
  return `${config.receiptsUrl}?${params.toString()}`;
}

async function poll(config, state) {
  if (document.hidden) return;

  try {
    const headers = {};
    if (state.etag) headers["If-None-Match"] = state.etag;

    const response = await fetch(buildUrl(config), { credentials: "same-origin", headers });

    if (response.status === 304 || !response.ok) return;

    const etag = response.headers.get("ETag");
    if (etag) state.etag = etag;

    const data = await response.json();
    state.hasPending = applyUpdates(data.results, config);
  } catch {
    // сеть моргнула — подождём следующий тик, а не остановим опрос совсем
  }
}

function initCabinetLive() {
  const configEl = document.getElementById("cabinet-config");
  if (!configEl) return;

  const config = JSON.parse(configEl.textContent);
  if (!config.hasPending) return;

  const state = { etag: null, hasPending: true };

  const tick = async () => {
    await poll(config, state);
    if (state.hasPending) {
      setTimeout(tick, POLL_INTERVAL_MS);
    }
  };

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && state.hasPending) {
      poll(config, state);
    }
  });

  setTimeout(tick, POLL_INTERVAL_MS);
}

initCabinetLive();
