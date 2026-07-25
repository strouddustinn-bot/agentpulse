import path from "node:path";
import { cloudflareTest, readD1Migrations } from "@cloudflare/vitest-pool-workers";
import { defineConfig } from "vitest/config";

export default defineConfig(async () => {
  const migrations = await readD1Migrations(path.join(import.meta.dirname, "migrations"));
  return {
    plugins: [
      cloudflareTest({
        wrangler: { configPath: "./wrangler.jsonc" },
        miniflare: {
          bindings: {
            TEST_MIGRATIONS: migrations,
            STRIPE_WEBHOOK_SECRET: "whsec_test_agentpulse",
            STRIPE_API_KEY: "sk_test_agentpulse",
            STRIPE_PRICE_STARTER: "price_test_starter",
            STRIPE_PRICE_PRO: "price_test_pro",
            STRIPE_PRICE_BUSINESS: "price_test_business",
            APP_BASE_URL: "https://app.agentpulse.test",
          },
        },
      }),
    ],
    test: { setupFiles: ["./test/apply-migrations.ts"] },
  };
});
