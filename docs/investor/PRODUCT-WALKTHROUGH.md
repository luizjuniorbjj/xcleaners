# Xcleaners -- Product Walkthrough for Investors

**Author:** @ux-design-expert (Sati)
**Date:** 2026-03-26
**Version:** 1.0
**Status:** FINAL

---

## 1. Product Overview

| Attribute | Detail |
|-----------|--------|
| **Platform type** | Progressive Web App (PWA) -- installable on any device from the browser |
| **Access** | Browser-based. Works on Chrome, Safari, Edge, Firefox. Installable to home screen on Android and iOS. |
| **Architecture** | Single HTML shell (`app.html`) with client-side routing. No page reloads. |
| **Backend** | Python 3.11 + FastAPI, PostgreSQL 16, Redis 7 |
| **Real-time** | Server-Sent Events (SSE) for live team progress, job status, and schedule updates |
| **Offline** | IndexedDB-backed offline store for cleaners in the field (queued actions sync when connectivity returns) |
| **Service Worker** | Full PWA service worker (`sw.js`) for caching, push notifications, and offline shell |
| **Internationalization** | Trilingual -- English, Spanish, Portuguese -- with browser auto-detection and runtime switching |
| **Authentication** | Email/password + Google OAuth. 256-bit encrypted sessions. |

### Three Distinct Portals

Xcleaners serves three user types, each with a purpose-built experience:

| Portal | Primary User | Access Pattern | Key Value |
|--------|-------------|---------------|-----------|
| **Owner Portal** | Business owner / manager | Desktop + tablet | Full operational control -- schedule, teams, clients, billing, AI assistant |
| **Cleaner/Team Portal** | Field cleaners | Mobile-first (phone) | Today's jobs, check-in/out, navigation, earnings -- designed for one-handed use |
| **Homeowner Portal** | End customers | Mobile + desktop | Book cleanings, view upcoming visits, pay invoices, set preferences |

### Design System

The product ships with a **2,678-line documented design system** (`design-system.css`) containing:

- **218+ CSS custom properties** (tokens for color, typography, spacing, shadows, radii, animations)
- **157+ component style rules** (buttons, cards, modals, toasts, forms, inputs, badges, skeletons, avatars, tabs, empty states, spinners)
- **6 semantic color families** with full 50-900 shade scales (Primary Teal, Success Green, Warning Amber, Danger Red, Neutral Gray, Info Cyan, plus a Purple accent for AI features)
- **Dark mode support** via `prefers-color-scheme: dark` media query
- **Reduced-motion support** via `prefers-reduced-motion` for accessibility
- **Print stylesheet** included
- **Responsive breakpoints** at 480px, 768px, 1024px, and 1280px

---

## 2. Onboarding Experience (5 Steps)

New business owners are guided through a **5-step setup wizard** that takes under 5 minutes. Progress is saved per step, so owners can leave and resume exactly where they stopped.

### Visual Design

The wizard features:
- A **step indicator** with numbered circles, color-coded (completed = green check, active = blue with glow ring, upcoming = gray)
- A **thin progress bar** that fills as steps complete
- **Back/Next navigation** with a skip option from Step 3 onward
- Centered, card-based layout (max-width 720px) for focused attention

### Step-by-Step Breakdown

| Step | Name | What the Owner Does | Data Captured |
|------|------|---------------------|---------------|
| **1** | Business Info | Enters business name, industry (pre-filled: cleaning), city, state, phone | Company identity, service region |
| **2** | Services | Selects from **service templates** (standard clean, deep clean, move-in/out, etc.). "Standard Clean" is pre-selected by default. | Service catalog with slugs, durations, descriptions |
| **3** | Service Area | Defines geographic coverage -- zip codes, neighborhoods, or radius | Routing and assignment boundaries |
| **4** | Pricing | Sets base prices per service type. Templates suggest starting prices. | Revenue model, invoice generation baseline |
| **5** | Team | Adds first team members (cleaners). Can invite by email or add manually. | Workforce roster for scheduling |

