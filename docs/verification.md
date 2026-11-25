# Verification

Checked on November 25, 2026.

## Automated

- 9 pytest tests passed locally under Python 3.12.
- `node --check web/app.js` passed.
- The packaged model and API previously passed an extracted-package startup smoke check.
- GitHub Actions defines API/model tests and a Docker build plus HTTP health/recommendations smoke check. Its live status is linked from the README.

## Browser checks

The browser ran the local FastAPI application with the actual bundled model.

- Reset showed popular items and an empty session.
- One-click example shopper loading changed the recommendations and activity.
- Revealing the next historical item honestly displayed a miss in the eight suggestions.
- Opening an item recorded a view and displayed an accessible native dialog.
- Demo cart and simulated purchase actions updated the profile and showed confirmation.
- Switching to similarity updated the serving-method indicator.
- An unknown item-number search displayed an empty state; clearing the search restored the catalog.
- Explore, Model results and How it works navigation worked.
- Results displayed the saved 2,000-query test evaluation.
- Desktop layout and a 390 × 844 mobile viewport were inspected visually. Both Explore and Model results had no page-width overflow at 390px.
- No browser console errors were recorded in this check.

## Scope

This is a research demo deployed on Render. No real purchases, online conversion experiment, accessibility certification or multi-user load test is claimed. Model quality metrics are unchanged by the interface redesign.

## Public deployment verification

Live URL: https://retailrank.onrender.com

Deployed the Docker image on Render's Free service. The public health endpoint reports `retailrank-v1` with 20,000 products. Verified homepage/static assets, an HTTPS Secure/HttpOnly/SameSite session cookie, popularity fallback, historical shopper replay, future-target exclusion, cart-driven recommendation updates, cross-origin mutation rejection and the 2,000-query evaluation report. The live browser also loaded an example shopper and the results dashboard.

The free instance can sleep after inactivity. Initial visits may take 50 seconds or more to wake it. SQLite demo activity is temporary and can reset on restarts or redeploys. The trained model is bundled in the image and remains available after restart.
