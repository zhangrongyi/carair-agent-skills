---
name: carair-new-sku-research
description: Research customer-supplied automotive A/C parts against Baijia products, company development projects, Malaysian competitors, and catalogs; write one sourced information-collection project for employee review.
---

# Car Air New SKU Research

Use this Skill when a customer supplies a part photo, listing, number, or vehicle details. The company management system is the development source of truth; this Skill does not read or write Lark. Read [references/field-map.md](references/field-map.md), [references/review-rules.md](references/review-rules.md), and [references/draft-format.md](references/draft-format.md).

## Workflow

1. Transcribe customer-provided numbers and labels exactly. Mark uncertain OCR. Keep customer images outside this repository. Identify the requesting customer for `采购说明` without uploading unrelated chats or personal data.
2. Run `scripts/workflow.py inspect` using reference, model, and category. It invokes the separate `query-carair-products` read-only Skill and the scoped company development API. Inspect **all** returned product and development candidates plus the company peer directory. If either internal query fails, stop; do not bypass it with SQL, SSH, or administrator endpoints.
3. Distinguish an existing sale SKU, exact development project, near match, and no result. Exact external reference means update the existing project rather than create another. Explain technical differences from near matches. Absence from search is not proof of absence.
4. Research peer-directory sites first, then Malaysian marketplaces and manufacturer catalogs. Capture exact URLs, access date, numbers, model, images, currency, and retail/wholesale context. Listings alone never confirm physical interchangeability.
5. Write a concise product title in `产品描述`; keep customer request and procurement questions in `采购说明`. Use vehicle make for `品牌`, series for `车型`, technical fitment evidence and limitations in `车款信息说明`, and cited URLs in `核对来源链接`. Include relevant customer product images and useful competitor product photos, with page and direct image URLs. If no comparable competitor photo exists, explain why.
6. Save one JSON draft outside Git with a stable `request_key`, then run `scripts/workflow.py apply DRAFT.json`. It validates the draft, downloads public HTTPS competitor images, rechecks both internal sources, uploads images to private temporary storage, and creates or updates one project through the scoped employee API. The API repeats checks and makes the write idempotent. Return the company project ID and source summary for **post-write human review**. Do not advance the stage or claim fitment until the employee verifies it.

New projects start at `信息收集`, default `贸易型`. Never assign a new CXA SKU, invent supplier/cost/price, quote a customer, place an order, or contact a supplier. Do not update the product catalog.

## Commands

```text
python3 <SKILL_DIR>/scripts/workflow.py configure-credential
python3 <SKILL_DIR>/scripts/workflow.py inspect --reference "ZETWIND 790482; DENSO DCP51012" --model "TOYOTA CAMRY 2.5 HYBRID" --category "压缩机"
python3 <SKILL_DIR>/scripts/workflow.py apply /path/outside/repo/draft.json
```

Each employee needs a separate development draft token issued in the company admin system, stored through `configure-credential` in macOS Keychain or Windows Credential Manager. The separate product read-only Skill keeps its own credential. `CAR_AIR_DEVELOPMENT_API_BASE_URL` and an ephemeral `CAR_AIR_DEVELOPMENT_API_TOKEN` can be used for local testing; never pass a token in command arguments, chat, screenshots, or a Git file.

## Partial failures

Source image download failure stops before upload. Uploaded images may remain temporary for up to one day if the final write fails. For an ambiguous final response, `apply` checks `request_key` before any retry; keep the same key and inspect the project. If a candidate set changed, rerun `inspect` and review the new candidates. A missing/expired credential or disabled module is reported, not bypassed.
