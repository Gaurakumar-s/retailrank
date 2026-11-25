# Sources and third-party notices

## Retailrocket ecommerce dataset

Original source and attribution: **Retailrocket**, [ecommerce dataset](https://www.kaggle.com/datasets/retailrocket/ecommerce-dataset).

Kaggle metadata identifies the dataset license as [Creative Commons Attribution–NonCommercial–ShareAlike 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). Preserve the attribution and applicable terms when redistributing or adapting this data. This project is for noncommercial educational use.

The raw dataset is not bundled. `scripts/download_data.py` downloads the original events file. SHA-256: `3745aa83238b1e6d44d8fda209807899f420084398f94ddf745f3cbcfecbf9e7`.

Changes made: exact interaction deduplication, chronological splitting, catalog filtering, weighted interaction modeling, session/query sampling, model training and aggregate evaluation. Dataset-derived model artifacts and historical replay examples are provided under CC BY-NC-SA 4.0. This project is not affiliated with or endorsed by Retailrocket.

## Algorithm libraries

- **Implicit**, Ben Frederickson and contributors: https://github.com/benfred/implicit — MIT license. Used for implicit-feedback ALS training. Upstream license: https://github.com/benfred/implicit/blob/main/LICENSE
- **LightGBM**, Microsoft Corporation and LightGBM developers: https://github.com/microsoft/LightGBM — MIT license. Used for LambdaMART ranking. Upstream license: https://github.com/microsoft/LightGBM/blob/master/LICENSE

These libraries are installed as dependencies, not presented as algorithms invented by this project. Other dependencies and their pinned versions are listed in `requirements.txt`; their own licenses apply. The browser requests Manrope and DM Sans from Google Fonts and falls back to local sans-serif fonts when unavailable.
