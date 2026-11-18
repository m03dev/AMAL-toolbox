---
name: public-apis
description: Find a free public API for a need (weather, maps, images, data, a game service) and prove it works before a job builds on it - maintained, documented, its limits and terms known, a real call made.
---
For "find an API for <need>", or any job that needs outside data or a service. A job builds on an API only after this
check; an API that cannot be called for real is reported as unproven, never used as if it works.

1. **Look in the maintained lists first** (with `web`): github.com/public-apis/public-apis (the big list, by category),
   github.com/public-api-lists/public-api-lists, and davemachado's public-api index; then the service's own developer
   page. Take 3-5 candidates that fit the need.
2. **Check each against the same points**, from its own documentation and repository, dated:
   - *maintained*: a release, changelog entry or commit in the last 12 months; the endpoint answers.
   - *documented*: request and response formats written down, with examples.
   - *authentication*: none, an API key, or OAuth (OAuth needs the owner's account: say so).
   - *limits*: requests per minute/day on the free plan.
   - *cost*: free, free tier (what triggers a charge), or paid. AMAL uses free routes only: a key that needs a card is
     reported, not signed up for.
   - *privacy and terms*: what is sent, what is kept, whether commercial use is allowed.
   - *reliability*: status page or uptime history when there is one.
3. **Call it for real** with `run` (curl), the smallest request that shows it works; keep the command and the answer.
   A key the owner must create: say where and stop at that step - never sign up for him.
4. **Report** `apis.md` in the job folder: the pick first (why, its limits, the working call), then a table of every
   candidate on the points above with links. Keys never go in the report, the code or the logs.
