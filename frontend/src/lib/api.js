import axios from "axios";

const getBackendUrl = () => {
  let envUrl = process.env.REACT_APP_BACKEND_URL;
  if (envUrl) {
    envUrl = envUrl.trim().replace(/\/$/, "");
    if (!envUrl.startsWith("http://") && !envUrl.startsWith("https://")) {
      envUrl = `https://${envUrl}`;
    }
    return envUrl;
  }

  // Auto-detect local vs production environment
  if (typeof window !== "undefined") {
    const hostname = window.location.hostname;
    if (hostname === "localhost" || hostname === "127.0.0.1") {
      return "http://localhost:8000";
    }
  }

  return "https://face-engine-backend.onrender.com";
};

export const BACKEND_URL = getBackendUrl();
export const API = `${BACKEND_URL}/api`;
export const UPLOADS_BASE = BACKEND_URL;

export const api = axios.create({
  baseURL: API,
  withCredentials: true,
});

// Attach token from localStorage as Bearer fallback (cross-site cookies may drop)
api.interceptors.request.use((cfg) => {
  const t = localStorage.getItem("access_token");
  if (t) cfg.headers = { ...(cfg.headers || {}), Authorization: `Bearer ${t}` };
  return cfg;
});

export function apiError(e) {
  const d = e?.response?.data?.detail;
  if (!d) return e?.message || "Something went wrong.";
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x.msg || JSON.stringify(x)).join(" ");
  return String(d);
}
