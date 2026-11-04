# Production HTTP monitoring and alerts

The runtime monitor keeps aggregate-only HTTP telemetry and evaluates a rolling five-minute sample. It does not store user IDs, request paths, headers, tokens or request bodies in the rolling sample. The sample is capped at 5,000 records to bound memory use.

## Alert thresholds

| Alert | Threshold | Recovery |
|---|---|---|
| Elevated server errors | At least 20 recent requests and HTTP 5xx rate ≥ 20% | Rate falls below threshold or traffic drops below the minimum |
| Slow responses | At least 20 recent requests and p95 latency ≥ 2,000 ms | p95 falls below threshold or traffic drops below the minimum |
| Database unavailable | Existing failed database health probe | Successful database probe |
| Backup unhealthy | Existing backup failure or stale-backup threshold | Successful fresh backup |

Alerts are sent to configured Telegram administrators on state transitions, including recovery notifications. The admin-only /ops/metrics endpoint now exposes the recent request count, server-error rate, p95 latency and active alert states.

## Operational limitations

- HTTP rolling samples are in process memory and reset when the application restarts.
- The five-minute sample is bounded to the most recent 5,000 requests; under extreme traffic this may represent less than five minutes.
- Thresholds are initial safeguards and should be tuned with production traffic and incident reviews.
- This does not provide an external metrics backend, durable time series, distributed tracing or independent uptime monitoring.
