---
name: carair-new-sku-research
description: Research customer-supplied automotive A/C parts against Baijia products, the Lark development table, Malaysian competitors, and catalogs; write one sourced information-collection record with a product image for human review.
---

# Car Air New SKU Research

Use this Skill when a customer supplies a part photo, listing, number, or vehicle details and the employee wants a researched record in `开款2.0`. Read [references/field-map.md](references/field-map.md) before mapping fields, [references/review-rules.md](references/review-rules.md) for evidence and fitment, and [references/draft-format.md](references/draft-format.md) before writing.

## Workflow

1. Inspect the supplied material. Transcribe visible numbers and labels exactly; mark uncertain OCR. Keep customer images in an authorized local workspace outside the Skill repository. Identify the requesting customer for `采购说明`.
2. Run `scripts/workflow.py inspect` with the available references, vehicle model, and category. It calls the separate `query-carair-products` read-only Skill, reads every existing `贸易型产品开发` row, and reads the competitor directory. Search important numbers separately and broaden product queries when needed. If an internal query fails, stop and report the incomplete check.
3. Distinguish existing sale SKU, same development record, near match, and no result. An exact external reference already in the development table means update that record, not create another. A missing result does not prove absence. Record technical differences from near matches.
4. Research the competitor-directory sites first, then selected Malaysian marketplaces, then broader sources and manufacturer catalogs. Capture exact URLs, access date, number, model, image comparison, currency, and retail/wholesale context. A listing alone does not prove physical interchangeability.
5. Write a concise product title in `产品描述`; place customer requests, listing context, and pending procurement questions in `采购说明`. Use the vehicle make for `品牌` and the vehicle series for `车型`. Put supported technical fitment in `车款信息说明`, external numbers in `外部参考编号`, and source URLs in `核对来源链接`. Include every relevant customer-supplied product photo in `image_paths`. For each matching competitor product page that has useful product photos, inspect the gallery and put at least one direct image URL with its product-page URL and source label in `source_images`; include more angles when they help compare fitment. Choose actual product photos, not logos, ads, or unrelated variants. If no comparable competitor image can be obtained, document the reason in `source_image_gap_reason`. Do not upload unrelated customer chats or personal data.
6. Save one JSON draft outside the Git repository and run `scripts/workflow.py apply DRAFT.json`. It validates fields, downloads and validates competitor images before any row write, rechecks both internal sources, writes one new or existing Lark record, uploads customer and competitor images together, and reads the row back. No pre-write human confirmation is required for this information-collection record. The result is then sent to the employee for **post-write human review**, with the record link, image sources, evidence, differences, and unresolved checks. Do not claim customer-vehicle fitment or advance the project stage until those checks are resolved.

The first write stage is `信息收集`, development type `贸易型`. Unknown fitment is allowed only when plainly recorded as pending. Never assign a new CXA SKU, fill unknown supplier/cost/planned price, quote a customer, place an order, or contact a supplier as part of this workflow. Do not update the product catalog.

## Commands

```text
python3 <SKILL_DIR>/scripts/workflow.py inspect --reference "ZETWIND 790482; DENSO DCP51012" --model "TOYOTA CAMRY 2.5 HYBRID" --category "压缩机"
python3 <SKILL_DIR>/scripts/workflow.py apply /path/outside/repo/draft.json
```

On macOS use `python3`; on Windows use `py -3`. The machine needs `lark-cli` authorized as the employee and `query-carair-products` with its own read-only credential. The script uses `--as user` for Lark. Never request credentials in chat.

## Partial failures

The script downloads only public HTTPS images, with size and image-type checks. If downloading a cited competitor image fails, it stops before writing and asks the agent to find a working product image or document the gap. It returns the record ID if the row was written but image upload or readback failed. **Inspect that record before any retry**; a second create could duplicate it. If a write response is ambiguous and no ID is returned, search the table by external reference before doing anything else. Do not bypass failed CLI or API checks through database, SSH, administrator endpoints, or another employee's credentials.
