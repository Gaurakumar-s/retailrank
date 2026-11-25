# RetailRank

[![Project checks](https://github.com/Gaurakumar-s/retailrank/actions/workflows/checks.yml/badge.svg)](https://github.com/Gaurakumar-s/retailrank/actions/workflows/checks.yml)

**Live demo: [retailrank.onrender.com](https://retailrank.onrender.com)**

A working product recommendation demo that updates recommendations as a shopper views products, adds them to a cart, or simulates a purchase. It combines collaborative filtering, behavioral similarity and a learned ranking model, with a dashboard for comparing results.

Products are anonymized Retailrocket item IDs. The interface uses abstract illustrations; it does not invent product names, prices or real purchases.

## Run locally

Use Python 3.12. A trained model is included, so downloading the dataset is optional.

```sh
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install --no-deps -e .
sh scripts/run.sh
```

Open http://127.0.0.1:8002. API documentation is at `/docs`. On macOS, if LightGBM reports a missing OpenMP library, install `libomp` through Homebrew. After setup, `Start-RetailRank.command` also starts the app.

## Try the demo in one minute

1. Open **Explore** and click **Try an example shopper**. Suggestions now use a real historical session's earlier activity.
2. Click **Explore item** to open its details. Add it to the demo cart or simulate a purchase and watch the activity counts and recommendations change.
3. Use **Reveal their next item** after loading an example to compare suggestions with the actual outcome. Examples include misses; they are not selected for successful predictions.
4. Open **Compare recommendation methods** to switch models while keeping the same activity.
5. Open **Model results** for the baseline comparison, evaluation timeline, coverage and limitations. **How it works** explains the pipeline.

**Start over** clears the current session. Search accepts item numbers. Purchases are simulated; there are no payments. Actions change the session profile immediately; they do not retrain model weights.

## Architecture

1. Clean and chronologically split the interaction data.
2. Train 32-dimensional implicit-feedback ALS item factors using **Implicit**.
3. Retrieve the union of up to 60 ALS, 60 behavioral-similarity and 20 popular candidates, excluding the last 20 interacted items.
4. Rank candidates with **LightGBM LambdaMART**, using 12 features covering relevance, popularity and session behavior.
5. Serve the shared inference code through **FastAPI**, with SQLite session/action/impression storage and a browser demo.

The implementation uses open-source algorithms from Implicit and LightGBM. Data preparation, chronological query construction, candidate combination, evaluation, serving and the demo are implemented in this project. See `THIRD_PARTY_NOTICES.md` for sources.

## Measured results

Processed **2,756,101 raw events** and selected **20,000 products** from the retrieval training period. ALS was fitted on 511,378 events from 105,476 eligible visitors. The results below use **2,000 sampled chronological test queries**; each asks for the next item outside the previous 20 interactions.

| Method | Hit rate @10 | NDCG @10 | Hit rate @20 |
| --- | ---: | ---: | ---: |
| Popularity | 0.15% | 0.00065 | 0.20% |
| ALS | 7.20% | 0.04178 | 10.30% |
| Behavioral similarity | 11.10% | 0.05944 | 14.95% |
| Two-stage ranker | **11.30%** | 0.05889 | **15.85%** |

The ranker improves top-10 hit rate by **4.1 percentage points over ALS**. The similarity baseline slightly outperforms it on NDCG and MRR; the ranker does not win every measure. These are offline recommendation results, not classification accuracy or demonstrated sales uplift.

Candidate recall is 26.2%; only 53.05% of test targets belong to the selected catalog. Out-of-catalog targets remain misses in the denominator. This makes improving retrieval and catalog coverage a priority.

Local inference p50/p95 was 0.64/0.78 ms over 100 queries on the recorded Mac environment. This excludes HTTP/network overhead and is not a production load benchmark. Full results and environment details: `reports/metrics.json`.

## Reproduce training

```sh
python scripts/download_data.py
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 python -m retailrank.train --events data/events.csv
pytest -q
```

The downloader verifies the original events file SHA-256. Training overwrites the bundled model and reports; restart the server afterward. The original dataset is downloaded separately and subject to its CC BY-NC-SA 4.0 license.

The retrieval period ends July 24, 2015 (UTC). Later windows train the ranker, validate it, and finally test it. Catalog selection and item statistics use only the first window. Histories contain strictly earlier events; future targets are never added to validation/test candidates. Ranker training does inject a missing positive target, and the audit counts disclose this. See `docs/model-card.md` for exact timestamps and limitations.

## API and persistence

- `GET /api/health`, `/api/metrics`, `/api/catalog`, `/api/state`
- `GET /api/recommendations?method=ranker&k=10`
- `POST /api/actions` with `{"item_id":5411,"event":"view"}` (also `addtocart`, `transaction`)
- `GET /api/scenarios`, `POST /api/scenarios/{index}`, `POST /api/reset`

Anonymous sessions use an HttpOnly cookie. SQLite records actions and impressions with the method and model version. The default database is `runtime/demo.sqlite3`; set `RETAILRANK_DB` to change it. This is a research demo with simulated purchases, not a live store. Hosting with an ephemeral filesystem will lose session records on restart; use durable storage for persistent public use.

## Validation and deployment

**9 tests pass**, covering ranking math, strict chronological histories, cold start, session isolation, invalid inputs, replay target separation and evaluation audits. Browser checks covered example shoppers, item details, cart/purchase actions, search, method switching and navigation. Desktop and 390px mobile layouts were visually checked. See `docs/verification.md`.

GitHub Actions runs the test suite and a separate Docker build/HTTP smoke check on pushes and pull requests. A Dockerfile and Render blueprint are included. The public demo runs on Render’s free Docker service; check the workflow status above for the latest container result. The first visit after inactivity may take 50 seconds or more while the service wakes up. Demo activity uses temporary SQLite storage and may reset when the instance restarts or redeploys. The included model requires no training during startup. For a public service, add request throttling, storage retention, deployment monitoring and a durable database as needed.

## Files

- `src/retailrank/train.py`: data pipeline, training and evaluation
- `src/retailrank/engine.py`: common offline/online recommendation logic
- `src/retailrank/api.py`: HTTP API and SQLite persistence
- `web/`: interactive demo and evaluation dashboard
- `artifacts/model.joblib`: trusted trained model; never load arbitrary uploaded joblib files
- `docs/model-card.md`: methodology and limitations
- `docs/interview-guide.md`: explanation of design choices

Future improvements: broader candidate coverage, comparisons with item-to-item co-occurrence and sequential models, session-grouped confidence intervals, scheduled retraining, and online evaluation with consented exposure logs.

## License

Project code: MIT, Gaurav Kumar. Dataset-derived artifacts and replay examples: CC BY-NC-SA 4.0. See `LICENSE` and `THIRD_PARTY_NOTICES.md`.
