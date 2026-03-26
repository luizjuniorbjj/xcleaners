# Xcleaners -- Technical Overview

**Prepared for:** Investors and Technical Due Diligence Reviewers
**Date:** March 2026
**Version:** 1.0.0

---

## Executive Summary

Xcleaners is a production-ready SaaS platform that gives residential cleaning businesses a complete digital operations suite: scheduling, team management, client CRM, invoicing, notifications, and AI-powered optimization. It is delivered as a Progressive Web App (PWA) that works on any device, installs like a native app, and functions offline.

The platform serves three distinct user portals through a single codebase, supports three languages natively, and integrates AI scheduling intelligence that goes beyond simple chatbot prompting -- it uses a tool-use architecture where the AI can query real business data to make actionable recommendations.

---

## 1. Architecture Summary

### High-Level System Diagram

```
                       +-----------------------------+
                       |       CLIENTS (Browser)     |
                       |  PWA / Mobile / Desktop     |
                       +-------------+---------------+
                                     |
                                     | HTTPS
                                     v
                       +-----------------------------+
                       |     SECURITY MIDDLEWARE      |
                       |  Headers | Rate Limit | WAF  |
                       +-------------+---------------+
                                     |
                       +-----------------------------+
                       |       FastAPI (Python)       |
                       |    102 API Endpoints         |
                       |    18 Route Modules          |
                       +---+--------+--------+-------+
                           |        |        |
                  +--------+  +-----+-----+  +--------+
                  |           |           |            |
            +-----v---+ +----v----+ +----v----+ +-----v------+
            |PostgreSQL| |  Redis  | |   AI    | | Ext. APIs  |
            | 39 Tables| | Cache   | | Claude/ | | Stripe     |
            | 95 Index | | Sessions| | OpenAI  | | Twilio     |
            +----------+ +---------+ +---------+ | WhatsApp   |
                                                  | Resend     |
                                                  +------------+
```

### Architecture Pattern: Modular Monolith

Xcleaners follows a **modular monolith** architecture -- a single deployable unit where internal code is organized into clearly separated modules with explicit boundaries.

**Why this is right for the current stage:**

- **Speed of iteration.** A single deployment pipeline means features ship in hours, not days. At the early-growth stage, velocity is the competitive advantage.
- **Operational simplicity.** One service to monitor, one database to back up, one deployment to manage. This keeps infrastructure costs under $50/month.
- **Clear extraction path.** Each module (scheduling, invoicing, notifications, AI) has its own service layer and route prefix. When scale demands it, any module can be extracted into a standalone microservice with minimal refactoring.
- **Proven pattern.** Companies like Shopify, Basecamp, and Linear all scaled past $100M ARR on modular monoliths before selectively extracting services.

### Module Boundaries

| Module | Routes | Services | Responsibility |
|--------|--------|----------|---------------|
| **Scheduling** | `schedule.py` | `schedule_service`, `recurrence_engine`, `daily_generator`, `frequency_matcher` | Booking lifecycle, recurring schedules, daily generation |
| **Teams** | `teams.py`, `members.py` | `team_service`, `team_assignment_scorer`, `cleaner_service` | Team CRUD, member management, AI-scored assignment |
| **Clients** | `clients.py` | `client_service`, `homeowner_service` | Client CRM, homeowner self-service portal |
| **Invoicing** | `invoice_routes.py` | `invoice_service`, `payment_link_service` | Invoice generation, Stripe payment links |
| **Notifications** | `notification_routes.py`, `push_routes.py` | `notification_service`, `sms_service`, `email_service` | Omnichannel delivery (WhatsApp, Push, SMS, Email) |
| **AI** | `ai_routes.py` | `ai_scheduling`, `ai_tools` | Schedule optimization, duration prediction, pattern detection |
| **Dashboard** | `dashboard_routes.py` | `dashboard_service`, `daily_generator` | Real-time analytics, daily summaries |
| **Auth** | `auth_routes.py` | Role guard, Business context | JWT + Google OAuth, RBAC, multi-business isolation |
| **Settings** | `settings_routes.py` | `settings_service` | Business configuration, branding, service areas |
| **Onboarding** | `onboarding.py` | `onboarding_service`, `setup_validator`, `template_copy_service` | Guided setup wizard with pre-built templates |

---

## 2. Technology Stack

