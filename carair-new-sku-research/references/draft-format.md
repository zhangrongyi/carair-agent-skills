# Company development draft

Save one UTF-8 JSON file **outside Git**. Generate `request_key` once per intended write (for example a UUID) and keep it unchanged on retry. `reviewed_product_codes` and `reviewed_development_record_ids` are the exact candidate IDs returned by `inspect`; `record_id` and `record_version` for update are numeric company project values returned by `inspect`.

```json
{
  "decision": "new",
  "request_key": "e2aa377e-4ef6-4968-a573-c7187ec6c14d",
  "reviewed_product_codes": [],
  "reviewed_development_record_ids": [],
  "own_product_difference": "",
  "development_record_difference": "",
  "unresolved": ["客户实车 VIN 与旧件插头待核对"],
  "image_paths": ["/absolute/local/path/customer-product.jpg"],
  "source_images": [{
    "label": "ZetWind 790482",
    "page_url": "https://www.zetwind.com.my/showproducts/productid/3058431/cid/206206/code790482-toyota-camry-2015-25-es27c-hybridnd-0422000460dcp51012/",
    "image_url": "https://example.com/direct-product-image.webp"
  }],
  "peer_currency": "",
  "peer_price_level": "",
  "fields": {
    "外部参考编号": "ZETWIND 790482; DENSO DCP51012",
    "品牌": "TOYOTA",
    "车型": "CAMRY",
    "年份": "2015（ZetWind 页面）",
    "类目": "COMPRESSOR",
    "产品描述": "COMPRESSOR TOYOTA CAMRY 2.5 HYBRID ES27 DCP51012",
    "采购说明": "TH LONG 找；客户实车待核对。",
    "车款信息说明": "Denso 目录关联 Camry 2.5 Hybrid 与 DCP51012；插头与安装脚待比对。",
    "核对来源链接": "https://www.zetwind.com.my/showproducts/productid/3058431/cid/206206/code790482-toyota-camry-2015-25-es27c-hybridnd-0422000460dcp51012/"
  }
}
```

The direct image URL above is a format placeholder: obtain a current URL from the cited product page. `source_images` may be empty only with a specific `source_image_gap_reason`; at least one customer or competitor product image is required for a new project. A competitor image's `page_url` must appear in `核对来源链接`. For a near match, explain differences in the corresponding difference field. For an existing exact reference, use `decision: update`, `record_id`, and `record_version`; preserve verified project fields. If `同行价格` is filled, add currency and retail/wholesale level.

The first write only records research. The employee reviews the project in the company admin system and advances it separately. If the final API response is ambiguous, rerun with the **same** request key; the server returns the original project rather than creating another.
