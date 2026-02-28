---
phase: 21
slug: websocket-recovery-listen-key-hardening
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-02-28
---

# Phase 21 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x + vitest (frontend) |
| **Config file** | backend/tests/conftest.py, frontend/vitest.config.js |
| **Quick run command** | `cd backend && python -m pytest tests/test_websocket_recovery.py -x -q` |
| **Full suite command** | `cd backend && python -m pytest tests/ -x -q` |
| **Estimated runtime** | ~20 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && python -m pytest tests/test_websocket_recovery.py -x -q`
- **After every plan wave:** Run `cd backend && python -m pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 20 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| TBD | 01 | 1 | WSRC-01 | unit | `pytest tests/test_websocket_recovery.py` | ❌ W0 | ⬜ pending |
| TBD | 01 | 1 | WSRC-02 | unit | `pytest tests/test_websocket_recovery.py` | ❌ W0 | ⬜ pending |
| TBD | 01 | 1 | WSRC-03 | unit | `pytest tests/test_websocket_recovery.py` | ❌ W0 | ⬜ pending |
| TBD | 02 | 2 | WSRC-04 | manual | frontend WebSocketContext check | ❌ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_websocket_recovery.py` — stubs for WSRC-01 through WSRC-03
- [ ] Mock fixtures for BinanceStreamManager and ReconciliationService

*Existing pytest infrastructure covers framework needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Frontend reconnect state display | WSRC-04 | React component rendering | Check WebSocketContext exposes reconnecting, attempts, error fields |
| Post-reconnect fill recovery | WSRC-01 | Requires live WebSocket disconnect | Kill backend WS, restart, verify fills recovered |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 20s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
