# Deployment

Public demo: https://retailrank.onrender.com

The app runs as a Docker web service on Render's Free plan in Oregon. It uses the repository's Dockerfile, the `main` branch and `/api/health` as its health endpoint. No external model API or training job is required at startup.

## Update the app

Push a tested change to `main`. In the Render service dashboard, use Manual Deploy to deploy the latest commit if an automatic deploy is not triggered. Deploy into the existing `retailrank` service to retain the same public URL.

## Runtime behavior

- Render supplies the HTTP port; the Docker command binds to `0.0.0.0`.
- The bundled model contains the item factors, ranker and evaluation report.
- SQLite stores anonymous demo activity in `/app/runtime`.
- Free hosting has no persistent disk, so demo sessions may reset after restarts or redeploys.
- Free instances sleep after inactivity; opening the demo can take 50 seconds or more while it wakes.

## Checks

GitHub Actions builds the Docker image and verifies the HTTP health and recommendation endpoints. After deployment, open the demo, load an example shopper and check Model results. The public `/api/health` should report status `ok`, catalog size 20000 and model version `retailrank-v1`.
