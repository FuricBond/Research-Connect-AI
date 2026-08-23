const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`);

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}
