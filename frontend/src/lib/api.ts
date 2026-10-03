import type { User } from "./types";

const SESSION_KEY = "collections-copilot.session";

export interface Session {
  token: string;
  user: User;
}

export function readSession(): Session | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Session;
    return parsed?.token && parsed?.user?.role ? parsed : null;
  } catch {
    return null;
  }
}

export function writeSession(session: Session) {
  window.sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

export function clearSession() {
  window.sessionStorage.removeItem(SESSION_KEY);
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** FastAPI returns `detail` as a string or as a list of validation errors. */
function readableDetail(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const parts = detail.map((item) => {
      if (item && typeof item === "object" && "msg" in item) {
        const loc = Array.isArray((item as { loc?: unknown[] }).loc)
          ? (item as { loc: unknown[] }).loc.filter((p) => p !== "body").join(" → ")
          : "";
        return loc ? `${loc}: ${(item as { msg: string }).msg}` : (item as { msg: string }).msg;
      }
      return typeof item === "string" ? item : JSON.stringify(item);
    });
    return parts.join("; ");
  }
  if (detail && typeof detail === "object") return JSON.stringify(detail);
  return null;
}

const STATUS_TEXT: Record<number, string> = {
  401: "Your session has ended. Please sign in again.",
  403: "Your role does not have access to this.",
  404: "Not found.",
  502: "The backend is not reachable. Is the API running on 127.0.0.1:8000?",
  503: "The backend is not ready yet.",
  504: "The backend took too long to respond.",
};

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const session = readSession();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");
  if (session) headers.set("Authorization", `Bearer ${session.token}`);

  let response: Response;
  try {
    response = await fetch(`/api${path}`, { ...init, headers, cache: "no-store" });
  } catch {
    throw new ApiError("Could not reach the local server. Check that the frontend and backend are running.", 0);
  }

  const text = await response.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = null;
    }
  }

  if (!response.ok) {
    const detail = body && typeof body === "object" ? readableDetail((body as { detail?: unknown }).detail) : null;
    if (response.status === 401 && session && typeof window !== "undefined") {
      clearSession();
      window.dispatchEvent(new Event("session-expired"));
    }
    throw new ApiError(detail ?? STATUS_TEXT[response.status] ?? `Request failed (HTTP ${response.status}).`, response.status);
  }
  if (body === null) throw new ApiError("The backend returned an empty or non-JSON response.", response.status);
  return body as T;
}

export function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}
