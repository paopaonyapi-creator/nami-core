# Nami Core v0.7.0 — ปัญหาและการแก้ไข

## วันที่: 2026-05-06

### สถานะสุดท้าย: v0.7.0 เสร็จสมบูรณ์ ✅

- **204 tests passed** (เพิ่มจาก 86)
- **22 workers** (เพิ่มจาก 19): +ai_chat, +sentiment, +search
- **React dashboard** build ผ่าน (Next.js 16.2.4 + Turbopack)
- **Production endpoints**: /cache, /cache/flush, /restart, /reload-workers

### ปัญหาหลัก: `import nami_workers.X as mod` คืนฟังก์ชันแทนโมดูล

**สาเหตุ:** `nami_workers/__init__.py` มี `from .pipeline_worker import pipeline_worker` ทำให้ `nami_workers.pipeline_worker` เป็นฟังก์ชัน ไม่ใช่โมดูล

**วิธีแก้:** ใช้ `importlib.import_module("nami_workers.pipeline_worker")` เพื่อเข้าถึงโมดูลจริง

### ปัญหาอื่นๆ ที่พบและแก้แล้ว

1. **Notification worker** — mock ผิด path: → `nami_workers.utils.telegram_send`
2. **Analytics worker** — action ชื่อ `dispatch_log` ไม่ใช่ `log`, `summary` ไม่ใช่ `stats`
3. **Scheduler worker** — `list` เรียก `_scheduler_ref.status()` ไม่ใช่ `.get_jobs()`
4. **Auth status code** — API คืน 401 ไม่ใช่ 403
5. **Async SDK tests** — ต้องใช้ `asyncio.run()` แทน `get_event_loop()`
6. **Relay trigger** — ต้องใช้ event ที่ไม่มี hook จึงจะได้ fired=0
7. **search_worker** — import analytics_worker ต้องใช้ importlib เหมือนกัน
8. **create_app()** — ต้องส่ง hermes+scheduler เข้าไป ไม่งั้นได้ app เปล่าๆ
9. **build_core()** — สร้างใหม่เพื่อแยก setup logic จาก run_server()

### ไฟล์ใหม่ที่สร้าง

- `src/nami_core/cache.py` — Redis cache + in-memory fallback
- `src/nami_workers/ai_chat_worker.py` — chat/complete/summarize/translate
- `src/nami_workers/sentiment_worker.py` — analyze/batch_analyze
- `src/nami_workers/search_worker.py` — web/knowledge search
- `config/ai_chat_harness.yaml`, `sentiment_harness.yaml`, `search_harness.yaml`
- `tests/test_new_workers.py` — notification, analytics, scheduler, cron, email, relay, pipeline
- `tests/test_sdk.py` — sync client, async client, WS listener
- `tests/test_integration.py` — full API round-trip
- `tests/test_ai_workers.py` — ai_chat, sentiment, search
- `tests/test_production.py` — cache module, production endpoints
- `nami-dashboard/` — Next.js React dashboard
