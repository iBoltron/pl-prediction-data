# Premier League prediction data

A small, read-only Big Balls Sports Data collector. Python 3.11+, no dependencies.
This is the data foundation for predictions, not a validated prediction model.
No bookmaker odds endpoints are requested. No API key belongs in this repository.

## Set up on GitHub

1. Create an empty **private** repository called `pl-prediction-data` at https://github.com/new.
2. Put the contents of this directory at the repository root, including `.github/workflows/collect.yml`.
3. In Settings → Secrets and variables → Actions, add repository secret **BBS_API_KEY**.
4. Open Actions → Collect Premier League data → Run workflow. Leave date blank for today in London.
5. Download the `premier-league-data` artifact from the workflow run. Upload `data.json` to the prediction chat.

To push from your computer after creating the empty repository:

```bash
cd pl-prediction-data
git init -b main
git add .
git commit -m "Add Big Balls Premier League data collector"
git remote add origin https://github.com/YOUR_USERNAME/pl-prediction-data.git
git push -u origin main
```

## What it collects

- Fixtures for the requested London date, using documented date/time-zone filters.
- Up to 15 completed matches per participating team from the current season.
- Per-match statistics, including xG **only where actually supplied**.
- Stored line-up responses for the target fixtures; presence alone is not proof of confirmed starters.
- Provider metadata, retrieval time and a coverage summary.

Output is a private workflow artifact retained for seven days, not committed to Git.
The workflow runs manually; no polling, schedule or background API usage is enabled.
Maximum 100 API calls per run; quota/HTTP errors stop the job without retries.
The fixture endpoint must honour its EPL and season filters. Unknown schemas fail visibly.

## Limits and freshness

Tested offline against synthetic records; not yet tested with a real account/key.
Missing xG is never converted to zero. Empty results are not proof of coverage.
Some endpoint records lack a source update timestamp, so freshness may be **unknown**.
Fetching now does not prove the provider updated the data now.
Early-season histories contain fewer than 15 matches; previous seasons are not silently substituted.
Completed history is cut off before the target day's London midnight AND the actual collection time.
Historical runs are not point-in-time reconstructions of historical line-ups or injury information.
If a run fails, previous output is removed and `status.json` records failure. Do not use failed runs.

## Next stage

Inspect a real `data.json` first. Then add a statistical model and chronological backtesting,
with Brier scores and calibration, before claiming better accuracy. These files do not fabricate
probabilities when coverage is inadequate. GitHub does not automatically attach its artifacts to ChatGPT.

## Local use

Set `BBS_API_KEY` in your environment using your preferred secret manager (do not put it in shell history).

```bash
python -m unittest discover -s tests -v
python collect.py --date 2026-10-17
```

## Provider references

- https://bigballsdata.com/docs/quickstart
- https://bigballsdata.com/openapi.json
- https://bigballsdata.com/soccer-api

Contract inspected 17 October 2026. Plan entitlement and data availability must be verified by a real run.
