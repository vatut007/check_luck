const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export class ApiError extends Error {
  constructor(status, data) {
    super(`API error ${status}`);
    this.status = status;
    this.data = data;
  }
}

function getCookie(name) {
  const match = document.cookie.match(new RegExp(`(^|;\\s*)${name}=([^;]*)`));
  return match ? decodeURIComponent(match[2]) : null;
}

/**
 * Единая обёртка над fetch(): куки сессии same-origin, CSRF-токен из cookie
 * на небезопасных методах, разбор JSON-ошибок, редирект на логин при 401/403.
 */
export async function apiFetch(url, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers || {});

  if (UNSAFE_METHODS.has(method)) {
    const csrftoken = getCookie("csrftoken");
    if (csrftoken) headers.set("X-CSRFToken", csrftoken);
  }

  const response = await fetch(url, {
    ...options,
    method,
    headers,
    credentials: "same-origin",
  });

  if (response.status === 401 || response.status === 403) {
    const next = encodeURIComponent(window.location.pathname);
    window.location.href = `/accounts/login/?next=${next}`;
    throw new ApiError(response.status, null);
  }

  let data = null;
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    data = await response.json();
  }

  if (!response.ok) {
    throw new ApiError(response.status, data);
  }

  return data;
}