| Layer | Technology | Why We Chose It |
|-------|-----------|-----------------|
| **Backend** | Python 3.12 + FastAPI | Fastest Python web framework (async-native). Type hints enable auto-generated API docs and input validation. Large talent pool. |
| **Frontend** | Vanilla HTML/CSS/JS (PWA) | Zero build step, instant load times, no framework churn. Service Worker enables offline capability. Installs as native app on iOS/Android. |
| **Database** | PostgreSQL 16 | Industry standard for transactional SaaS. JSONB for flexible config. UUID primary keys for distributed-ready IDs. 39 tables, 95 indexes. |
| **Cache** | Redis 7 | Session management, rate limiting, real-time pub/sub. Graceful fallback to in-memory when unavailable. |
| **AI** | Claude (Anthropic) + OpenAI (fallback) | Tool-use architecture for data-aware scheduling AI. Provider abstraction layer allows swapping without code changes. |
| **Payments** | Stripe | PCI-compliant payment processing. Payment links for invoicing. Subscription management for platform billing. |
| **Notifications** | Twilio (SMS) + WhatsApp API + Web Push + Resend (Email) | Omnichannel with smart routing: free channels first (WhatsApp, Push), paid channels (SMS) as fallback. |
| **Auth** | JWT + Google OAuth 2.0 + bcrypt | Industry-standard token auth. Social login reduces onboarding friction. bcrypt for password hashing. |
| **Hosting** | Railway (Docker) | One-command deploys via GitHub Actions. Auto-scaling. Health checks. Under $20/month at current scale. |
| **Voice** | Edge TTS | Text-to-speech for accessibility features. Free, high-quality, multiple languages. |
| **Monitoring** | Google Analytics + Search Console | User behavior tracking and SEO performance monitoring built-in. |
| **Data Validation** | Pydantic v2 | Runtime type validation on all API inputs. Auto-generates OpenAPI schema. Catches bugs before they reach the database. |

---

## 3. Product Capabilities (Quantified)

### Platform Scale

| Metric | Count | Details |
|--------|-------|---------|
| **API Endpoints** | 102 | Full REST API across 18 route modules |
| **Database Tables** | 39 | 16 platform + 23 cleaning-domain tables |
| **Database Indexes** | 95 | Optimized for read-heavy dashboard and scheduling queries |
| **Database Migrations** | 10 | Versioned, additive-only, safe for live systems |
| **Backend Services** | 26 | Dedicated business logic layer per domain |
| **Frontend Modules** | 28 | JS modules across 4 portals + shared utilities |
| **Languages Supported** | 3 | English, Spanish, Portuguese (full i18n) |
| **Test Suite** | 26 | Automated tests covering health, routes, security, config, models |

### Three-Portal Architecture

Each user role gets a purpose-built experience:

| Portal | Target User | Key Screens | JS Modules |
|--------|------------|-------------|------------|
| **Owner Portal** | Business owner / manager | Dashboard, Schedule Builder, Client Manager, Team Manager, Invoices, Reports, AI Assistant, Settings, CRM, Chat Monitor | 14 modules |
| **Team Portal** | Cleaners / field workers | Today's Jobs, My Schedule, Earnings, Job Detail, Profile | 5 modules |
| **Homeowner Portal** | End customers | My Bookings, Booking Detail, My Invoices, Preferences | 4 modules |
| **Super Admin** | Platform operator | Cross-business management, system health | 1 module |

### AI Features

| Feature | What It Does | How It Works |
|---------|-------------|-------------|
| **Schedule Optimization** | Analyzes daily schedule and suggests improvements | AI queries real booking data via 6 tools, minimizes travel, balances workload |
| **Team Assignment** | Recommends best team for each job | 5-factor weighted scoring: area match (35%), workload (25%), preference (20%), proximity (10%), continuity (10%) |
| **Duration Prediction** | Predicts cleaning time for each job | Historical analysis of client-specific data, adjusted for service complexity |
| **Pattern Detection** | Identifies cancellation trends, peak days, underutilized teams | Analyzes 30+ days of data, flags actionable patterns |

### Notification Channels

| Channel | Cost | Use Case | Priority |
|---------|------|----------|----------|
| **WhatsApp** | Free (via Evolution API) | Booking confirmations, reminders, updates | 1st (default) |
| **Web Push** | Free | Real-time alerts for logged-in users | 2nd |
| **SMS** (Twilio) | Paid | Critical notifications (24h reminders), fallback | 3rd (fallback) |
| **Email** (Resend) | Free tier | Invoices, receipts, marketing | Parallel |

