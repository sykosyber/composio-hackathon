# Legacy

`ballot_explainer/` is an earlier idea this repo started with: a ballot explainer that read
your inbox and researched each race with citations. The project pivoted on October 19 2026 to
the neighborhood pin and route agent in the root of this repo.

It is kept for history only. It is not part of the product, it is not wired into the app, and
it should not be extended. The reusable infrastructure from it, env and config loading, the
LLM client, the Composio session setup, the Parallel client setup, and the caching helpers,
now lives in `app/` and is imported from there.

The only election feature in the current product is one static card of dates and logistics in
the morning brief. There is no race research.
