---
type: guide
title: "Xcleaners Business Model — Investor Brief"
project: xcleaners
tags:
  - project/xcleaners
  - business-model
  - investor
  - revenue
---

# Xcleaners Business Model

**Prepared by:** @mifune (Business Strategist)
**Date:** 2026-03-26
**Version:** 1.0
**Status:** Investor-Ready Draft
**Confidential:** LPJ Services LLC

---

## 1. Executive Summary

**Xcleaners** is a vertical SaaS platform purpose-built for residential cleaning businesses in the United States. It is a Progressive Web App (PWA) that serves three distinct users from a single interface: business owners manage schedules and payments, cleaning teams see daily jobs and check in/out on-site, and homeowners reschedule and pay online. Unlike horizontal field-service tools adapted for cleaning, Xcleaners is built from the ground up for the recurring-schedule, multi-team, multi-frequency operations model that defines residential cleaning.

**The Problem (Quantified):**
- 1.25 million cleaning businesses in the US; 90% have fewer than 10 employees.
- ~75% still use spreadsheets, WhatsApp groups, or pen-and-paper to manage schedules.
- Owners spend 15+ hours per week on manual scheduling, payment chasing, and team coordination -- work that generates zero revenue.
- Persona research confirms: a 4-team, 120-client business loses ~$800/week to no-shows and carries ~$4,200 in untracked outstanding invoices at any given time.
- Existing software is either generic (Jobber: built for HVAC/plumbing, charges $29/user/month) or limited (ZenMaid: no auto-invoicing, breaks at 5+ teams).

**The Solution:**
Xcleaners replaces the scheduling spreadsheet, the WhatsApp group chat, and the Venmo payment chase with one app. AI-powered schedule optimization (Pro tier and above) reduces weekly planning from 3 hours to under 15 minutes. Flat monthly pricing -- no per-seat fees -- means a 15-cleaner operation pays the same $49/month as a 5-cleaner operation. Trilingual support (English, Spanish, Portuguese) addresses the reality that 49% of US residential cleaning workers speak Spanish at home.

---

## 2. Revenue Model

### 2.1 Subscription Tiers

| | **Basic** | **Pro** | **Business** |
|---|---|---|---|
| **Monthly Price** | $29/mo | $49/mo | $99/mo |
| **Annual Price** | $278/yr ($23.17/mo) | $470/yr ($39.17/mo) | $950/yr ($79.17/mo) |
| **Annual Discount** | 20% (2 months free) | 20% (2 months free) | 20% (2 months free) |
| **Scheduling** | Manual drag-and-drop | AI-assisted | Full AI auto-generation |
| **Clients** | Up to 50 | Up to 200 | Unlimited |
| **Teams** | 1 team (3 cleaners) | 3 teams (15 cleaners) | Unlimited (50 cleaners) |
| **Client Portal** | No | Yes | Yes |
| **Online Payments** | No | Auto-invoicing | Stripe payments + auto-charge |
| **Notifications** | Email + Push | Email + SMS + Push | All channels + WhatsApp |
| **Marketing Site** | No | No | Full website + AI chat + SEO |
| **Support** | Email (48h) | Email + Chat (24h) | Phone + Chat (4h) |

### 2.2 Revenue Characteristics

| Metric | Value |
|--------|-------|
| **Pricing model** | Flat monthly subscription (no per-seat) |
| **Expected ARPU** | $55/month (weighted across tiers) |
| **Annual discount** | 20% off monthly price |
| **Free trial** | 14 days, Pro features unlocked, no credit card required |
| **Payment processor** | Stripe (subscriptions + one-time setup fees) |
| **Billing cycles** | Monthly or Annual |

### 2.3 Revenue Streams