Smart routing logic: the system tries free channels first and only falls back to paid SMS when necessary. Critical notifications (e.g., 24-hour reminders) go directly via SMS to guarantee delivery.

---

## 4. Security Posture

### Authentication

| Mechanism | Implementation | Coverage |
|-----------|---------------|----------|
| **JWT Tokens** | PyJWT with configurable expiration | All API endpoints |
| **Google OAuth 2.0** | Social login for frictionless onboarding | Login and registration |
| **bcrypt** | Password hashing with automatic salt | All stored passwords |
| **PIN Authentication** | bcrypt-hashed PINs for cleaner portal | Team member quick-login |

### Authorization (Role-Based Access Control)

Four distinct roles with enforced boundaries:

| Role | Access Level | Enforcement |
|------|-------------|-------------|
| **Owner** | Full business management, all data, settings, billing | Role guard middleware |
| **Team Lead** | Team schedule, member management, limited reports | Role guard middleware |
| **Cleaner** | Own schedule, job details, earnings, check-in/out | Role guard middleware |
| **Homeowner** | Own bookings, invoices, preferences only | Role guard middleware |

Role enforcement is implemented as FastAPI middleware dependencies -- every protected endpoint declares its required role, and the guard runs before any business logic executes.

### Data Isolation

- **Multi-tenant by design.** Every cleaning-domain table includes a `business_id` foreign key. All queries are scoped by business. One business owner cannot see another's data.
- **Business Context Middleware.** A dedicated middleware layer (`BusinessContextMiddleware`) extracts and validates the business context on every request, ensuring data isolation at the HTTP layer.
- **Platform user isolation.** Platform-level tables (users, subscriptions) use UUID primary keys and are never exposed across tenant boundaries.

### Encryption

| Data Type | Method | Details |
|-----------|--------|---------|
| Passwords | bcrypt | Industry-standard adaptive hashing |
| API keys | Fernet AES-128 | Symmetric encryption with per-user salt |
| Chat messages | Fernet AES-128 | Encrypted at rest in `messages.content_encrypted` |
| Affiliate payout details | Fernet AES-128 | Financial data encrypted before storage |

### Security Middleware Stack

Three layers of defense, applied to every request in order:

| Layer | Function | Details |
|-------|----------|---------|
| **Security Headers** | OWASP headers on every response | X-Content-Type-Options, X-Frame-Options, Strict-Transport-Security, CSP, Referrer-Policy |
| **Rate Limiting** | Redis-based sliding window | Prevents brute force and API abuse. Graceful degradation when Redis unavailable. |
| **Request Validation** | Body size limits, path traversal blocking, UA filtering | Blocks oversized payloads, directory traversal attempts, and known bot signatures |

### PCI Compliance

Payment processing is handled entirely by Stripe. No credit card numbers, CVVs, or bank account details ever touch Xcleaners servers. Stripe Payment Links are used for invoice collection, keeping the platform out of PCI scope.

---

## 5. Scalability Path

### Current Capacity

The platform currently supports multiple concurrent cleaning businesses, each with their own clients, teams, schedules, and invoices. The modular monolith handles this comfortably on a single Railway container.

**Current infrastructure cost: under $50/month** (Railway compute + PostgreSQL + Redis).

### Short-Term Scaling (10-100 businesses)

| Action | Effort | Impact |
|--------|--------|--------|
| Railway horizontal scaling | Configuration only | 2-4x capacity via multiple containers |
| PostgreSQL read replicas | Configuration only | Offload dashboard/reporting queries |
| Redis cluster mode | Configuration only | Distributed session and rate-limit state |
| CDN for static assets | 1 day | Reduce server load for PWA shell and assets |

### Medium-Term Scaling (100-1,000 businesses)

| Action | Effort | Impact |
|--------|--------|--------|
| Extract notification service | 1-2 weeks | Independent scaling of high-volume notification delivery |
| Extract AI scheduling service | 1-2 weeks | Isolate AI compute from core API latency |
| Connection pooling (PgBouncer) | 1 day | Handle 10x more concurrent database connections |
| Background job queue (Celery/ARQ) | 1 week | Async processing for invoices, reports, notifications |

### Database Readiness

