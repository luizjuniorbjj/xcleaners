# Xcleaners

**Your cleaning business, finally organized.**

---

## What is Xcleaners?

Xcleaners is a vertical SaaS platform purpose-built for residential cleaning businesses. It replaces the patchwork of spreadsheets, group chats, and manual invoicing that most cleaning companies rely on with a single AI-powered platform. Three dedicated portals serve business owners, cleaning teams, and homeowners -- with full bilingual support in English, Spanish, and Portuguese.

## The Problem

- **Scheduling chaos.** Most cleaning businesses still manage bookings through texts, calls, and sticky notes. Double-bookings, missed appointments, and last-minute cancellations cost real revenue every week.
- **Payment chasing.** Owners spend hours following up on unpaid invoices instead of growing their business. Late payments are the norm, not the exception.
- **Team coordination breakdown.** Cleaning teams operate in the field with no central system. Job details get lost, quality is inconsistent, and there is no visibility into who is where or what has been completed.

## The Solution

- **One platform, three portals.** Owner dashboard for business operations, cleaner app for field teams, and homeowner portal for bookings and communication.
- **AI-powered scheduling.** Intelligent job assignment that considers team availability, location, and skill match. Recurring schedules that actually work.
- **Automated payments and invoicing.** Stripe-integrated billing with automatic invoice generation, payment tracking, and subscription management.
- **Bilingual by default.** Full EN/ES/PT support across every screen, notification, and document -- because that is who works in this industry.
- **Real-time notifications.** WhatsApp, SMS, push, and email keep everyone informed without anyone having to make a phone call.

## Platform at a Glance

| Metric | Value |
|--------|-------|
| API Endpoints | 102 |
| Database Tables | 39 |
| Frontend Modules | 28 |
| Automated Tests | 26 |
| Languages | EN, ES, PT |
| User Portals | 3 (Owner, Cleaner, Homeowner) |
| AI Integration | Claude (Anthropic) |
| Notification Channels | 4 (WhatsApp, SMS, Push, Email) |

## Key Features

### For Business Owners
- Full business dashboard with revenue, jobs, and team metrics at a glance
- Client management with service history, preferences, and notes
- Team management with role-based permissions and performance tracking
- Automated invoicing and payment collection via Stripe
- Multi-location support with territory mapping
- AI assistant for business insights and decision support

### For Cleaning Teams
- Mobile-first PWA with today's schedule, job details, and navigation
- Clock in/out with GPS verification
- Job checklists and photo documentation
- Real-time updates when schedules change
- Bilingual interface that switches instantly

### For Homeowners
- Online booking with transparent pricing
- Real-time job status and cleaner arrival tracking
- Service history and upcoming appointments
- Direct communication channel with the business
- Easy rebooking and subscription management

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.12 + FastAPI |
| Frontend | HTML/CSS/JS (Progressive Web App) |
| Database | PostgreSQL 16 |
| Cache | Redis 7 |
| AI | Claude (Anthropic) |
| Payments | Stripe (subscriptions + one-time) |
| Notifications | WhatsApp, SMS, Push, Email |
| Auth | JWT + Google OAuth |
| Hosting | Railway (Docker) |

## Pricing

| Plan | Price/mo | Highlights |
|------|----------|------------|
| **Basic** | $29 | 1 team, scheduling, invoicing, homeowner portal |
| **Pro** | $49 | Unlimited teams, AI assistant, WhatsApp notifications, analytics |
| **Business** | $99 | Multi-location, API access, priority support, custom branding |

## Investor Documentation

Detailed materials are available in [`docs/investor/`](docs/investor/):

| Document | Description |
|----------|-------------|
| [Executive Summary](docs/investor/EXECUTIVE-SUMMARY.md) | Company overview, traction, and ask |
| [One-Pager](docs/investor/ONE-PAGER.md) | Single-page snapshot for quick review |
| [Business Model](docs/investor/BUSINESS-MODEL.md) | Revenue model, unit economics, projections |
| [Investment Thesis](docs/investor/INVESTMENT-THESIS.md) | Why Xcleaners, why now |
| [Market Analysis](docs/investor/MARKET-ANALYSIS.md) | TAM/SAM/SOM, competitive landscape |
| [Brand Package](docs/investor/BRAND-PACKAGE.md) | Brand identity, positioning, visual system |
| [Technical Overview](docs/investor/TECHNICAL-OVERVIEW.md) | Architecture and platform capabilities |
| [Technical Due Diligence](docs/investor/TECHNICAL-DUE-DILIGENCE.md) | Code quality, security, scalability |
| [Product Walkthrough](docs/investor/PRODUCT-WALKTHROUGH.md) | Feature-by-feature guided tour |

## Quick Start (Development)

```bash
# 1. Clone and configure
cp .env.example .env   # Fill in your values

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the application
python xcleaners_main.py

# 4. Open in browser
open http://localhost:8003/cleaning/app
```

### Dev Setup (with test dependencies)

```bash
pip install -r requirements-dev.txt
```

## Demo Mode

Xcleaners includes a fully functional demo mode. Use these accounts to explore each portal:

| Email | Password | Role |
|-------|----------|------|
| superadmin@xcleaners.app | admin123 | Super Admin |
| admin@xcleaners.app | admin123 | Owner |
| cleaner@xcleaners.app | admin123 | Cleaner |
| donocasa@xcleaners.app | admin123 | Homeowner |

## License

Proprietary -- All rights reserved.

Copyright 2026 LPJ Services LLC.

## Contact

**LPJ Services LLC**
Automations, AI & Web3

[xcleaners.app](https://xcleaners.app)

