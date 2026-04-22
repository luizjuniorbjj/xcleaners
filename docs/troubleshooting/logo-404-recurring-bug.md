# Logo 404 Recurring Bug — Troubleshooting & Fix

> **Status:** RESOLVED 2026-04-22 via commit `1c92bc9`
> **History:** 3 previous incidents (2026-04-17, earlier) treated symptoms, not root cause.

## Symptom

Logo image (`/cleaning/static/img/logo.png`) returns 404 in production.
Broken image icon in app header. Console errors:

```
Failed to load resource: 404 — https://app.xcleaners.app/cleaning/static/img/logo.png
Failed to load resource: 404 — https://app.xcleaners.app/cleaning/static/icons/icon-192.png
```

Recurring — same bug reported and "fixed" multiple times, keeps returning.

## Root Cause (DEFINITIVE)

`.gitignore` contains global `*.png` and `*.jpg` patterns. The Railway deploy workflow (`.github/workflows/deploy.yml`) uses `railway up --service cleanclaw-api` to upload the build context from the GitHub Actions runner.

**`railway up` respects `.gitignore` by default** when creating the build context archive. Even though PNGs are tracked in git (via historical `git add --force`), they are **excluded from the upload** to Railway.

Chain of events:
1. GitHub Actions runner checks out code (PNGs present locally)
2. `railway up` reads `.gitignore` → excludes `*.png` from archive
3. Archive uploaded to Railway without the PNG files
4. Railway executes `docker build` — Dockerfile `COPY frontend/ ./frontend/` runs but source context has no PNGs
5. Container deploys with empty `img/` and `icons/` folders
6. FastAPI `StaticFiles` mount returns Starlette default 404 for PNG requests
7. Logo renders as broken image icon in browser

## Why It's Recurring

Without explicit whitelist, any developer/merge can re-add `*.png` to `.gitignore` (to avoid committing random screenshots, for example) without realizing it breaks production assets.

Commit `b31a42d` originally removed `*.png` from `.gitignore`. Patterns were re-added at some point (likely during a cleanup/merge), reintroducing the bug.

## Fix (PERMANENT)

`.gitignore` **must** have explicit whitelist exceptions for `frontend/` assets:

```gitignore
*.png
*.jpg
!frontend/**/*.png
!frontend/**/*.jpg
```

This preserves the ability to ignore random `*.png` screenshots in the repo root while guaranteeing that frontend assets always travel in the build context.

Applied in commit `1c92bc9` (2026-04-22).

## How to Verify Fix is Still in Place

```bash
# Should return the whitelist lines:
grep -E "!frontend/\*\*/\*\.(png|jpg)" .gitignore
```

If this grep returns nothing, the whitelist was removed. Re-add it and redeploy.

## Diagnostic Commands (for future occurrences)

If logo 404 returns, use this decision tree:

### 1. Confirm the bug type
```bash
curl -s -o /dev/null -w "%{http_code} %{content_type}\n" \
  https://app.xcleaners.app/cleaning/static/img/logo.png
```

- **404 with `application/json`** → server-side issue (file not found or routing wrong)
- **404 with `text/html`** → SPA catch-all serving HTML (path wrong)
- **200 with `text/html`** → file missing, catch-all took over
- **200 with `image/png`** → no bug, client-side issue (cache, etc)

### 2. Check container filesystem (requires Railway CLI)
```bash
cd C:/xcleaners
railway environment production
MSYS_NO_PATHCONV=1 railway ssh -s cleanclaw-api -e production \
  "ls -la /app/frontend/cleaning/static/img/ /app/frontend/cleaning/static/icons/"
```

Expected: 5 PNG files total (logo.png, icon-x.png in img/; icon-192.png, icon-512.png, icon-maskable.png in icons/).

If empty: build context upload is missing files → check `.gitignore`.

### 3. Check `.gitignore`
```bash
grep -E "^\*\.(png|jpg)" .gitignore
grep -E "!frontend" .gitignore
```

If `*.png` or `*.jpg` appear without `!frontend/**` whitelist → apply Fix above.

### 4. Check PNGs are tracked in git
```bash
git ls-files frontend/cleaning/static/img/ frontend/cleaning/static/icons/
```

Should list 5 PNG files. If empty, run:
```bash
git add --force frontend/cleaning/static/img/*.png frontend/cleaning/static/icons/*.png
git commit -m "fix(assets): re-track frontend PNGs that were removed"
```

### 5. Trigger rebuild + verify
```bash
git commit --allow-empty -m "chore(infra): trigger Railway rebuild for assets"
git push origin main
# Wait for GitHub Actions to complete (~1min)
# Verify via SSH again that PNGs are now in /app/frontend/cleaning/static/img/
```

## Why Previous "Fixes" Didn't Stick

| Commit | Approach | Why it failed |
|--------|----------|---------------|
| `eae92aa` | Append `?v=2` cache-busting to logo src tags | Treated symptom (client cache), not cause. Reverted in `d25c80e`. |
| `9d5a72d` | Marked as "debt cosmético aceito" | Not a fix — deferred. |
| `e9fdd23` | One-shot Service Worker cleanup in `cleaning/app.html` | Treated stale SW cache. Worked briefly because Luiz's browser had bad SW cached. But never addressed WHY PNGs returned 404 in the first place. |
| `1c92bc9` | Whitelist `!frontend/**/*.{png,jpg}` in `.gitignore` | **Addresses root cause.** |

## Related Files

- `.gitignore` — the fix lives here
- `.github/workflows/deploy.yml` — uses `railway up` which respects gitignore
- `Dockerfile` — line 31 `COPY frontend/ ./frontend/` is correct, not the bug
- `frontend/cleaning/app.html` — SW cleanup script on lines 44-63 is still useful for legacy clients with bad cached SW, but NOT the fix for PNG 404

## Preventive Recommendations

### Option 1 (easy, applied): Whitelist in `.gitignore`
Done in `1c92bc9`. If someone removes the `!frontend/**/*.{png,jpg}` exceptions, bug returns.

### Option 2 (robust, backlog): Dockerfile integrity assert
Add to `Dockerfile` after COPY statements:

```dockerfile
RUN test -f /app/frontend/cleaning/static/img/logo.png \
    && test -f /app/frontend/cleaning/static/icons/icon-192.png \
    || (echo "CRITICAL: PNG assets missing from build context" && exit 1)
```

Makes build fail loudly if the bug returns instead of silently deploying broken.

### Option 3 (most robust, backlog): CDN-hosted brand assets
Move logos and brand icons to Cloudflare R2 or similar CDN. Reference via absolute CDN URLs in HTML. Eliminates dependency on container filesystem entirely.

## Debugging History

See `projects/xcleaners/PROJECT-CHECKPOINT.md` (session 2026-04-22) for full diagnostic chain: Neo → Smith → Operator with 5-layer validation.
