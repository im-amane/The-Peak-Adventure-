import { defineRailway, github, project, service, volume } from "railway/iac";

/**
 * Railway project definition for the single-process prototype.
 *
 * This file is applied explicitly with `railway config plan` and
 * `railway config apply`. It is not executed during Docker builds.
 */
export default defineRailway(() => {
  const data = volume("peak-adventure-data", {
    region: "asia-southeast1-eqsg3a",
    sizeMB: 1024,
  });

  const bot = service("peak-adventure", {
    source: github("im-amane/The-Peak-Adventure-", { branch: "main" }),
    // Telegram long polling and SQLite currently require exactly one replica.
    replicas: { "asia-southeast1-eqsg3a": 1 },
    healthcheck: "/healthz",
    healthcheckTimeout: 300,
    volumeMounts: {
      "/data": data,
    },
    env: {
      WEBAPP_URL: "https://peak-adventure-edge.thepeakadventure.workers.dev",
      DATABASE_PATH: "/data/peak_adventure.db",
      BACKUP_DIR: "/data/backups",
      BACKUP_INTERVAL_SECONDS: "21600",
      BACKUP_RETENTION: "7",
      POSTGRES_BACKUP_DIR: "/data/postgres_backups",
      POSTGRES_BACKUP_RETENTION: "7",
      WEB_HOST: "0.0.0.0",
      ENABLE_TELEGRAM_STARS: "false",
      LOG_LEVEL: "INFO",
    },
  });

  return project("the-peak-adventure", {
    resources: [bot, data],
  });
});
