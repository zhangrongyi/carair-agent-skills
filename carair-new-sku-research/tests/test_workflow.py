import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE = Path(__file__).parents[1] / "scripts" / "workflow.py"
spec = importlib.util.spec_from_file_location("workflow", MODULE)
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)


def draft(image, decision="new"):
    data = {
        "decision": decision,
        "reviewed_product_codes": [],
        "reviewed_development_record_ids": [],
        "unresolved": [],
        "image_paths": [str(image)],
        "source_images": [],
        "source_image_gap_reason": "Fixture: no comparable competitor image",
        "fields": {
            "外部参考编号": "ZETWIND 790482; DENSO DCP51012",
            "品牌": "TOYOTA",
            "车型": "CAMRY",
            "类目": "COMPRESSOR",
            "产品描述": "COMPRESSOR TOYOTA CAMRY 2.5 HYBRID ES27 DCP51012",
            "采购说明": "客户提出需求；ZetWind 790482 页面所示产品",
            "核对来源链接": "https://example.com/part/790482",
        },
    }
    if decision == "update":
        data["record_id"] = "rec123ABC"
    return data


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
        self.assertEqual(workflow.reference_queries("ZETWIND 790482; DENSO DCP51012; ND 042200-0460"),
                         ["ZETWIND 790482", "790482", "DENSO DCP51012", "DCP51012", "ND 042200-0460", "042200-0460"])

    def test_reference_and_model_find_existing_record(self):
        rows = [{"record_id": "rec123", "fields": {"外部参考编号": "DENSO DCP51012",
                 "车型": "CAMRY", "产品描述": "COMPRESSOR", "品牌": "TOYOTA"}}]
        result = workflow.candidate_records(rows, "ZETWIND 790482; DENSO DCP51012", "TOYOTA CAMRY")
        self.assertEqual(result[0]["record_id"], "rec123")
        self.assertTrue(result[0]["exact_reference"])

    def test_pending_fitment_is_written_to_procurement_notes(self):
        data = draft(self.image)
        data["unresolved"] = ["客户实车 VIN 未收到", "旧件插头待核对"]
        proposed = workflow.validate_draft(data)
        self.assertIn("客户实车 VIN 未收到", proposed["采购说明"])
        self.assertEqual(proposed["项目阶段"], ["信息收集"])
        self.assertNotIn("待人工核对", data["fields"]["采购说明"])

    def test_missing_image_or_procurement_note_blocks_write(self):
        data = draft(self.image)
        data["image_paths"] = []
        with self.assertRaises(workflow.WorkflowError):
            workflow.validate_draft(data)
        data = draft(self.image)
        data["source_image_gap_reason"] = ""
        with self.assertRaises(workflow.WorkflowError):
            workflow.validate_draft(data)
        data = draft(self.image)
        del data["fields"]["采购说明"]
        with self.assertRaises(workflow.WorkflowError):
            workflow.validate_draft(data)

    def test_forbidden_fields_cannot_be_written(self):
        data = draft(self.image)
        data["fields"]["成本"] = "1"
        with self.assertRaises(workflow.WorkflowError):
            workflow.validate_draft(data)

    def test_request_context_must_not_be_product_title(self):
        data = draft(self.image)
        data["fields"]["产品描述"] = "客户指定 ZetWind 页面所示压缩机"
        with self.assertRaisesRegex(workflow.WorkflowError, "产品描述"):
            workflow.validate_draft(data)

    def test_competitor_image_requires_cited_product_page(self):
        data = draft(self.image)
        data["source_images"] = [{"label": "ZetWind 790482", "page_url": "https://other.example/part",
                                  "image_url": "https://cdn.example/part.jpg"}]
        with self.assertRaisesRegex(workflow.WorkflowError, "核对来源链接"):
            workflow.validate_draft(data)

    def test_competitor_image_url_cannot_target_local_machine(self):
        with self.assertRaisesRegex(workflow.WorkflowError, "non-public|public host"):
            workflow.public_https_url("https://127.0.0.1/private.jpg")
        with self.assertRaisesRegex(workflow.WorkflowError, "public HTTPS"):
            workflow.public_https_url("http://cdn.example/part.jpg")

    def test_missing_lark_cli_stops_before_api_call(self):
        with patch.object(workflow.shutil, "which", return_value=None), patch.object(workflow, "run_json") as run_json:
            with self.assertRaisesRegex(workflow.WorkflowError, "lark-cli is not installed"):
                workflow.lark("+field-list")
            run_json.assert_not_called()

    def test_lark_permission_error_is_reported(self):
        result = type("Result", (), {"stdout": json.dumps({"ok": False, "error": {"message": "permission denied"}}), "returncode": 1})()
        with patch.object(workflow.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(workflow.WorkflowError, "permission denied"):
                workflow.run_json(["lark-cli", "base", "+field-list"])

    def test_competitor_image_download_precedes_record_write(self):
        data = draft(self.image)
        data["source_images"] = [{"label": "ZetWind 790482", "page_url": "https://example.com/part/790482",
                                  "image_url": "https://cdn.example/part.jpg"}]
        path = self.save(data)
        fresh = {"product_queries": [], "development_candidates": []}
        with patch.object(workflow, "require_fields", return_value={"产品图片": {"type": "attachment"}}), \
             patch.object(workflow, "check_category_option"), \
             patch.object(workflow, "inspect", return_value=fresh), \
             patch.object(workflow, "download_source_images", side_effect=workflow.WorkflowError("image unavailable")), \
             patch.object(workflow, "lark") as lark:
            with self.assertRaisesRegex(workflow.WorkflowError, "image unavailable"):
                workflow.apply(path)
            lark.assert_not_called()

    def test_update_does_not_reset_stage(self):
        proposed = workflow.validate_draft(draft(self.image, "update"))
        self.assertNotIn("项目阶段", proposed)
        self.assertNotIn("开发类型", proposed)

    def test_duplicate_recheck_blocks_write(self):
        path = self.save(draft(self.image))
        fresh = {"product_queries": [], "development_candidates": [{"record_id": "recDUP", "exact_reference": True}]}
        with patch.object(workflow, "require_fields", return_value={"产品图片": {"type": "attachment"}}), \
             patch.object(workflow, "check_category_option"), \
             patch.object(workflow, "inspect", return_value=fresh), \
             patch.object(workflow, "lark") as lark:
            with self.assertRaises(workflow.WorkflowError):
                workflow.apply(path)
            lark.assert_not_called()

    def test_changed_product_results_block_write(self):
        path = self.save(draft(self.image))
        fresh = {"product_queries": [{"data": {"items": [{"product_code": "CXA-1"}]}}],
                 "development_candidates": []}
        with patch.object(workflow, "require_fields", return_value={"产品图片": {"type": "attachment"}}), \
             patch.object(workflow, "check_category_option"), \
             patch.object(workflow, "inspect", return_value=fresh), \
             patch.object(workflow, "lark") as lark:
            with self.assertRaises(workflow.WorkflowError):
                workflow.apply(path)
            lark.assert_not_called()

    def test_apply_writes_uploads_and_reads_back_before_human_review(self):
        data = draft(self.image)
        data["source_images"] = [{"label": "ZetWind 790482", "page_url": "https://example.com/part/790482",
                                  "image_url": "https://cdn.example/part.webp"}]
        competitor = Path(self.temp.name) / "competitor.webp"
        competitor.write_bytes(b"RIFF0000WEBP")
        path = self.save(data)
        proposed = workflow.validate_draft(data)
        fresh = {"product_queries": [], "development_candidates": []}
        def fake_lark(*args):
            if args[0] == "+record-upsert":
                return {"data": {"created": True, "record": {"record_id_list": ["recNEW"]}}}
            if args[0] == "+record-upload-attachment":
                self.assertIn(str(self.image), args)
                self.assertIn(str(competitor), args)
                return {"data": {"file_token_list": ["file123"]}}
            self.fail("Unexpected Lark call")
        output = io.StringIO()
        with patch.object(workflow, "require_fields", return_value={"产品图片": {"type": "attachment"}}), \
             patch.object(workflow, "check_category_option"), \
             patch.object(workflow, "inspect", return_value=fresh), \
             patch.object(workflow, "download_source_images", return_value=[str(competitor)]), \
             patch.object(workflow, "lark", side_effect=fake_lark), \
             patch.object(workflow, "readback", return_value={**proposed, "产品图片": [{"file_token": "file123"}, {"file_token": "file456"}], "记录ID": "KK-260111"}), \
             contextlib.redirect_stdout(output):
            workflow.apply(path)
        result = json.loads(output.getvalue())
        self.assertEqual(result["record_id"], "recNEW")
        self.assertEqual(result["image_count"], 2)
        self.assertEqual(result["competitor_images"][0]["label"], "ZetWind 790482")
        self.assertIn("human_review", result)

    def test_image_failure_reports_written_record_without_retry(self):
        path = self.save(draft(self.image))
        fresh = {"product_queries": [], "development_candidates": []}
        calls = []
        def fake_lark(*args):
            calls.append(args[0])
            if args[0] == "+record-upsert":
                return {"data": {"record": {"record_id_list": ["recNEW"]}}}
            raise workflow.WorkflowError("upload unavailable")
        with patch.object(workflow, "require_fields", return_value={"产品图片": {"type": "attachment"}}), \
             patch.object(workflow, "check_category_option"), \
             patch.object(workflow, "inspect", return_value=fresh), \
             patch.object(workflow, "lark", side_effect=fake_lark):
            with self.assertRaisesRegex(workflow.WorkflowError, "Record recNEW was written"):
                workflow.apply(path)
        self.assertEqual(calls, ["+record-upsert", "+record-upload-attachment"])


if __name__ == "__main__":
    unittest.main()
