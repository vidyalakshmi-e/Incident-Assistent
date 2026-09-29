// Thin client for the FastAPI backend, reached through the same-origin /api proxy (next.config.ts).

export const API_BASE = "/api";

export class APIError extends Error {
  status: number;
  constructor(message: string, status = 0) {
    super(message);
    this.status = status;
  }
}

async function parse(res: Response): Promise<unknown> {
  const type = res.headers.get("content-type") ?? "";
  const body = type.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) {
    const detail =
      typeof body === "object" && body && "detail" in body ? (body as { detail: unknown }).detail : body;
    if (res.status === 500 || res.status === 502 || res.status === 504) {
      throw new APIError(
        "The API did not answer. Start it with: uvicorn backend.main:app --port 8000",
        res.status,
      );
    }
    throw new APIError(typeof detail === "string" ? detail : JSON.stringify(detail), res.status);
  }
  return body;
}

export async function getJSON<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { headers: { accept: "application/json" } });
  } catch {
    throw new APIError("The API is unreachable. Start it with: uvicorn backend.main:app --port 8000");
  }
  return (await parse(res)) as T;
}

export async function postJSON<T>(path: string, payload: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "content-type": "application/json", accept: "application/json" },
      body: JSON.stringify(payload ?? {}),
    });
  } catch {
    throw new APIError("The API is unreachable. Start it with: uvicorn backend.main:app --port 8000");
  }
  return (await parse(res)) as T;
}

export const fetcher = <T,>(path: string) => getJSON<T>(path);
