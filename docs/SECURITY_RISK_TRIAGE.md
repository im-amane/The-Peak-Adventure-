# Security risk triage

The security event stream records invalid gameplay, economy, payment and repeated rate-limit activity. This layer classifies aggregate event telemetry for administrators; it does not automatically ban, mute, restrict, or otherwise punish players.

## Risk thresholds

| Risk | Trigger | Suggested action |
|---|---|---|
| Low | Below the medium/high thresholds | Log only |
| Medium | Maximum severity ≥ 3, economy abuse events ≥ 2, rate-limit events ≥ 3, or risk score ≥ 8 | Monitor |
| High | Maximum severity = 5, economy abuse events ≥ 4, or risk score ≥ 15 | Manual review |

The risk score is the sum of event severities inside the selected time window. The admin security view now displays the risk level and suggested action alongside the underlying counts so an operator can inspect why a player was surfaced.

## Safety and limitations

- Thresholds are triage signals, not proof of cheating.
- No automated enforcement is performed; moderation remains an explicit administrator action.
- Invalid-action telemetry does not measure every successful coin transfer or market transaction.
- Thresholds should be tuned against production telemetry and false-positive reviews before any automated action is considered.
- Security event details remain bounded and retained under the existing event-retention policy.
