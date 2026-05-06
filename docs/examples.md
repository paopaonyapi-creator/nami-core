# Nami Core API Examples

## Base URL

```
https://nami.178.104.181.132.nip.io
```

## Health Check

```bash
curl https://nami.178.104.181.132.nip.io/health
```

```typescript
import { NamiClient } from "./lib/sdk";
const client = new NamiClient();
const health = await client.health();
```

## List Workers

```bash
curl https://nami.178.104.181.132.nip.io/workers
```

## Single Dispatch (requires API key)

```bash
curl -X POST https://nami.178.104.181.132.nip.io/dispatch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{"worker":"lottery","action":"predict","payload":{}}'
```

```typescript
const client = new NamiClient("https://nami.178.104.181.132.nip.io", "YOUR_API_KEY");
const result = await client.dispatch("lottery", "predict");
```

## Batch Dispatch (requires API key)

```bash
curl -X POST https://nami.178.104.181.132.nip.io/dispatch/batch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{"items":[
    {"worker":"status","action":"health","payload":{}},
    {"worker":"gold","action":"prices","payload":{}}
  ]}'
```

```typescript
const result = await client.batchDispatch([
  { worker: "status", action: "health" },
  { worker: "gold", action: "prices" },
]);
```

## Worker Health Check

```bash
curl https://nami.178.104.181.132.nip.io/workers/proxy/health
```

```typescript
const health = await client.workerHealth("proxy");
```

## Webhook with Signature Verification

```bash
# Send a webhook
curl -X POST https://nami.178.104.181.132.nip.io/webhook \
  -H "Content-Type: application/json" \
  -d '{"source":"github","event":"push","data":{"repo":"nami-core"}}'

# Verify signature
curl https://nami.178.104.181.132.nip.io/webhook/verify
```

Verify on receiver side:

```python
import hmac, hashlib
signature = hmac.new(
    WEBHOOK_SECRET.encode(),
    request_body.encode(),
    hashlib.sha256
).hexdigest()
assert f"sha256={signature}" == received_signature
```

## SSE Streaming

```bash
curl -N https://nami.178.104.181.132.nip.io/events
```

```typescript
const es = client.events();
es.addEventListener("dispatch", (e) => {
  console.log("Dispatch:", JSON.parse(e.data));
});
es.addEventListener("ping", () => console.log("Heartbeat"));
```

## WebSocket

```javascript
const ws = new WebSocket("wss://nami.178.104.181.132.nip.io/ws");
ws.onmessage = (e) => console.log(JSON.parse(e.data));
```

## Metrics

```bash
curl https://nami.178.104.181.132.nip.io/metrics
curl https://nami.178.104.181.132.nip.io/metrics/prometheus
```

## Rate Limit Status (requires API key)

```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \
  https://nami.178.104.181.132.nip.io/workers/lottery/rate-limit
```
