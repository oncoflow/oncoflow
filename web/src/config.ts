import type { ClinicalDomain, Language, ThemeMode } from "./domain/types.js";
import {
  EnvConfigSchema,
  resolveClinicalDomain,
  resolveLanguage,
  resolveThemeMode,
} from "./infrastructure/validation/schemas.js";

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
  const parsed = EnvConfigSchema.parse(env);

  const defaultDomain = resolveClinicalDomain(parsed.APP_DOMAIN, "oncology");
  const allowedRaw = (parsed.APP_ALLOWED_DOMAINS || "oncology,sma")
    .split(",")
    .map((d) => d.trim().toLowerCase())
    .filter((d): d is ClinicalDomain => d === "oncology" || d === "sma");

  const devMode = parsed.APP_DEV_MODE !== "false" && parsed.NODE_ENV !== "production";
  const authMode: AuthMode =
    (parsed.APP_AUTH_MODE || "local").toLowerCase() === "oauth_proxy" ? "oauth_proxy" : "local";

  const adminUsers = (parsed.APP_ADMIN_USERS || "")
    .split(",")
    .map((u) => u.trim().toLowerCase())
    .filter(Boolean);

  // Fake fallback is disabled by default so the Web UI is 100% connected to the real FastAPI backend.
  // It is only enabled when explicitly requested via WEB_FAKE_API_FALLBACK=true or APP_USE_FAKE_ONLY=true (e.g. automated tests).
  const useFakeApiFallback =
    parsed.WEB_FAKE_API_FALLBACK === "true" || parsed.APP_USE_FAKE_ONLY === "true";

  const rawPort = Number(parsed.PORT_WEB ?? parsed.PORT ?? 3000);
  const port = Number.isNaN(rawPort) ? 3000 : rawPort;

  return {
    port,
    host: parsed.HOST_WEB || "127.0.0.1",
    apiUrl: (parsed.APP_API_URL || parsed.APP_QUEUE_API_URL || "http://127.0.0.1:8000").replace(
      /\/$/,
      "",
    ),
    apiToken: parsed.APP_API_TOKEN || "",
    proxySecret: parsed.APP_PROXY_SECRET || "",
    authMode,
    devMode,
    adminUsers,
    defaultDomain,
    allowedDomains: allowedRaw.length > 0 ? allowedRaw : ["oncology", "sma"],
    defaultLanguage: resolveLanguage(parsed.APP_LANGUAGE, "fr"),
    defaultTheme: resolveThemeMode(parsed.APP_THEME, "auto"),
    useFakeApiFallback,
  };
}
