import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("workflow", SCRIPTS / "workflow.py")
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)


def draft(image):
    return {
        "decision": "new", "request_key": "test-request-12345678",
        "reviewed_product_codes": [], "reviewed_development_record_ids": [],
        "unresolved": ["VIN 待核对"], "image_paths": [str(image)], "source_images": [],
        "source_image_gap_reason": "测试无同行图片",
        "fields": {"外部参考编号": "ZETWIND 790482", "品牌": "TOYOTA", "车型": "CAMRY", "类目": "COMPRESSOR",
                   "产品描述": "COMPRESSOR TOYOTA CAMRY 790482", "采购说明": "客户询问；适配待确认",
                   "核对来源链接": "https://example.com/part/790482"},
    }


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.image = Path(self.temp.name) / "customer.jpg"
        self.image.write_bytes(b"\xff\xd8\xff\xd9")

    def save(self, data):
        path = Path(self.temp.name) / "draft.json"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    def test_reference_numbers_are_searched_separately(self):
        self.assertEqual(workflow.reference_queries("ZETWIND 790482; DENSO DCP51012"),
                         ["ZETWIND 790482", "790482", "DENSO DCP51012", "DCP51012"])

    def test_product_search_reads_all_candidates(self):
        first={"ok":True,"data":{"total":21,"items":[{"product_code":str(i)} for i in range(20)]}}
        second={"ok":True,"data":{"total":21,"items":[{"product_code":"20"}]}}
        with patch.object(workflow,"product_client",return_value=Path("/tmp/query.py")),patch.object(workflow,"run_json",side_effect=[first,second]) as run:
            found=workflow.product_search(["790482"])
        self.assertEqual(len(found[0]["data"]["items"]),21)
        self.assertEqual(run.call_count,2)

    def test_inspect_requires_both_internal_sources(self):
        with patch.object(workflow, "product_search", return_value=[{"query":"790482"}]), \
             patch.object(workflow.development_api, "call", return_value={"development_candidates":[],"peer_sources":[]}):
            data = workflow.inspect("790482", "CAMRY", "COMPRESSOR")
            self.assertIn("product_queries", data)
            self.assertIn("peer_sources", data)
        with patch.object(workflow, "product_search", side_effect=workflow.WorkflowError("product API failed")), \
             patch.object(workflow.development_api, "call") as api:
            with self.assertRaisesRegex(workflow.WorkflowError, "product API failed"):
                workflow.inspect("790482", "CAMRY", "COMPRESSOR")
            api.assert_not_called()

    def test_validation_requires_key_image_and_source(self):
        data = draft(self.image)
        self.assertEqual(workflow.validate_draft(data), ["https://example.com/part/790482"])
        for change in (lambda d:d.pop("request_key"), lambda d:d.update(image_paths=[]),
                       lambda d:d["fields"].pop("采购说明"), lambda d:d["fields"].update({"成本":"1"})):
            d = draft(self.image); change(d)
            with self.assertRaises(workflow.WorkflowError): workflow.validate_draft(d)

    def test_cited_competitor_image_required(self):
        data = draft(self.image)
        data["source_images"] = [{"label":"peer","page_url":"https://other.example/part","image_url":"https://cdn.example/part.jpg"}]
        with self.assertRaises(workflow.WorkflowError): workflow.validate_draft(data)
        with self.assertRaises(workflow.WorkflowError): workflow.public_https_url("https://127.0.0.1/private.jpg")

    def test_exact_duplicate_stops_before_upload(self):
        path = self.save(draft(self.image))
        fresh = {"reviewed_product_codes":[],"development_candidates":[{"id":7,"exact_reference":True}]}
        with patch.object(workflow, "inspect", return_value=fresh), patch.object(workflow.development_api,"call",return_value={}) as api:
            with self.assertRaises(workflow.WorkflowError): workflow.apply(path)
            self.assertEqual(api.call_count,1)

    def test_changed_candidates_stop_before_upload(self):
        path = self.save(draft(self.image))
        fresh = {"reviewed_product_codes":["CXA-1"],"development_candidates":[]}
        with patch.object(workflow, "inspect", return_value=fresh), patch.object(workflow.development_api,"call",return_value={}) as api:
            with self.assertRaises(workflow.WorkflowError): workflow.apply(path)
            self.assertEqual(api.call_count,1)

    def test_apply_uploads_then_posts_idempotent_draft(self):
        path = self.save(draft(self.image))
        fresh = {"reviewed_product_codes":[],"development_candidates":[]}
        calls=[]
        def fake_call(method, endpoint, **kwargs):
            calls.append(endpoint)
            if endpoint=="result": return {}
            if endpoint=="uploads": return {"upload_token":"staged123"}
            if endpoint=="drafts":
                self.assertEqual(kwargs["payload"]["request_key"],"test-request-12345678")
                self.assertEqual(kwargs["payload"]["upload_tokens"],["staged123"])
                return {"id":42,"replayed":False}
            self.fail(endpoint)
        out=io.StringIO()
        with patch.object(workflow,"inspect",return_value=fresh),patch.object(workflow.development_api,"call",side_effect=fake_call), \
             patch.object(workflow.development_api,"base_url",return_value="https://example.com"),contextlib.redirect_stdout(out):
            workflow.apply(path)
        self.assertEqual(calls,["result","uploads","drafts"])
        self.assertEqual(json.loads(out.getvalue())["record_id"],42)

    def test_ambiguous_write_uses_request_key_result(self):
        path=self.save(draft(self.image))
        fresh={"reviewed_product_codes":[],"development_candidates":[]}
        result_calls=0
        def fake_call(method,endpoint,**kwargs):
            nonlocal result_calls
            if endpoint=="uploads":return {"upload_token":"temp"}
            if endpoint=="drafts":raise RuntimeError("connection lost")
            if endpoint=="result":
                result_calls+=1
                return {} if result_calls==1 else {"project_id":42}
            self.fail(endpoint)
        out=io.StringIO()
        with patch.object(workflow,"inspect",return_value=fresh),patch.object(workflow.development_api,"call",side_effect=fake_call), \
             patch.object(workflow.development_api,"base_url",return_value="https://example.com"),contextlib.redirect_stdout(out):
            workflow.apply(path)
        self.assertEqual(json.loads(out.getvalue())["record_id"],42)

    def test_retry_checks_result_before_inspect_or_upload(self):
        path=self.save(draft(self.image))
        with patch.object(workflow,"inspect") as inspect, patch.object(workflow.development_api,"call",return_value={"project_id":42}) as api, \
             patch.object(workflow.development_api,"base_url",return_value="https://example.com"),contextlib.redirect_stdout(io.StringIO()):
            workflow.apply(path)
            inspect.assert_not_called()
            api.assert_called_once()

if __name__=="__main__":unittest.main()
