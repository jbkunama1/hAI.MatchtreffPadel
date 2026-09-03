---
goal: Implementation Plan for Matchtreff Padel Features
version: 1.0
date_created: 2026-08-29
status: 'Planned'
tags: [feature, admin, dl]
---

# Introduction

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

This plan outlines the implementation of requested features for the Matchtreff Padel application, including admin tools, DL management, and frontend enhancements.

## 1. Requirements & Constraints

- Admin-facing WhatsApp message template editor
- Messaging system for user-to-admin communication
- TPCG Info group QR/Link popup on startpage
- AI-based help chat integration
- Admin bio fields on "About" page
- Media file management system (upload, edit, preview)
- Admin-controlled file visibility
- Americana advertisement toggle

## 2. Implementation Steps

### Phase 1: Admin & User Infrastructure
| Task | Description | Completed |
| --- | --- | --- |
| TASK-001 | WhatsApp text template edit/copy interface | |
| TASK-002 | Internal "Message to Admin" messaging system | |
| TASK-003 | Admin bio management on "About" page | |

### Phase 2: Startpage & Intelligence
| Task | Description | Completed |
| --- | --- | --- |
| TASK-004 | TPCG Info group QR/Link popup | |
| TASK-005 | AI-driven help chat widget integration | |

### Phase 3: DL Management & Ad Control
| Task | Description | Completed |
| --- | --- | --- |
| TASK-006 | Media upload, edit, and preview system | |
| TASK-007 | Admin/User file visibility controls | |
| TASK-008 | Americana ad display toggle in admin settings | |

## 3. Alternatives

- **ALT-001**: AI Help Chat: Use external service (e.g., Landbot, Intercom) vs local LLM endpoint wrapper.

## 4. Dependencies
- Admin session authentication
- Existing database schema for file records

## 5. Files
- `templates/admin_dashboard.html`, `templates/admin_settings.html`
- `logic_settings.py`, `logic_db.py`

## 6. Testing
- Unit tests for file upload/edit logic
- Manual testing of admin dashboard interfaces

## 7. Risks & Assumptions
- Assuming current Python/Flask architecture can support async AI chat integration.
