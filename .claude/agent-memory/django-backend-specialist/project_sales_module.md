---
name: project-sales-module
description: Sales module architecture — key models, flows, and design decisions added in the June 2026 expansion
metadata:
  type: project
---

The sales module (PDV) was significantly expanded in migration 0083. Key additions and patterns to know:

**`stock_reduced` flag on `Sale`** — introduced to distinguish rascunho (draft) saves from finalized sales. Stock is only reduced when `stock_reduced=True`. All cancel and edit flows check this flag before reversing stock. Never assume a Sale has its stock reduced just because it exists.

**`ProductVariant` model** — products with `format=COM_VARIACOES` have related `ProductVariant` rows. `SaleItem.variant` FK points here. In stock operations (reduce/increase), always check `item.variant if item.variant else item.product` — the target can be a variant or the product itself.

**`SaleReturn` / `SaleReturnItem`** — two-step approval flow. Returns start as PENDENTE, stock is NOT restored until `sale_return_approve` is called (POST). Cancellation (CANCELADA) never touches stock.

**`cost_price_ato` on `SaleItem`** — frozen cost price at the time of sale, set inside `SaleItem.save()` in the same `if is_new or product_changed or not self.ncm_ato:` block that freezes fiscal fields.

**`sale_export_csv`** — uses `utf-8-sig` BOM encoding and `;` delimiter for Excel compatibility. Reuses the same filter params as `sale_list`.

**URL ordering** — `vendas/exportar/` and `vendas/devolucoes/<id>/...` MUST come before `vendas/<int:number>/` in urls.py to avoid Django resolving "exportar" and "devolucoes" as integer `number` captures.

**Why:** Needed draft saves, variant-aware stock, return workflow, KPI dashboard, and CSV export for the commercial team.

**How to apply:** When touching sale/stock logic, always respect the `stock_reduced` flag and the `variant or product` target pattern.
