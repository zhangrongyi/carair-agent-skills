# Direct-write draft for post-write review

Save one UTF-8 JSON file outside the Git repository. `image_paths` lists existing local customer-supplied JPG, PNG, WebP, or GIF files; use `[]` only when the customer supplied no product image. `source_images` lists the matching competitor product photos to download from public HTTPS URLs. Each item needs a human-readable `label`, the cited `page_url`, and the direct `image_url`. The script downloads and validates these images before writing, then uploads customer and competitor images to `产品图片` together. Keep product-page provenance in `核对来源链接` and the post-write report. The source image URL itself is not a fitment reference.

`reviewed_product_codes` and `reviewed_development_record_ids` list all candidates returned by `inspect`; empty arrays mean there were no candidates. When creating despite near matches, explain their technical differences in `own_product_difference` and `development_record_difference`. An exact external reference in an existing development row blocks a new row; use `decision: update` with that row's ID. Keep verified existing fields when updating.

```json
{
  "decision": "new",
  "reviewed_product_codes": [],
  "reviewed_development_record_ids": [],
  "unresolved": ["客户实车 VIN 与旧件插头待核对"],
  "image_paths": ["/absolute/local/path/customer-product.jpg"],
  "source_images": [
    {
      "label": "ZetWind 790482",
      "page_url": "https://www.zetwind.com.my/showproducts/productid/3058431/cid/206206/code790482-toyota-camry-2015-25-es27c-hybridnd-0422000460dcp51012/",
      "image_url": "https://cdn1.npcdn.net/images/159591809751dbda1ab8d6769fa76b7543427161b6.webp?from=jpg&md5id=fea68355a2b250eb95468fb15c087d8c&new_height=1000&new_width=1000&size=max&type=9&w=1532934371"
    }
  ],
  "fields": {
    "外部参考编号": "ZETWIND 790482; DENSO DCP51012; ND 042200-0460",
    "品牌": "TOYOTA",
    "车型": "CAMRY",
    "年份": "2015（ZetWind 页面）",
    "类目": "COMPRESSOR",
    "产品描述": "COMPRESSOR TOYOTA CAMRY 2.5 HYBRID ES27 DCP51012",
    "采购说明": "客户提出此需求；ZetWind 790482 页面标注 ES27C、ND 042200-0460；客户实车待核对。",
    "车款信息说明": "Denso 目录将 Camry 2.5 Hybrid 2AR-FXE 与 DCP51012、Toyota OE 88370-33020 关联；页面 ES27C 与目录 ES27 的称呼有差异。",
    "核对来源链接": "https://www.zetwind.com.my/showproducts/productid/3058431/cid/206206/code790482-toyota-camry-2015-25-es27c-hybridnd-0422000460dcp51012/\nhttps://www.denso-technic.com/images/e-catalogues/a-c-components-catalogue-2016-2017.pdf"
  }
}
```

This is a format example, not an instruction to write that item. Obtain current direct image URLs from the actual product page; CDN links can expire. Use at least one useful product image per cited matching competitor listing when available, and include distinct angles when relevant. If no comparable competitor image is available, use `"source_images": []` and give a specific `source_image_gap_reason`; a customer image must still be present. At least one image overall is required. Run `apply` only after the automated research and internal candidate review are complete. `unresolved` may be nonempty for a new information-collection row; the script appends those items to `采购说明` so post-write reviewers see them. This does not establish customer-vehicle fitment or authorize procurement.

The script sets `项目阶段=信息收集` and `开发类型=贸易型` for new rows. Never place unknown supplier, factory number, cost, planned selling price, internal SKU, or order values in the draft. Customer identity is allowed in `采购说明` because it is the demand source; omit contacts, private chat text, and other unnecessary personal data.

After `apply`, check its returned record link, customer image count, competitor image sources, and total attachment count. Ask the employee to review the new row in Lark. If an upload or readback error follows a row write, inspect the returned record ID before any retry.
