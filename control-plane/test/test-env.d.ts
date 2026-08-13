import type { D1Migration } from "@cloudflare/vitest-pool-workers";

declare global {
  namespace Cloudflare {
    interface Env {
      TEST_MIGRATIONS: D1Migration[];
      STRIPE_WEBHOOK_SECRET: string;
      STRIPE_API_KEY: string;
      STRIPE_PORTAL_URL: string;
      APP_BASE_URL: string;
    }
  }
}

export {};
