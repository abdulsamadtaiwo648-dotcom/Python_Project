// Typed client for the FastAPI backend. Every write carries the CSRF token
// the server issued with the session.

export class ApiError extends Error {
  constructor(message: string, public status: number, public body?: unknown) {
    super(message);
  }
}

export interface SessionUser {
  id: string;
  email: string;
  first_name: string | null;
  last_name: string | null;
  /** The owner's business is a test business: test reset is available to its owner. */
  is_test_business?: boolean;
}

export interface Access {
  is_owner: boolean;
  is_staff: boolean;
  role: string;
  role_label?: string;
  /** Page keys this person may use. The owner has them all. */
  pages: string[];
  business_id?: string;
}

export interface SessionInfo {
  status: "ok";
  csrf_token: string;
  user: (SessionUser & { business_owner?: string }) | null;
  access: Access | null;
}

let csrfToken = "";

export async function loadSession(): Promise<SessionInfo> {
  const res = await fetch("/api/session", { credentials: "same-origin", cache: "no-store" });
  const body = (await res.json()) as SessionInfo;
  csrfToken = body.csrf_token;
  return body;
}

type Method = "GET" | "POST" | "PUT" | "DELETE";

async function request<T>(method: Method, url: string, body?: unknown, opId?: string): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  let payload: BodyInit | undefined;
  if (body instanceof FormData) {
    payload = body;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  if (method !== "GET") {
    if (!csrfToken) await loadSession();
    headers["X-CSRFToken"] = csrfToken;
    if (opId) headers["X-Client-Op"] = opId;
  }
  let res = await fetch(url, { method, headers, body: payload, credentials: "same-origin" });
  if (res.status === 400 && method !== "GET") {
    // A stale security token (the session was renewed elsewhere): fetch a fresh one and try once more.
    const peek = (await res.clone().json().catch(() => null)) as { message?: string } | null;
    if (peek?.message && /token/i.test(peek.message)) {
      await loadSession();
      headers["X-CSRFToken"] = csrfToken;
      res = await fetch(url, { method, headers, body: payload, credentials: "same-origin" });
    }
  }
  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    /* empty body */
  }
  if (!res.ok) {
    const message = (data as { message?: string } | null)?.message ?? `Request failed (${res.status}).`;
    if (res.status === 401 && !url.startsWith("/api/login")) window.dispatchEvent(new Event("solobiz:signed-out"));
    throw new ApiError(message, res.status, data);
  }
  return data as T;
}

/** True when a failure means "could not reach the server" rather than "the server said no". */
export const isNetworkError = (e: unknown) => !(e instanceof ApiError);

export const api = {
  get: <T>(url: string) => request<T>("GET", url),
  /** A write that can be replayed safely: the server ignores a repeated op id. */
  send: <T>(method: "POST" | "PUT" | "DELETE", url: string, body: unknown, opId: string) => request<T>(method, url, body, opId),
  post: <T>(url: string, body?: unknown) => request<T>("POST", url, body),
  put: <T>(url: string, body?: unknown) => request<T>("PUT", url, body),
  del: <T>(url: string) => request<T>("DELETE", url),
};

export interface Ok {
  status: "ok" | "success";
  message?: string;
  redirect?: string;
}

export const auth = {
  login: (email: string, password: string) => api.post<Ok>("/api/login", { email, password }),
  logout: async () => {
    const r = await api.post<Ok>("/api/logout");
    // Forget this account's offline copy on this device.
    navigator.serviceWorker?.controller?.postMessage({ type: "CLEAR_PRIVATE_OFFLINE_DATA" });
    return r;
  },
  registerRequest: (b: {
    email: string; first_name: string; last_name: string;
    password: string; confirm_password: string; privacy_accepted: boolean;
  }) => api.post<Ok>("/api/register/request", b),
  registerVerify: (email: string, code: string) => api.post<Ok>("/api/register/verify", { email, code }),
  registerResend: (email: string) => api.post<Ok>("/api/register/resend", { email }),
  forgotRequest: (email: string) => api.post<Ok>("/api/forgot-password/request", { email }),
  forgotResend: (email: string) => api.post<Ok>("/api/forgot-password/resend", { email }),
  forgotReset: (email: string, code: string, password: string) =>
    api.post<Ok>("/api/forgot-password/reset", { email, code, password }),
};