| Stream | Description | Status |
|--------|-------------|--------|
| **Core SaaS subscription** | Monthly/annual recurring revenue from 3 tiers | Live |
| **Affiliate program** | 30% recurring commission on referred subscribers | Live (crypto payout via USDT/BEP20) |
| **Setup fee (Business tier)** | $200 one-time for custom website build and onboarding | Live (Stripe price ID configured) |
| **Payment processing margin** | Future: small markup on Stripe transaction fees for Business tier | Planned (Phase 5+) |

---

## 3. Unit Economics

### 3.1 Customer Acquisition Cost (CAC)

| Channel | Estimated CAC | Notes |
|---------|--------------|-------|
| **Organic/SEO** | $15-30 | Content marketing targeting "cleaning business software" keywords |
| **Google Ads** | $80-150 | Cleaning SaaS is a niche vertical; CPC for "cleaning business scheduling software" ~$4-8 |
| **Referral/Affiliate** | $20-40 | 30% commission on first 12 months = $6.60-$11.88/mo per referral; effective CAC = first 2-4 months of commission |
| **Direct/Word of Mouth** | $0-10 | Cleaning industry is community-driven; WhatsApp groups, cleaning associations |
| **Blended CAC (target)** | **$60** | Weighted average across channels, improving as organic scales |

### 3.2 Lifetime Value (LTV)

| Variable | Value | Basis |
|----------|-------|-------|
| ARPU | $55/month | Weighted average: 40% Basic, 40% Pro, 20% Business |
| Gross margin | 82% | SaaS-typical; primary costs are hosting (Railway/Cloudflare), AI API calls, Twilio SMS |
| Avg. customer lifetime | 36 months | Industry benchmark for vertical SaaS with high switching costs; target <5% monthly churn |
| **LTV** | **$1,623** | $55 x 0.82 x 36 months |

### 3.3 Key Ratios

| Ratio | Value | Benchmark | Status |
|-------|-------|-----------|--------|
| **LTV:CAC** | **27:1** | >3:1 is healthy; >10:1 signals room to invest more in acquisition | Excellent |
| **Payback period** | **1.3 months** | $60 CAC / $45.10 gross margin per month | Excellent |
| **Gross margin** | **82%** | SaaS benchmark: 75-85% | On target |
| **Net revenue retention (target)** | **110%+** | Expansion from Basic to Pro to Business | Target |

### 3.4 Gross Margin Breakdown

| Cost Component | Monthly per Customer | % of ARPU |
|----------------|---------------------|-----------|
| Hosting (Railway + Cloudflare + Redis) | $3.50 | 6.4% |
| AI API costs (OpenAI/proxy for scheduling) | $2.00 | 3.6% |
| SMS/WhatsApp (Twilio + Evolution API) | $2.50 | 4.5% |
| Stripe processing fees (2.9% + $0.30) | $1.90 | 3.5% |
| **Total COGS** | **$9.90** | **18%** |
| **Gross profit per customer** | **$45.10** | **82%** |

---

## 4. Financial Projections (3 Years)

### 4.1 Year 1 — Product-Market Fit

| Quarter | Customers (EOQ) | New Adds | Churn (5%) | MRR (EOQ) | ARR Run Rate |
|---------|-----------------|----------|------------|-----------|-------------|
| Q1 | 10 | 10 | 0 | $550 | $6,600 |
| Q2 | 25 | 17 | 2 | $1,375 | $16,500 |
| Q3 | 40 | 19 | 4 | $2,200 | $26,400 |
| Q4 | 50 | 15 | 5 | $2,750 | $33,000 |

| Metric | Year 1 |
|--------|--------|
| **Ending MRR** | $2,750 |
| **Total Revenue** | ~$20,000 |
| **Customer count** | 50 |
| **Blended churn** | 5%/month (declining) |
| **Team size** | 1 founder + AI automation |

### 4.2 Year 2 — Growth

| Quarter | Customers (EOQ) | New Adds | Churn (4%) | MRR (EOQ) | ARR Run Rate |
|---------|-----------------|----------|------------|-----------|-------------|
| Q1 | 80 | 38 | 8 | $4,400 | $52,800 |
| Q2 | 120 | 50 | 10 | $6,600 | $79,200 |
| Q3 | 165 | 58 | 13 | $9,075 | $108,900 |
| Q4 | 200 | 50 | 15 | $11,000 | $132,000 |

