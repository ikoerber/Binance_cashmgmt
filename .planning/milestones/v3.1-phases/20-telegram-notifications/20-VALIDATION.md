---
phase: 20
slug: telegram-notifications
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-02-28
---

# Phase 20 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | backend/tests/conftest.py |
| **Quick run command** | `cd backend && python -m pytest tests/test_telegram_notifier.py -x -q` |
| **Full suite command** | `cd backend && python -m pytest tests/ -x -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && python -m pytest tests/test_telegram_notifier.py -x -q`
- **After every plan wave:** Run `cd backend && python -m pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| TBD | 01 | 1 | TELE-01 | unit | `pytest tests/test_telegram_notifier.py` | ❌ W0 | ⬜ pending |
| TBD | 01 | 1 | TELE-02 | unit | `pytest tests/test_telegram_notifier.py` | ❌ W0 | ⬜ pending |
| TBD | 01 | 1 | TELE-03 | unit | `pytest tests/test_telegram_notifier.py` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_telegram_notifier.py` — stubs for TELE-01 through TELE-03
- [ ] Mock fixtures for telegram Bot and health check service

*Existing pytest infrastructure covers framework needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Telegram message arrives on actual service failure | TELE-01 | Requires real Telegram bot token | Configure test bot, kill a service, verify message in chat |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
