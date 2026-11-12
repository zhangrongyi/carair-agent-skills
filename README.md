# Car Air Agent Skills

Two Codex Skills for automotive A/C work:

- [`query-carair-products`](query-carair-products/SKILL.md) queries Baijia products, stock, Ref. Price and cached customer invoice history through a protected **read-only** API.
- [`carair-new-sku-research`](carair-new-sku-research/SKILL.md) checks internal products and company development projects, researches public competitor and catalog sources, then creates or updates one `信息收集` company project with product images for employee review.

The development Skill no longer needs Lark at runtime. A one-time, separately authorized Lark export/import is maintained in the company management repository. Publishing this repository grants no internal data access.

## Installation

Install both directories with Codex `$skill-installer` from `zhangrongyi/carair-agent-skills`. Python 3.10+ is required. Each employee needs two separate credentials:

1. A product **read-only** token configured with `query-carair-products/scripts/query_products.py configure-credential`.
2. A scoped development draft token issued in the company admin panel and configured with `carair-new-sku-research/scripts/workflow.py configure-credential`.

On macOS, both use separate Keychain services; on native Windows, separate Credential Manager targets. Never put either token in Git, a chat, screenshots, or command arguments. The development token can create and update research projects and upload temporary images; it cannot modify products, prices, orders, or development stages. Admins can revoke each employee's token independently.

## Read-only setup checks

```text
python3 <QUERY_SKILL_DIR>/scripts/query_products.py health
python3 <QUERY_SKILL_DIR>/scripts/query_products.py search "Alza compressor" --limit 5
python3 <RESEARCH_SKILL_DIR>/scripts/workflow.py inspect --reference "729415" --model "CAM PLACER X VAN" --category "冷凝器"
```

`inspect` must return product queries, development candidates, and peer sources. Do not run `apply` as an installation test. For actual work, read the research Skill's field map, evidence rules, and draft format, save the draft outside the repository, then run `apply` with a stable `request_key`.

`CAR_AIR_API_BASE_URL` and `CAR_AIR_DEVELOPMENT_API_BASE_URL` may point to an explicitly configured localhost test system. Production API defaults to `https://www.baijia.com.my`.
