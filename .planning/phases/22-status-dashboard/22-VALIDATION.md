---
phase: 22
slug: status-dashboard
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-02-28
---

# Phase 22 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | vitest (frontend) |
| **Config file** | frontend/vitest.config.js |
| **Quick run command** | `cd frontend && npx acorn --ecma2022 --module src/components/StatusDashboard.jsx > /dev/null 2>&1 && echo "PARSE OK"` |
| **Full suite command** | `cd frontend && npm run build` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run quick parse check
- **After every plan wave:** Run `cd frontend && npm run build`
- **Before `/gsd:verify-work`:** Full build must succeed
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| TBD | 01 | 1 | DASH-01 | parse | `acorn --ecma2022 --module StatusDashboard.jsx` | ❌ W0 | ⬜ pending |
| TBD | 01 | 1 | DASH-02 | parse | `acorn --ecma2022 --module StatusDashboard.jsx` | ❌ W0 | ⬜ pending |
| TBD | 01 | 1 | DASH-03 | parse | `acorn --ecma2022 --module StatusDashboard.jsx` | ❌ W0 | ⬜ pending |
| TBD | 02 | 2 | DASH-04 | parse | `acorn --ecma2022 --module GlobalNav.jsx` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*No Wave 0 required — frontend components verified via parse check and build.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Color-coded service cards render correctly | DASH-01 | Visual verification | Load /status, verify green/amber/red cards |
| Relative age indicator updates | DASH-02 | Timing-dependent rendering | Watch dashboard for 30s, verify age updates |
| WebSocket reconnect state display | DASH-03 | Requires live WebSocket context | Disconnect WS, verify attempts/error shown |
| Nav status dot color matches overall health | DASH-04 | Visual verification | Check nav dot matches dashboard overall status |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