| Metric | Year 2 |
|--------|--------|
| **Ending MRR** | $11,000 |
| **Total Revenue** | ~$95,000 |
| **Customer count** | 200 |
| **Blended churn** | 4%/month |
| **Net revenue retention** | 108% (upsell Basic to Pro) |
| **Team size** | 2-3 (founder + support + marketing) |

### 4.3 Year 3 — Scale

| Quarter | Customers (EOQ) | New Adds | Churn (3%) | MRR (EOQ) | ARR Run Rate |
|---------|-----------------|----------|------------|-----------|-------------|
| Q1 | 265 | 80 | 15 | $14,575 | $174,900 |
| Q2 | 345 | 100 | 20 | $18,975 | $227,700 |
| Q3 | 430 | 110 | 25 | $23,650 | $283,800 |
| Q4 | 500 | 100 | 30 | $27,500 | $330,000 |

| Metric | Year 3 |
|--------|--------|
| **Ending MRR** | $27,500 |
| **Total Revenue** | ~$250,000 |
| **Customer count** | 500 |
| **Blended churn** | 3%/month |
| **Net revenue retention** | 115% (tier upgrades + setup fees) |
| **Team size** | 5-7 |

### 4.4 Key Assumptions

1. **ARPU stays at $55/month** -- conservative; actual ARPU likely increases as more customers upgrade to Pro/Business.
2. **Monthly churn decreases over time** (5% to 4% to 3%) as product matures and switching costs increase.
3. **No external funding required** for Year 1-2; platform is already built and running on Railway/Cloudflare at minimal cost.
4. **Customer acquisition is primarily organic** (SEO, content, referrals) in Year 1, shifting to paid channels in Year 2-3.
5. **No enterprise tier** included in projections; potential upside from cleaning franchises not modeled.
6. **Single-market focus** (US only); international expansion is additive upside.

---

## 5. Pricing Strategy

### 5.1 Why Flat Pricing Wins

The residential cleaning industry has a structural characteristic that makes per-seat pricing toxic: **high employee count relative to revenue.** A typical 5-team operation has 15-20 cleaners generating $200K-400K in annual revenue. Per-seat pricing punishes growth.

| Scenario | Xcleaners (Pro) | Jobber (Team) | ZenMaid | Housecall Pro |
|----------|----------------|---------------|---------|---------------|
| 5 cleaners | $49/mo | $39 + $145 = **$184/mo** | $19 + $45 = **$64/mo** | $109/mo |
| 10 cleaners | $49/mo | $39 + $290 = **$329/mo** | $19 + $90 = **$109/mo** | $109 + add-ons |
| 15 cleaners | $49/mo | $39 + $435 = **$474/mo** | $19 + $135 = **$154/mo** | $199/mo |
| 20 cleaners | $99/mo (Business) | $39 + $580 = **$619/mo** | Not supported | $199+ |

**Key insight:** At 15 cleaners, Jobber costs 9.7x more than Xcleaners for the same scheduling capability. This is our primary sales lever.

### 5.2 Natural Upsell Path

```
Basic ($29) ──── at ~80 clients ────> Pro ($49) ──── at ~200 clients ────> Business ($99)
     |                                     |                                      |
  "I need AI                         "I need online                      "I need a website,
   scheduling"                        payments and                        lead capture, and
                                      client portal"                      WhatsApp"
```

**Upsell triggers:**
- **Basic to Pro:** Owner hits 50-client limit or spends >2 hours/week scheduling manually. AI scheduling becomes the unlock.
- **Pro to Business:** Owner wants online payments via Stripe, a professional website, or WhatsApp notifications. These are the growth features.

### 5.3 Expansion Revenue Opportunities

