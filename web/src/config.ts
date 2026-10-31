import type { ClinicalDomain, Language, ThemeMode } from "./domain/types.js";

export type AuthMode = "local" | "oauth_proxy";

export interface WebAppConfig {
  port: number;
  host: string;
  apiUrl: string;
  apiToken: string;
  proxySecret: string;
  authMode: AuthMode;
  devMode: boolean;
  adminUsers: string[];
  defaultDomain: ClinicalDomain;
  allowedDomains: ClinicalDomain[];
  defaultLanguage: Language;
  defaultTheme: ThemeMode;
  useFakeApiFallback: boolean;
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): WebAppConfig {
  const rawDomain = (env.APP_DOMAIN || "oncology").toLowerCase();
  const defaultDomain: ClinicalDomain = rawDomain === "sma" ? "sma" : "oncology";
  const allowedRaw = (env.APP_ALLOWED_DOMAINS || "oncology,sma")
    .split(",")
    .map((d) => d.trim().toLowerCase())
    .filter((d): d is ClinicalDomain => d === "oncology" || d === "sma");

  const devMode = env.APP_DEV_MODE !== "false" && env.NODE_ENV !== "production";
  const authMode: AuthMode =
    (env.APP_AUTH_MODE || "local").toLowerCase() === "oauth_proxy" ? "oauth_proxy" : "local";

  const adminUsers = (env.APP_ADMIN_USERS || "")
    .split(",")
    .map((u) => u.trim().toLowerCase())
    .filter(Boolean);

  // Fake fallback is disabled by default so the Web UI is 100% connected to the real FastAPI backend.
  // It is only enabled when explicitly requested via WEB_FAKE_API_FALLBACK=true or APP_USE_FAKE_ONLY=true (e.g. automated tests).
  const useFakeApiFallback =
    env.WEB_FAKE_API_FALLBACK === "true" || env.APP_USE_FAKE_ONLY === "true";

  return {
    port: Number(env.PORT_WEB || env.PORT || 3000),
    host: env.HOST_WEB || "127.0.0.1",
    apiUrl: (env.APP_API_URL || env.APP_QUEUE_API_URL || "http://127.0.0.1:8000").replace(
      /\/$/,
      "",
    ),
    apiToken: env.APP_API_TOKEN || "",
    proxySecret: env.APP_PROXY_SECRET || "",
    authMode,
    devMode,
    adminUsers,
    defaultDomain,
    allowedDomains: allowedRaw.length > 0 ? allowedRaw : ["oncology", "sma"],
    defaultLanguage: env.APP_LANGUAGE === "en" || env.APP_LANGUAGE === "english" ? "en" : "fr",
    defaultTheme: env.APP_THEME === "dark" ? "dark" : "light",
    useFakeApiFallback,
  };
}
