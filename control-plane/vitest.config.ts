import { defineWorkersConfig, readD1Migrations } from "@cloudflare/vitest-pool-workers";

export default defineWorkersConfig(async () => {
  const migrations = await readD1Migrations("./migrations");
  return {
    test: {
      setupFiles: ["./test/apply-migrations.ts"],
      poolOptions: {
        workers: {
          wrangler: { configPath: "./wrangler.jsonc" },
          miniflare: {
            bindings: {
              TEST_MIGRATIONS: migrations,
              STRIPE_WEBHOOK_SECRET: "whsec_test_agentpulse",
              STRIPE_API_KEY: "sk_test_agentpulse",
            },
          },
        },
      },
    },
  };
});
