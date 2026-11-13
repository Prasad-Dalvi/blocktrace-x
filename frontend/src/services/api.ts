const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:5000/api";

export function getToken(): string | null {
  return localStorage.getItem("bt_token");
}

export async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.error ? JSON.stringify(data.error) : "API request failed");
  }
  return data as T;
}
