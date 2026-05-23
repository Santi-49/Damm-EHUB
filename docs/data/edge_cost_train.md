# `edge_cost_train` — merged into `wo_changeovers.csv`

> This data product no longer exists as a separate file.
>
> [`wo_changeovers.csv`](./wo_changeovers.md) is now the transition master table
> and the direct training input for the changeover ML model. It contains
> `sku_from_id`, `sku_to_id`, all SKU attribute features, change flags, context
> features, and the `changeover_hours` target — purely from real observations.
>
> `changeover_costs.csv` (theoretical matrix) is **not** used as training data;
> it serves only as the optimizer's floor/fallback for unseen pairs.
