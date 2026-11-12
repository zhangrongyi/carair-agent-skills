# Development project field map

The company management system stores the project. The following Chinese draft fields remain stable for employees familiar with `开款2.0`; `workflow.py` maps them to the scoped development API.

| Draft field | Meaning |
| --- | --- |
| `品牌` | Vehicle make, not compressor maker or supplier. |
| `车型` | Vehicle series; keep generation and engine details in notes. |
| `年份` | Verified year or range, labeling listing-only claims. |
| `类目` | Existing English product category, such as `COMPRESSOR`. |
| `产品描述` | Short part title with distinguishing variant or number. |
| `采购说明` | Requesting customer, buying context, and open questions. |
| `车款信息说明` | Fitment evidence and limits, including physical checks still pending. |
| `外部参考编号` | Competitor, manufacturer, and catalog references, each labeled by source. |
| `核对来源链接` | Exact HTTPS product/catalog pages, one per line. |
| `同行价格` | Only supported by currency, date, condition, pack size, and retail/wholesale level. Add `peer_currency` and `peer_price_level` to the draft. |

New projects have stage `信息收集` and type `贸易型`. Unknown fitment is allowed only when explicit in `unresolved` and the notes. Supplier, factory number, cost, planned price, CXA number, and order fields remain outside the automated writer. Customer and competitor product images are uploaded to private company storage with their source metadata.
