import axios from "axios";

// All calls go to /api/v1; Vite proxies /api to the FastAPI backend.
const api = axios.create({ baseURL: "/api/v1", timeout: 20000 });

const TOKEN_KEY = "onboardiq_token";

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: user just needs to log in again */
  }
}

api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Normalise every failure into the backend's §10.2 shape: { status, code, message, fields }
api.interceptors.response.use(
  (res) => res,
  (err) => {
    const status = err.response?.status ?? 0;
    const body = err.response?.data?.error;
    if (status === 401 && !err.config?.url?.includes("/auth/login")) {
      setToken(null);
      window.dispatchEvent(new Event("onboardiq:logout"));
    }
    return Promise.reject({
      status,
      code: body?.code ?? (status ? "ERROR" : "NETWORK_ERROR"),
      message: body?.message ?? (status ? "Something went wrong" : "Cannot reach the server"),
      fields: body?.fields ?? [],
    });
  }
);

/** Download a protected file (e.g. audit CSV) with the JWT attached. */
export async function downloadFile(url, filename) {
  const res = await api.get(url, { responseType: "blob" });
  const href = URL.createObjectURL(res.data);
  const a = document.createElement("a");
  a.href = href;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(href);
}

export default api;
