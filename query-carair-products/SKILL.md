---
name: query-carair-products
description: Query Zhejiang Baijia products and cached customer invoice prices through the protected read-only Codex API. Use for product codes or keywords, stock, reserved or available stock, Ref. Price, categories, images, freshness, customer searches, or a customer's recent sales-invoice price. Also use for Chinese requests such as 查询商品、查库存、参考价、客户成交价、最近销售价、商品图片 or 按车型找产品.
---

# Query Car Air Products

Use the bundled client to retrieve internal production or explicitly configured local-test data. Never connect directly to PostgreSQL, SSH, administrator APIs, or SQL Account.

## Query workflow

1. Use `CAR_AIR_API_BASE_URL` when set; otherwise use `https://www.baijia.com.my`. The client reads `CAR_AIR_CODEX_API_TOKEN` first and otherwise reads the operating-system credential store: macOS Keychain service `com.baijia.codex-readonly-api`, account `production`, or Windows Credential Manager target `com.baijia.codex-readonly-api:production`.
2. Choose one command:
   - Run `detail PRODUCT_CODE` only when the user supplied one unambiguous product code.
   - Run `search QUERY` for names, vehicle models, partial codes, categories, or discovery.
   - Run `customers QUERY` when resolving a customer name or partial customer code.
   - Run `customer-price CUSTOMER_CODE PRODUCT_CODE` only with an exact customer code and exact product code.
   - Run `health` for connection, source, freshness, or authentication diagnostics.
3. Resolve the directory containing this `SKILL.md`, then execute its bundled `scripts/query_products.py` with the selected command. Use `python3` on macOS/Linux or `py -3` on Windows. Never place the token in command arguments.
4. Read the JSON result. Treat `ok: false` as a failed query; do not invent product values.
5. State whether `data.environment` is `production` or `local`, then present the requested values and their field-specific synchronization times.

## Search commands

```bash
python3 "<SKILL_DIR>/scripts/query_products.py" search "Nissan condenser" --in-stock --limit 10
python3 "<SKILL_DIR>/scripts/query_products.py" search "Toyota Estima 03" --category CONDENSER
python3 "<SKILL_DIR>/scripts/query_products.py" detail CXA-671096
python3 "<SKILL_DIR>/scripts/query_products.py" customers "Example Customer"
python3 "<SKILL_DIR>/scripts/query_products.py" customer-price CUSTOMER_CODE CXA-671096
python3 "<SKILL_DIR>/scripts/query_products.py" health
```

On Windows, use the same commands with `py -3` and Windows path separators, for example:

```powershell
py -3 "<SKILL_DIR>\scripts\query_products.py" health
```

To configure the production token, run this in an interactive local terminal. The prompt accepts the secret without echoing it or placing it in command arguments. It stores the token in macOS Keychain or Windows Credential Manager:

```bash
python3 "<SKILL_DIR>/scripts/query_products.py" configure-credential
```

`configure-keychain` remains available as a macOS compatibility alias.

Use `--out-of-stock` only when the user explicitly asks for unavailable or negative-stock products. Keep the default limit at 10 unless the user asks for more; never exceed 20.

## Response rules

- If exactly one search result clearly matches, answer from that result.
- If multiple plausible products match, list compact candidates with product codes and titles, then ask the user to choose. Do not select one silently.
- If no product matches, say so and suggest a shorter code, model, or category query.
- Always state the response `generated_at` time or the most relevant `stock_synced_at` / `price_synced_at` time.
- Always state the data source from `environment`; never infer production solely from the URL.
- Describe `ref_price` as **Ref. Price**. State that it is an internal reference price, not a customer-specific last transaction price.
- Describe `customer_price` only as the **最近销售发票成交价** and cite `source_invoice_date` plus `customer_price_synced_at` or `customer_price_last_checked_at`. It is cached history, not a real-time quote.
- If `price_status` is `no_recent_purchase`, say that no qualifying sales-invoice purchase was found since `customer_price_valid_from`. Do not substitute Ref. Price for the missing customer price.
- If customer search returns multiple plausible matches, list customer code and company name and ask the user to choose. Continue automatically only for an exact code or one unique, unambiguous match.
- Preserve negative available stock and label it clearly; do not clamp it to zero.
- Show image URLs only when the user asks for images or product details.

Read [references/product-fields.md](references/product-fields.md) when interpreting fields or explaining freshness and pricing.

## Safety and failures

- Only query active-customer identity fields and the single cached customer × product price endpoint. Never query contacts, addresses, balances, credit limits, order contents, costs, or write endpoints.
- Never fall back to direct database access, server SSH, the public PC endpoint, administrator tokens, or SQL Account when the protected API fails.
- On missing credentials or `401`, report that the local environment or operating-system credential-store token is missing or invalid. Never ask the user to paste a token into chat.
- On `429`, report the rate limit and retry only after a short wait when the user still needs the query.
- On `404`, distinguish a missing product from a missing undeployed API by reading the structured error.
- On timeout, non-JSON, or server failure, report that current data could not be verified.
