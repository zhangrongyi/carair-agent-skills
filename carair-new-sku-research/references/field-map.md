# 开款2.0 field map and writing convention

Most rows use `品牌` for the **vehicle make** (TOYOTA, BMW, PROTON), `车型` for the **vehicle series** (CAMRY, X70, X1), `产品描述` for a short part title, `采购说明` for the requesting customer and buying context, and `产品图片` for one or more attachments. Existing rows may be inconsistent, so use the rules below rather than copying their mistakes. The Skill writes only this table and reads `汽车空调行业同行与客户档案` → `公司档案` for source discovery.

| Field | Rule | Example for ZetWind 790482 |
| --- | --- | --- |
| `品牌` | Vehicle manufacturer, not compressor maker, competitor, or supplier. Use an established vehicle make; if unknown, leave it unresolved and do not invent one. | `TOYOTA` |
| `车型` | Vehicle series only; keep generation, engine, and year in description or vehicle notes. Use established spelling consistently. | `CAMRY` |
| `年份` | Verified applicable year or range, with uncertainty clearly stated if only a listing supplies it. | `2015（ZetWind 页面）` |
| `类目` | Existing English select option. | `COMPRESSOR` |
| `产品描述` | Short product name: part category + vehicle make/series + distinguishing version/specification/part number. No phrases such as “客户指定”“页面所示”“根据网页”. | `COMPRESSOR TOYOTA CAMRY 2.5 HYBRID ES27 DCP51012` |
| `采购说明` | Requesting customer, source listing context, desired quantity/price when supplied, and open buying or fitment questions. Clearly label unverified claims. | `客户提出需求；ZetWind 790482 页面标注 ES27C / ND 042200-0460；客户实车 VIN 与旧件插头待核对。` |
| `车款信息说明` | Technical fitment evidence and limits: engine, generation, catalog period, OE number role, connector/pipe/mounting checks. Distinguish observed, corroborated, and pending. | `Denso 目录：Camry 2AR-FXE ...` |
| `外部参考编号` | Competitor, manufacturer, and catalog numbers with their source names; do not mislabel a competitor code as OE. | `ZETWIND 790482; DENSO DCP51012; ND 042200-0460` |
| `核对来源链接` | Exact HTTPS URLs, one per line, supporting the identifiers and fitment. | Source product page and catalog URLs |
| `产品图片` | Upload all relevant customer product images plus product photos from each matching cited competitor listing. Name competitor attachments with their source label; reject logos, ads, and different variants. Keep local customer images outside the Skill repository. | Customer screenshot + `competitor_ZetWind_790482_….webp` |
| `同行价格` | Only with currency, access date, condition, and retail/wholesale level; otherwise blank. Never treat a retail listing as Baijia wholesale. | Blank if no reliable comparable level |

The new row starts at `项目阶段=信息收集` and `开发类型=贸易型`. `供应商`, `厂家编号`, `成本`, `计划售价`, `CXA编号`, and order fields remain outside this writer. A technical manufacturer's part number belongs in `外部参考编号` until its role as a factory number is separately established.

The Base URLs can be overridden by `CARAIR_DEVELOPMENT_BASE_URL` and `CARAIR_PEERS_BASE_URL`. The script checks field names and the category option live before a write.