| Opportunity | Revenue Impact | Timeline |
|-------------|---------------|----------|
| **Tier upgrades** (Basic to Pro to Business) | +$20-50/customer/month | Ongoing |
| **Annual prepay conversion** | Improves cash flow; 20% of customers expected to prepay | Year 1+ |
| **Setup fee (Business)** | $200 one-time per Business customer | Live |
| **SMS overage charges** | $0.02/SMS beyond plan limits | Year 2 |
| **Premium integrations** (QuickBooks, Gusto payroll) | $10-20/mo add-on | Year 2-3 |
| **White-label / franchise licensing** | $500+/month per franchise brand | Year 3+ |

### 5.4 Affiliate Program

| Parameter | Value |
|-----------|-------|
| Commission rate | 30% of net subscription revenue |
| Commission type | Recurring (paid monthly as long as referral is active) |
| Cookie duration | 30 days |
| Minimum payout | $10/month |
| Auto-payout threshold | $25 |
| Payout method | USDT (BEP20) -- crypto-native, no banking friction |
| Expected affiliate CAC | $16.50/month (30% of $55 ARPU) |

**Why 30% recurring:** Cleaning business owners are deeply networked through local associations, Facebook groups, and WhatsApp communities. A generous recurring commission turns every customer into a long-term distribution channel. At 36-month average retention, a single referral generates $594 in commission -- enough to motivate active promotion.

---

## 6. Key Metrics

### 6.1 Current State (March 2026)

| Metric | Current | Notes |
|--------|---------|-------|
| **Product status** | Production-ready | 102 API endpoints, 20 screens, 39 DB tables (16 platform + 23 cleaning-domain) |
| **MVP completeness** | 100% | All 4 launch phases complete |
| **First client** | Clean New Orleans | Active beta user |
| **Demo mode** | Live | Full demo with sample data at xcleaners.app |
| **Tech stack** | Python 3.12 + FastAPI + PostgreSQL + Redis | Deployed on Railway |
| **Frontend** | PWA (HTML/CSS/JS) | Works on any device, no app store required |
| **Languages** | English, Spanish, Portuguese | Full i18n support |

### 6.2 Target Metrics

| Metric | 90-Day | Year 1 | Year 3 |
|--------|--------|--------|--------|
| **MRR** | $1,000 | $2,750 | $27,500 |
| **ARR** | $12,000 | $33,000 | $330,000 |
| **Active customers** | 10 | 50 | 500 |
| **Monthly churn** | <5% | <5% | <3% |
| **NPS** | >50 | >55 | >60 |
| **Activation rate** (signup to first schedule) | 60% | 70% | 80% |
| **Time to value** | <5 min | <5 min | <3 min |
| **Trial-to-paid conversion** | 20% | 25% | 35% |
| **Net revenue retention** | 100% | 105% | 115% |
| **LTV:CAC** | 15:1 | 20:1 | 27:1 |

---

## 7. Competitive Pricing Advantage

### 7.1 Feature + Price Comparison

| Feature | **Xcleaners** | **Jobber** | **ZenMaid** | **Housecall Pro** | **Launch27** |
|---------|:---:|:---:|:---:|:---:|:---:|
| **Starting price** | $29/mo | $39/mo | $19/mo + $9/user | $59/mo | $75/mo |
| **Per-user fee** | None | $29/user/mo | $9/user/mo | Varies | None |
| **AI scheduling** | Pro ($49) | Not available | Not available | Not available | Not available |
| **Cleaning-specific** | Yes | No (generic field service) | Yes | No (generic) | Partial (booking only) |
| **Client self-service** | Pro ($49) | $39+ | Limited | $59+ | $75+ |
| **Online payments** | Business ($99) | $39+ (Stripe) | Manual only | $59+ | $75+ |
| **Multi-language** | EN/ES/PT | EN only | EN only | EN only | EN only |
| **PWA (no download)** | Yes | No (native app) | No (web only, no PWA) | No (native app) | No (web only) |
| **AI chat receptionist** | Business ($99) | $99/mo add-on | Not available | Not available | Not available |
| **Marketing site** | Business ($99) | $79/mo add-on | Not available | Not available | Not available |
| **WhatsApp notifications** | Business ($99) | Not available | Not available | Not available | Not available |

