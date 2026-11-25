# Explaining RetailRank

## A simple introduction

RetailRank recommends products using a shopper's recent views, cart actions and purchases. It first finds possible products, then ranks them. It includes a working demo and a comparison of four recommendation methods on later historical data.

## Why two stages?

Retrieval narrows the catalog to a small group of candidates. Ranking uses more features to order that group. The ranker cannot recover a relevant product that retrieval missed, which is why candidate recall matters.

## What is ALS doing?

It learns short numerical vectors for shoppers and products from their interaction patterns. Products used by similar shoppers can end up with related vectors. For a new session, we calculate a shopper vector using the learned product vectors. These vectors do not come from product descriptions.

## Why do purchases have more weight?

A purchase usually gives a stronger interest signal than a view. The 1/3/6 weights are a modeling choice, not a proven universal rule. They should be compared using validation data.

## Why LightGBM?

It can combine several numerical signals and learn how to order a candidate list. LambdaMART trains for ranking. Using an established library lets this project focus on data handling, evaluation and serving.

## What prevents data leakage?

Catalog selection and retrieval training use the earliest period. Ranker training, validation and testing happen in later windows. A query's history contains only strictly earlier events. Training may add a missed target to its candidates, but validation and testing do not. The shared inference code keeps demo behavior aligned with evaluation.

## How good is it?

In 2,000 test queries, the next item appeared in the ranker's top 10 in 11.3% of cases, compared with 7.2% for ALS. Similarity scored 11.1% and had slightly better NDCG, so the ranking model does not win every comparison. The results are offline; they do not establish increased sales.

## Why are many predictions wrong?

Only 53.05% of test targets are in the capped catalog, and candidate recall is 26.2%. Some profiles contain no known products. Improving candidate coverage is a more useful first step than only tuning the ranker.

## What happens when someone clicks a product?

The API saves the action in SQLite and recalculates recommendations from the session's recent history. The model weights stay fixed. Scheduled retraining would be a separate feature.

## What did the project implement around the libraries?

Dataset cleaning, chronological sessions and queries, combining candidate sources, ranking features, baseline comparisons, evaluation audits, API/session storage, historical replay and the browser dashboard. The ALS and LambdaMART algorithms come from Implicit and LightGBM.

## What would improve next?

Expand the catalog, test co-occurrence and sequential retrieval, compare performance on different session types, add scheduled retraining, and measure serving performance under concurrent traffic. Use a durable database and request limits for a public service. Collect real exposure logs before attempting an online business-impact evaluation.
