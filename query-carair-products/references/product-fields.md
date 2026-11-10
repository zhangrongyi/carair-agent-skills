# Product field reference

## Inventory

- `stock`: Current website stock snapshot synchronized from the product data source.
- `stock_reserved`: Quantity locked by website order or issue workflows.
- `available_stock`: Signed value calculated as `stock - stock_reserved`. Negative values are valid internal data and must remain negative.
- `stock_status`: `in_stock`, `low_stock`, `out_of_stock`, or `negative`. Low stock means available quantity is from 1 through 5.
- `stock_synced_at`: Time the stock snapshot was last synchronized. Prefer this timestamp when answering stock questions.

## Price

- `ref_price`: Internal Ref. Price. It normally comes from SQL Account product details and may fall back to compatible website price fields when the primary value is absent.
- `price_source`: `internal_ref_price` when a value is present or `internal_price_missing` when no usable value exists.
- `price_synced_at`: Time Ref. Price was last synchronized.

Ref. Price is not a customer-specific historical invoice price, quotation, or guaranteed selling price.

## Customer price

- `customer_price`: Cached most recent qualifying sales-invoice price for one exact customer and one exact product.
- `price_status`: `customer_last_invoice_price` when a record exists, otherwise `no_recent_purchase`.
- `source_invoice_no` / `source_invoice_date`: Source invoice reference and business date. Describe the value as the most recent sales-invoice transaction price, not a live quote.
- `customer_price_synced_at`: When that cache record was synchronized.
- `customer_price_last_checked_at`: Latest completed cache-check task known to the API; it may be older than product inventory synchronization.
- `customer_price_valid_from`: Oldest eligible invoice date. Records before this boundary are excluded.

When `customer_price` is null, keep it null and explain `no_recent_purchase`. The separately returned `ref_price` is only a comparison and must never replace customer price.

Customer search returns only customer code, company name, currency, and customer synchronization time. Do not infer or request contacts, addresses, account balances, credit limits, order contents, or other customer details.

## Product information

- `product_code`: Stable product identifier and preferred value for a detail lookup.
- `categories`: Website category objects containing `id`, `name`, and `category_code`.
- `main_image` and `banner_images`: Absolute product image URLs.
- `product_updated_at`: Last website product record update.
- `product_synced_at`: Last base product synchronization.
- `generated_at`: API response generation time; it does not mean every underlying field was synchronized at that instant.

## Freshness

For inventory answers, cite `stock_synced_at` when present. For Ref. Price answers, cite `price_synced_at`. If the relevant synchronization time is missing, cite `generated_at` and explicitly say that the field-level synchronization time was unavailable.

Use `environment` to label every answer as production or local-test data. Product, stock, Ref. Price, customer profile, and customer-price cache timestamps are independent and must not be combined into a single “latest” time.