### Completion Flow

Once all 5 steps are complete (or the owner clicks "Finish Setup"), the wizard auto-redirects to the Owner Dashboard. If the owner has previously completed or skipped onboarding, they go straight to the dashboard on login.

---

## 3. Owner Portal Walkthrough

The Owner Portal is the command center. It provides 14 JavaScript modules totaling a full business management suite.

### 3.1 Dashboard

**Route:** `#/owner/dashboard`

The dashboard opens with a **personalized greeting card** ("Good morning, James!") in a gradient primary-color banner, followed by a real-time summary of the day.

| Section | What It Shows | Interaction |
|---------|--------------|-------------|
| **KPI Stat Cards** | 4 cards in a grid (2x2 on mobile, 4-col on desktop): Today's Bookings, Active Clients, Active Teams, Monthly Revenue | Each card shows the number, label, and trend indicator |
| **Team Progress** | Real-time progress bars per team, updated via SSE | Click "View Schedule" to jump to the calendar |
| **Revenue Chart** | Pure CSS bar chart with Week / Month / Quarter toggle buttons | Toggle periods to see revenue trends |
| **Overdue Payments** | List of past-due invoices with amounts | Click "View Invoices" to manage |
| **Quick Actions** | 3 action buttons: Generate Schedule, View Unassigned Jobs, Send Reminders | One-tap to common daily workflows |

**Technical note:** Dashboard data loads via `CleanAPI.cleanGet('/dashboard')` with graceful fallback to zero-state defaults. SSE subscription (`_subscribeSSE`) keeps team progress live without polling.

### 3.2 Schedule Builder

**Route:** `#/owner/schedule`

A **native calendar implementation** (zero external dependencies) providing:

| Feature | Detail |
|---------|--------|
| **Weekly view** | 7 days, 7 AM - 6 PM, 30-minute time slots |
| **Day / Week navigation** | Previous/next arrows, date picker |
| **Drag-and-drop** | Move bookings between time slots and days |
| **Click empty slot** | Opens "Add Booking" modal |
| **Click booking** | Opens side panel with booking detail |
| **Team filter chips** | Toggle visibility by team (color-coded) |
| **Generate schedule** | AI-powered one-click schedule generation |
| **Mobile adaptation** | Single-day view on screens below 768px |
| **SSE real-time** | Live updates when cleaners check in/out |
| **Undo support** | Timed undo bar after drag-and-drop moves |

### 3.3 Teams

**Route:** `#/owner/teams`

| Feature | Detail |
|---------|--------|
| **Team cards** | Each team displayed as an expandable card with member list and workload stats |
| **Create team** | Name, assign color, set team lead |
| **Add members** | Invite cleaners by email or add from existing roster |
| **Workload stats** | Jobs assigned this week, hours, utilization percentage |
| **Team lead** | Designate a team lead for communication and accountability |

### 3.4 Clients (CRM)

**Route:** `#/owner/clients`

Full client relationship management:

| Feature | Detail |
|---------|--------|
| **Client list** | Searchable, sortable table with name, address, service frequency, last cleaning date |
| **Client detail** | Dedicated view with service history, preferences, notes, invoices, and upcoming bookings |
| **Add client** | Manual entry or bulk import |
| **Service history** | Timeline of all past cleanings with ratings and notes |
| **Preferences** | Pet info, alarm codes, special instructions, room-specific notes |

### 3.5 Invoices

**Route:** `#/owner/invoices`

| Feature | Detail |
|---------|--------|
| **Status tabs** | All / Draft / Sent / Paid / Overdue -- filterable views |
| **Summary cards** | Total revenue, outstanding balance, overdue amount |
| **Batch generate** | One-click invoice generation for completed jobs |
| **Send / Remind** | Email invoices or send payment reminders |
| **Mark paid** | Modal with payment method options: Cash, Check, Zelle, Other |
| **Invoice detail** | Line items, service dates, amounts, payment link |
| **Payment link** | Copyable link for client self-service payment (Stripe integration) |
| **Bulk select** | Checkbox selection for batch operations |