- **95 indexes** across 39 tables, optimized for the most common query patterns (dashboard loads, schedule lookups, client searches).
- **UUID primary keys** on all tables -- ready for distributed ID generation if sharding is needed.
- **JSONB columns** for flexible configuration (business settings, instance config) without schema migrations.
- **Additive-only migrations** -- all 10 migrations use `IF NOT EXISTS` and `ADD COLUMN IF NOT EXISTS`, safe to run on live production databases.

---

## 6. Development Infrastructure

### CI/CD Pipeline (GitHub Actions)

Every push to `main` triggers an automated pipeline:

```
Push to main
    |
    v
[1] Run Test Suite (pytest, 26 tests)
    |
    v (only if tests pass)
[2] Deploy to Railway (Docker)
    |
    v
[3] Health Check (automatic, every 30s)
```

- **Zero-downtime deploys** via Railway's rolling deployment strategy.
- **Automatic rollback** if the health check fails after deployment.
- **Manual trigger** available via `workflow_dispatch` for on-demand deploys.

### Docker Configuration

Multi-stage build optimized for production:

| Stage | Purpose | Result |
|-------|---------|--------|
| **Builder** | Install dependencies, compile native extensions | Temporary -- discarded after build |
| **Runtime** | Lean image with only production code and runtime libs | Final image, ~150MB |

Security hardening in the Docker image:
- Non-root user (`appuser`) -- process cannot escalate privileges.
- No build tools in production -- reduced attack surface.
- Built-in health check -- container restarts automatically if the app becomes unresponsive.

### Test Suite

| Test File | Coverage Area | Tests |
|-----------|--------------|-------|
| `test_health.py` | API health endpoint, startup verification | 3 |
| `test_routes.py` | Route registration, endpoint accessibility | 5 |
| `test_security.py` | Auth enforcement, token validation, security headers | 3 |
| `test_config.py` | Environment configuration, defaults | 4 |
| `test_models.py` | Data models, validation, serialization | 5 |
| `test_rebrand.py` | Brand consistency across codebase | 6 |
| **Total** | | **26** |

---

## 7. AI Integration

### Architecture: Tool-Use (Not Simple Prompting)

Most SaaS products bolt on AI as a chatbot that generates generic text. Xcleaners takes a fundamentally different approach.

The AI scheduling assistant uses **tool-use** (also called "function calling") -- a pattern where the AI can call structured functions to query real business data before making recommendations.

```
User asks: "Optimize tomorrow's schedule"
    |
    v
AI receives 6 available tools:
    - get_schedule_for_date
    - get_team_availability
    - get_client_history
    - calculate_distance
    - get_team_workload_summary
    - get_cancellation_patterns
    |
    v
AI decides which tools to call (up to 8 iterations)
    |
    v
Each tool queries the actual PostgreSQL database
    |
    v
AI analyzes real data and returns actionable suggestions
    with concrete numbers (distances, times, percentages)
```

**Why this matters:** The AI does not hallucinate schedules. It works with the actual bookings, actual team availability, and actual client history. Every suggestion is grounded in real data.

### Provider Abstraction

The AI layer supports three providers through a unified interface:

| Provider | Role | Switching Cost |
|----------|------|---------------|
| **Anthropic (Claude)** | Primary provider | Default |
| **OpenAI** | Fallback provider | Configuration change only |
| **Proxy** | Custom endpoint (e.g., self-hosted models) | Configuration change only |

Tool definitions are maintained in Anthropic's format and automatically converted to OpenAI's function-calling format when needed. Changing providers requires only an environment variable change -- no code modification.

### Graceful Degradation

If the AI service is unavailable (API outage, rate limit, configuration missing):
- The scheduling system continues to function with manual scheduling.
- The team assignment scorer falls back to its deterministic 5-factor algorithm (no AI needed).
- Notifications, invoicing, and all other features are completely independent of AI.

The AI is an enhancement layer, not a dependency.

---

## 8. Intellectual Property

### Custom Scheduling Engine

The scheduling system includes proprietary algorithms built specifically for the residential cleaning industry:

- **Recurrence Engine** -- handles complex recurring schedule patterns (weekly, biweekly, monthly, custom) with automatic next-occurrence computation and conflict resolution.
- **Frequency Matcher** -- matches client schedule preferences against team availability across multiple frequency types.
- **Daily Generator** -- automatically generates daily booking instances from recurring schedules, handling exceptions and overrides.
- **Conflict Resolver** -- detects and suggests resolutions for double-bookings, capacity overflows, and team availability gaps.

