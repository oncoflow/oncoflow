import { loadConfig } from "./config.js";
import { HttpOncoflowApiAdapter } from "./infrastructure/api/http-oncoflow-api.adapter.js";
import { InMemoryOncoflowApiFake } from "./infrastructure/api/in-memory-oncoflow-api.fake.js";
import { buildServer } from "./ui/server.js";

async function main() {
  const config = loadConfig(process.env);

  if (!config.devMode) {
    if (!config.apiToken) {
      throw new Error(
        "APP_API_TOKEN is mandatory when running outside development mode (APP_DEV_MODE=false).",
      );
    }
    if (config.authMode === "oauth_proxy" && !config.proxySecret) {
      throw new Error("APP_PROXY_SECRET is mandatory when APP_AUTH_MODE=oauth_proxy.");
    }
  }

  const fakeFallback = config.useFakeApiFallback ? new InMemoryOncoflowApiFake() : undefined;
  const api =
    process.env.APP_USE_FAKE_ONLY === "true" && fakeFallback
      ? fakeFallback
      : new HttpOncoflowApiAdapter({
          baseUrl: config.apiUrl,
          apiToken: config.apiToken,
          proxySecret: config.proxySecret,
          fallbackPort: fakeFallback,
        });

  const app = await buildServer({ config, api });
  await app.listen({ port: config.port, host: config.host });
  process.stdout.write(
    `[DataSyntis Web M3] Server listening on http://${config.host}:${config.port} (API: ${config.apiUrl})\n`,
  );
}

main().catch((err) => {
  process.stderr.write(`Fatal startup error: ${String(err)}\n`);
  process.exit(1);
});