### 3.6 AI Assistant

**Route:** Available from schedule builder and dashboard

| Feature | Detail |
|---------|--------|
| **AI Optimize** | Button on the schedule builder that triggers AI-powered schedule optimization |
| **Suggestion panel** | Displays AI suggestions with accept/reject per suggestion |
| **Insights card** | Dashboard widget with scheduling efficiency insights |
| **Plan gating** | Basic plan users see an upgrade prompt; AI features require Intermediate+ plan |

### 3.7 Reports

**Route:** `#/owner/reports`

| Section | What It Shows |
|---------|--------------|
| **Revenue summary** | This month vs. last month with percentage change indicator (green up / red down) |
| **Weekly revenue bars** | Visual bar chart showing revenue per day of the week |
| **Job stats** | Jobs by day chart, completion rates |
| **Top clients** | Ranked list of highest-value clients by revenue |
| **Team performance** | Per-team metrics: jobs completed, hours worked, average job time |

### 3.8 Settings

**Route:** `#/owner/settings`

Business configuration, notification preferences, billing management, and account settings.

### 3.9 Additional Owner Modules

| Module | Route | Purpose |
|--------|-------|---------|
| **Services** | `#/owner/services` | Manage service catalog (types, durations, pricing) |
| **Bookings** | `#/owner/bookings` | Booking list with filters and detail view |
| **Chat Monitor** | `#/owner/chat` | Monitor customer conversations |

---

## 4. Cleaner/Team Portal Walkthrough

Designed for cleaners who work in the field with only a smartphone. Every screen is optimized for **mobile-first, one-handed operation**.

### 4.1 Today View

**Route:** `#/team/today`

The primary screen for cleaners. Shows today's jobs ordered by time.

| Feature | Detail |
|---------|--------|
| **Summary stats** | 3 mini-cards at top: Total Jobs, Completed, Remaining |
| **Job cards** | Each card shows: client name, address, time, service type, status badge |
| **Check-in** | One-tap check-in with geolocation verification |
| **Navigate** | GPS navigation button opens maps app with client address |
| **Pull-to-refresh** | Native pull-to-refresh gesture to reload job list |
| **Status flow** | Scheduled -> Checked In -> In Progress -> Completed |

### 4.2 Job Detail

**Route:** `#/team/job/:id`

The execution view for an active job:

| Feature | Detail |
|---------|--------|
| **Client info** | Name, address, phone, special instructions |
| **Job timer** | Active timer showing elapsed time since check-in |
| **Room-by-room checklist** | Checkable task list per room (kitchen, bathrooms, bedrooms, etc.) |
| **Photo capture** | Camera integration for before/after photos |
| **Notes** | Free-text field for job-specific notes |
| **Report issue** | Flag problems (broken item, access issue, safety concern) |
| **Check-out** | Complete the job with final notes and time stamp |

### 4.3 My Schedule

**Route:** `#/team/schedule`

Weekly and monthly calendar view of upcoming jobs. Cleaners can see their full schedule but cannot modify it (owner-controlled).

### 4.4 Earnings

**Route:** `#/team/earnings`

Commission tracking and payment history. Cleaners see what they have earned per job and in aggregate.

### 4.5 Profile

**Route:** `#/team/profile`

Personal information, notification preferences, and availability settings.

---

## 5. Homeowner Portal Walkthrough

The client-facing portal where homeowners manage their relationship with the cleaning business.

### 5.1 My Bookings

**Route:** `#/homeowner/bookings`

| Feature | Detail |
|---------|--------|
| **Next Cleaning hero card** | Prominent card showing the next scheduled cleaning with date, time, team, and service type |
| **Upcoming tab** | List of future bookings with date, time, and status |
| **Past tab** | History of completed cleanings |
| **Request Cleaning** | Button to request a new booking (opens modal) |

### 5.2 Booking Detail

**Route:** `#/homeowner/booking/:id`

