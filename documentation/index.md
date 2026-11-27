# AgentWatch

Monitors AI-agent activity on Linux hosts, detects defined suspicious behavior, and exports activity and detections to Splunk for SOC investigation.

- [Architecture](architecture.md): components and data flow
- [AWS account](infrastructure/aws.md): access, restrictions, budget, and open decisions
- [Local Claude Code demo](infrastructure/claude-code-demo.md)
- [Local Splunk](infrastructure/splunk.md): run Splunk Enterprise with Docker Compose and test HEC
- [v1 telemetry contract](telemetry-v1.md): schema, identity, redaction, and fixtures
- [Forwarder](forwarder.md): map Tetragon records to v1 events and send them to ingestion
- [API (Swagger)](http://52.60.176.146/docs): live REST API
- [Repository](https://github.com/AgentWatchOrg/AgentWatch) · [Board](https://github.com/orgs/AgentWatchOrg/projects/1)
