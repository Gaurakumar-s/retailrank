# RetailRank model card

## Intended use

A noncommercial educational demo of personalized next-item recommendation. It operates on anonymous product IDs from historical Retailrocket browsing, cart and transaction events. It is not evidence of business impact and does not predict an individual's purchase probability.

## Data and splits

Source: https://www.kaggle.com/datasets/retailrocket/ecommerce-dataset

License reported by Kaggle: CC BY-NC-SA 4.0. Raw events: 2,756,101; after exact timestamp/visitor/event/item deduplication: 2,755,641.

| Period boundary | UTC timestamp |
| --- | --- |
| Data start | 2015-05-03 03:00:04.384 |
| Retrieval training end | 2015-07-24 22:11:54.426 |
| Ranker training end | 2015-08-14 14:59:51.937 |
| Validation end / test begins | 2015-08-28 10:11:50.277 |
| Data end | 2015-09-18 02:59:47.788 |

Time boundaries are 60%, 75% and 85% of the observation span, not percentages of rows. The catalog selects the top 20,000 items with at least five earlier events. ALS fits visitors with 2–100 distinct catalog items: 105,476 visitors and 511,378 events. This limits very heavy activity but is not a validated bot detector.

Sessions use a 30-minute gap. Each query uses up to 20 prior interactions and targets an item absent from that history. Tied timestamps cannot create an earlier-to-later query. There are at most three queries per session. Seeded reservoir samples contain 7,000 training, 2,000 validation and 2,000 test queries. This measures recommendations within active sessions; first-visit cold start is tested separately.

## Models

View/cart/transaction weights are 1/3/6, converted into ALS confidence as `1 + 15 * log1p(total weight)`. Implicit ALS uses 32 factors, 15 iterations and regularization 0.1. New session factors are solved with fixed item factors. Offline and online code share this calculation; its maximum score discrepancy from Implicit's fold-in implementation was approximately 6.52e-8.

Candidate retrieval merges up to 60 ALS, 60 recency-weighted normalized item-factor similarity and 20 popularity candidates. These are behavioral embeddings, not text or image embeddings. Empty or entirely unknown profiles fall back to popularity.

LightGBM LambdaMART ranks candidates using 12 relevance, popularity and history features. It uses learning rate 0.05, 15 leaves, minimum child samples 40, L2 penalty 2 and at most 250 trees. Early stopping selected iteration 20 using validation candidate groups. A ranking score is not a calibrated probability.

Training included 3,013 eligible groups: 1,911 already retrieved the positive and 1,102 required positive injection. Other sampled training queries had unknown targets (2,966) or profiles (1,021). Injection creates useful training positives but introduces a train/serving distribution difference. Unobserved candidates are training negatives, not confirmed dislikes. Validation and test never inject targets. Early stopping uses eligible validation candidate groups; full evaluation retains all 2,000 queries, including unretrievable targets.

## Evaluation

Full metrics are saved in `reports/metrics.json` and displayed in the app. On 2,000 test queries, ranker Hit@10 is 11.30%, versus ALS 7.20%, similarity 11.10% and popularity 0.15%. Ranker NDCG@10 is 0.05889; similarity is slightly better at 0.05944. With one target, Hit@K equals Recall@K. NDCG rewards earlier placement; MRR uses reciprocal rank.

Candidate recall: 26.2%. Target catalog coverage: 53.05%. Queries with a known profile: 59.5%. Ranker top-20 recommendations cover 35.64% of the catalog across test queries. Unknown targets count as misses. Item factors/statistics remain frozen after retrieval training; no future events update them.

The 95% paired query-bootstrap interval for ranker minus ALS NDCG@10 is [0.00985, 0.02435]. Queries may come from the same shopper/session, so this is descriptive and not an independent-user confidence interval.

Local inference: p50 0.64 ms, p95 0.78 ms for 100 queries, Python 3.12.15 on macOS ARM64, with two BLAS/OpenMP threads. Network, database and serving overhead are excluded. Performance will vary by machine.

## Limitations and next experiments

The data is from 2015, the catalog is capped, and only observed activity is available. There are no exposure propensities or verified negative preferences. Popularity bias and distribution shifts are plausible. The model does not represent names, prices, availability or product categories. It does not learn continuously when demo buttons are clicked.

Prioritize broader retrieval/catalog coverage, item-to-item co-occurrence baselines, user/session-grouped uncertainty estimates and new validation data before claiming improvement. Compare sequential models under the same time splits. Any real conversion measurement would require an appropriately designed online experiment.