### 5-Factor Team Assignment Scorer

A weighted scoring algorithm (documented in architecture v3, Section 7.3) that evaluates every team for every job:

| Factor | Weight | What It Measures |
|--------|--------|-----------------|
| Area Match | 35% | Does the team's service area include the client's zip code? |
| Workload Balance | 25% | How loaded is this team today vs. others? |
| Client Preference | 20% | Has the client requested this specific team? |
| Proximity | 10% | Haversine distance to the team's nearest assigned job |
| Continuity | 10% | Did this team serve the client last time? |

### Three-Portal PWA Architecture

A single HTML shell (`app.html`, 186 lines) serves all four user roles through client-side routing. The Service Worker implements five distinct caching strategies (Cache First, Network First, Stale While Revalidate, Network Only with offline queue, and CDN caching) for optimal performance across network conditions.

### Bilingual-Native Design System

The i18n system is not a bolt-on translation layer. It is a first-class architecture component:
- Three complete language files (English, Spanish, Portuguese).
- All UI strings, notifications, and AI responses are localized.
- The cleaning industry in the US has a predominantly bilingual workforce -- this is a market requirement, not a nice-to-have.

### Omnichannel Notification Orchestrator

Smart routing logic with cost optimization:
- Prioritizes free channels (WhatsApp, Web Push) over paid (SMS).
- Critical notifications bypass the priority queue and go directly via SMS.
- Template system with 6 pre-built notification types (booking confirmation, 24h reminder, invoice sent, schedule change, check-in alert, payment reminder).

---

## 9. Technical Debt (Honest Assessment)

### Known Issues

| Issue | Severity | Remediation Plan | Timeline |
|-------|----------|-----------------|----------|
| **Test coverage at 26 tests** | Medium | Add integration tests for scheduling engine, invoice flow, and notification delivery. Target: 80+ tests. | 2-4 weeks |
| **Duplicate `/admin/db-check` endpoint** | Low | Remove the duplicate route in `xcleaners_main.py` (lines 295-308). Cosmetic issue, no runtime impact. | 1 hour |
| **Inline DB migration endpoints** | Low | Move `db-fix-users` and `db-check` to a CLI script. Currently protected by secret key but should not be HTTP-accessible in production. | 1 day |
| **Schema inherits from parent platform** | Low | The base `schema.sql` includes tables from the parent ClaWtoBusiness platform (conversations, memories, affiliates). These are unused by Xcleaners but harmless. Clean separation planned for v2. | 2-3 days |
| **No API versioning** | Low | Current API is v1 implicitly. Add `/api/v1/` prefix before introducing breaking changes. | 1 day |

### Why Current Debt Is Manageable

1. **All debt is in non-critical paths.** The core scheduling engine, invoicing, and notification systems have no known issues. Technical debt lives in peripheral areas (test coverage, legacy routes, schema cleanup).

2. **Architecture supports incremental remediation.** The modular structure means each issue can be fixed independently without touching other modules. No "rewrite everything" risk.

3. **Production is stable.** The platform has been deployed and tested with real business data. The CI/CD pipeline, Docker health checks, and security middleware provide a safety net.

4. **Debt was strategic, not accidental.** The platform was extracted from a larger parent system (ClaWtoBusiness) to move faster. The inherited schema and shared auth layer allowed shipping in weeks instead of months. The extraction path is clear and the cost is known.

---

## Summary of Technical Moat

| Advantage | Detail |
|-----------|--------|
| **AI that uses real data** | Tool-use architecture, not generic chatbot. AI queries actual business data. |
| **Three portals, one codebase** | Owner, cleaner, and homeowner each get a purpose-built PWA experience. |
| **Works offline** | Service Worker with 5 caching strategies. Field workers can view schedules without internet. |
| **Bilingual-native** | EN/ES/PT from day one. Critical for the US cleaning industry workforce. |
| **Smart notifications** | Free channels first, paid as fallback. Cost-optimized by design. |
| **102 endpoints, shipping** | Not a prototype. Production-deployed with CI/CD, security middleware, and health monitoring. |
| **Under $50/month infra** | Efficient architecture keeps burn rate minimal during growth phase. |

---
*Version 1.0 | Last Updated: 2026-03-26 | Confidential*
