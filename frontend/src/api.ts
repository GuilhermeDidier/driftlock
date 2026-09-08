const base = import.meta.env.DEV ? "http://127.0.0.1:8000" : "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${base}/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    throw new Error(`${response.status} on ${path}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  state: () => request<import("./types").AppState>("/state/"),
  source: (key: string) => request<import("./types").Source>(`/sources/${key}/`),
  run: (id: number) => request<import("./types").Run>(`/runs/${id}/`),
  triggerRun: (key: string) =>
    request<import("./types").Run>(`/sources/${key}/run/`, {
      method: "POST", body: JSON.stringify({}),
    }),
  setLayout: (layout: string) =>
    request<{ layout: string }>("/demo/layout/", {
      method: "POST", body: JSON.stringify({ layout }),
    }),
};

export const storeUrl = `${base}/demo/store/`;