### 7.2 Total Monthly Cost: 5-Team, 120-Client Business

This is the most common profile in our target market. Here is what each platform actually costs to run this operation.

| Platform | Base Plan | User Fees (15 cleaners) | Required Add-ons | **Total Monthly Cost** |
|----------|-----------|------------------------|-------------------|----------------------|
| **Xcleaners (Pro)** | $49 | $0 | None | **$49/mo** |
| **Xcleaners (Business)** | $99 | $0 | None (website + AI chat included) | **$99/mo** |
| **Jobber (Grow)** | $119 | $435 (15 x $29) | AI Receptionist $99 + Marketing $79 | **$732/mo** |
| **ZenMaid** | $19 | $135 (15 x $9) | No AI, no payments, no marketing | **$154/mo** |
| **Housecall Pro (Essentials)** | $109 | Included (limited) | Online booking $30, reviews $20 | **$159/mo** |
| **Launch27 (Pro)** | $149 | $0 | Limited features at this tier | **$149/mo** |

### 7.3 Annual Cost Comparison (Same 5-Team Business)

| Platform | Annual Cost | **Savings vs Xcleaners Pro** |
|----------|------------|------------------------------|
| **Xcleaners Pro (annual)** | **$470/yr** | -- |
| **Xcleaners Business (annual)** | **$950/yr** | -- |
| ZenMaid | $1,848/yr | Xcleaners saves **$1,378/yr** (75% less) |
| Launch27 Pro | $1,788/yr | Xcleaners saves **$1,318/yr** (74% less) |
| Housecall Pro | $1,908/yr | Xcleaners saves **$1,438/yr** (75% less) |
| Jobber Grow + add-ons | $8,784/yr | Xcleaners saves **$8,314/yr** (95% less) |

**Bottom line:** A cleaning business owner switching from Jobber to Xcleaners Pro saves $8,314 per year -- nearly $700 per month -- while gaining AI scheduling and multilingual support that Jobber does not offer at any price.

---

## 8. Market Opportunity Summary

| Metric | Value |
|--------|-------|
| US residential cleaning market | $12.5 billion (2025) |
| Cleaning businesses in the US | ~1.25 million |
| Businesses with <10 employees | ~90% of total |
| Currently using dedicated software | ~20-25% |
| Total Addressable Market (TAM) | ~1.25M businesses |
| Serviceable Addressable Market (SAM) | ~200K-350K (residential, 1-10 teams, tech-reachable) |
| Serviceable Obtainable Market (SOM) | ~15K-30K (PWA-adoptable, EN/ES, initially Southeast US) |
| Cleaning services software market | $652M-$1.98B (2025) |
| Software market CAGR | 6.6%-10.1% |

**Why Xcleaners wins in this market:**

1. **Price disruption.** Flat pricing at $29-99/mo vs. competitors at $154-732/mo for the same business size.
2. **Language access.** The only platform with full Spanish and Portuguese support -- serving 49% of the cleaning workforce that competitors ignore.
3. **Purpose-built.** Not a field-service tool adapted for cleaning. Built specifically for recurring residential schedules, multi-team operations, and house-level preferences.
4. **AI as a feature, not an add-on.** AI scheduling is included in the Pro tier at $49/mo. Jobber charges $99/mo extra just for an AI receptionist.
5. **Zero friction distribution.** PWA installs from a link -- no app store, no download, no storage complaints. Cleaners add it to their home screen in 10 seconds.

---

*This document is confidential and intended for investor evaluation purposes only.*
*LPJ Services LLC -- 2026. All rights reserved.*

---
*Version 1.0 | Last Updated: 2026-03-26 | Confidential*
