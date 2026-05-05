---
name: Feature Request
about: Request a new feature or worker
labels: enhancement
---

**Worker**: [e.g. signal, proxy, or new worker]

**Feature description**:

**Use case**:

**Proposed harness config** (if new worker):
```yaml
name: my_worker
allowed_agents:
  - hermes
allowed_actions:
  - act
quality:
  require_non_empty: []
  forbid_terms: []
```