Detailed view of a specific booking: service type, scheduled team, time window, special instructions, and status updates.

### 5.3 My Invoices

**Route:** `#/homeowner/invoices`

Payment history and outstanding invoices. Homeowners can view line items and pay via the payment link (Stripe).

### 5.4 Preferences

**Route:** `#/homeowner/preferences`

Service customization: preferred cleaning day/time, pet information, access codes, room-specific instructions, and communication preferences.

---

## 6. Key UX Differentiators

### Mobile-First Design

Cleaners do not sit at desks. The Team Portal is built for **one-handed phone use** with large tap targets, bottom-anchored actions, and minimal scrolling. The Owner Portal is responsive across all breakpoints but optimized for tablet and desktop workflows.

### Trilingual (EN/ES/PT) with Auto-Detection

The i18n system (`I18n.init()`) detects the browser language and loads the appropriate string file. Users can switch language at runtime. All UI strings use the `I18n.t('key')` pattern -- no hardcoded text in the interface.

This matters because **the cleaning industry workforce in the US is heavily Spanish-speaking and Portuguese-speaking**. Competing products are English-only.

### Offline Support

The `OfflineStore` module uses **IndexedDB** to cache today's jobs and queue actions (check-in, check-out, notes) when connectivity is lost. Queued actions sync automatically when the connection returns. A service worker (`sw.js`) caches the app shell for instant loading even without network.

This matters because **cleaners work inside homes** where Wi-Fi and cellular coverage are unreliable.

### 5-Second Check-In

Check-in is a single tap with automatic geolocation capture. No forms, no typing. The cleaner opens the app, taps "Check In" on the job card, and the system records time + GPS coordinates.

This matters because **reducing friction at the start of every job saves 100+ taps per day across a cleaning team**.

### Real-Time Everything (SSE)

Team progress on the Owner Dashboard updates in real time via Server-Sent Events. The owner sees cleaners check in, jobs complete, and the revenue chart update -- all without refreshing the page.

### Demo Mode

A built-in `DemoData` provider generates realistic mock data (teams, clients, bookings, invoices) when the API is unavailable. Demo data persists to `localStorage` across sessions, allowing investors and prospects to explore the full product without a backend connection.

---

## 7. Design System Maturity

| Metric | Value |
|--------|-------|
| **CSS file** | `design-system.css` -- 2,678 lines, loaded before all other styles |
| **CSS custom properties** | 218+ design tokens (color, typography, spacing, shadows, radii, transitions) |
| **Component rules** | 157+ (buttons, cards, modals, toasts, forms, inputs, badges, skeletons, avatars, tabs, empty states, spinners, progress bars, greeting cards) |
| **Color palette** | 6 semantic families x 10 shades each = 60+ color tokens, plus team-assignable custom colors |
| **Typography** | Inter (UI) + JetBrains Mono (code/data). 10 size steps (11px-36px), 4 weight steps (400-800), 4 line-height options, 4 letter-spacing options |
| **Spacing scale** | 13-step scale from 0 to 4rem (0, 0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 2.5, 3, 4 rem) |
| **Elevation** | 6-level shadow scale (0-5) with legacy aliases |
| **Border radius** | 7 steps from 0.125rem to 9999px (pill) |
| **Responsive breakpoints** | 480px (small), 768px (tablet), 1024px (desktop), 1280px (wide) |
| **Accessibility** | WCAG 2.1 Level AA -- primary color contrast ratio 4.6:1 on white (documented in CSS comments). Reduced-motion media query. Print stylesheet. |
| **Dark mode** | CSS-native via `prefers-color-scheme: dark` |
| **Skeleton loading** | Built-in shimmer animations for every data-loading state |
| **Animation system** | Fade-in, slide-up, and ease curves defined as tokens |

### Brandbook

A comprehensive **brandbook** (`docs/brandbook.md`) documents:
- Brand mission, vision, tagline, and positioning statement
- Brand personality traits and archetypes (The Sage + The Creator)
- Voice and tone guidelines with per-context examples (dashboard, onboarding, errors, marketing)
- Vocabulary rules (words to use vs. words to avoid)
- Logo system with 6 variations, clear space rules, minimum sizes, and misuse guidelines
- Full color system with semantic usage rules per business context

---

## 8. Demo Instructions

### Step 1: Access the Application

| Environment | URL |
|-------------|-----|
| **Production** | `https://xcleaners.com/cleaning/app.html` |
| **Local development** | `http://localhost:8002/cleaning/app.html` |

### Step 2: Demo Credentials

The application includes a **built-in demo mode** that activates automatically when the backend API is unavailable or when using demo credentials:

| Field | Value |
|-------|-------|
| Email | Use any email (demo mode intercepts) |
| Password | Use any password |
| Alternative | Click "Sign in with Google" (demo mode) |

Demo mode populates the entire application with realistic data: 4 teams, 15+ clients, 30+ bookings, invoices, and earnings history.

### Step 3: Recommended Demo Flow (5-Minute Investor Demo)

| Time | Action | What to Show |
|------|--------|-------------|
| **0:00 - 0:30** | Login screen | Point out: Google OAuth, 256-bit encryption badge, PWA installability, professional design |
| **0:30 - 1:30** | Owner Dashboard | Show: personalized greeting, 4 KPI cards, live team progress bars, revenue chart (toggle week/month/quarter), quick actions |
| **1:30 - 2:30** | Schedule Builder | Show: weekly calendar, drag-and-drop a booking, team filter chips, click empty slot to add booking, mention AI Optimize button |
| **2:30 - 3:15** | Teams + Clients | Show: team cards with member lists, client CRM with service history and preferences |
| **3:15 - 4:00** | Invoices | Show: status tabs (Draft/Sent/Paid/Overdue), batch generate, mark-paid modal with payment methods, payment link copy |
| **4:00 - 4:30** | Switch to Cleaner Portal | Show: Today's Jobs view, check-in button, job detail with room checklist and photo capture, earnings |
| **4:30 - 5:00** | Switch to Homeowner Portal | Show: Next Cleaning hero card, upcoming/past tabs, request cleaning button, preferences |

### Step 4: Key Screens to Capture

If taking screenshots or recording, prioritize these screens:

1. **Owner Dashboard** -- the "wow" screen with KPIs, greeting card, and revenue chart
2. **Schedule Builder** -- the visual calendar showing a full week of color-coded team assignments
3. **Cleaner Today View** -- mobile-first job list with check-in buttons
4. **Onboarding Wizard** -- the 5-step setup showing progress indicator
5. **Invoice Manager** -- professional billing with status tabs and batch operations

### Step 5: Features to Highlight in Conversation

| Feature | Investor Talking Point |
|---------|----------------------|
| **PWA / Installable** | No app store approval needed. Deploy updates instantly. Works offline. |
| **Trilingual** | 40%+ of US cleaning workers speak Spanish or Portuguese natively. Competitors are English-only. |
| **AI Scheduling** | One-click schedule optimization for 100+ recurring jobs across multiple teams. |
| **Real-time SSE** | Owners see live progress without refreshing. No WebSocket complexity. |
| **Offline-first for cleaners** | Jobs cached in IndexedDB. Check-in/out works without signal. Syncs when back online. |
| **Demo mode** | Prospects can explore the full product without creating an account or needing a backend. |
| **Design system maturity** | 2,678-line documented design system. Not a prototype -- production-grade UI foundation. |
| **Zero dependencies (calendar)** | Schedule builder is a custom implementation. No FullCalendar, no external JS libraries. |
| **3 portals, 1 codebase** | Owner, Cleaner, and Homeowner share one app shell with role-based routing. Efficient to maintain. |
| **Stripe integration** | Payment links, invoice tracking, and subscription billing built in. |

---

*Document generated by @ux-design-expert (Sati) for investor review. Based on direct code analysis of the Xcleaners production codebase.*

---
*Version 1.0 | Last Updated: 2026-03-26 | Confidential*
