"""Tests for ID generation (Phase 1)."""

from vsrs.core.ids import (
    generate_evidence_id,
    generate_finding_id,
    generate_hypothesis_id,
    generate_id,
    generate_patch_id,
    generate_provenance_id,
    generate_run_id,
    generate_task_id,
    generate_verification_id,
)


class TestIDGeneration:
    def test_generate_id_with_prefix(self):
        uid = generate_id("test")
        assert uid.startswith("test_")
        assert len(uid) > len("test_")

    def test_generate_id_without_prefix(self):
        uid = generate_id()
        assert "_" in uid

    def test_uniqueness(self):
        ids = {generate_id("x") for _ in range(100)}
        assert len(ids) == 100

    def test_run_id(self):
        uid = generate_run_id()
        assert uid.startswith("run_")

    def test_task_id(self):
        uid = generate_task_id()
        assert uid.startswith("task_")

    def test_evidence_id(self):
        uid = generate_evidence_id()
        assert uid.startswith("ev_")

    def test_patch_id(self):
        uid = generate_patch_id()
        assert uid.startswith("patch_")

    def test_verification_id(self):
        uid = generate_verification_id()
        assert uid.startswith("verify_")

    def test_hypothesis_id(self):
        uid = generate_hypothesis_id()
        assert uid.startswith("hyp_")

    def test_provenance_id(self):
        uid = generate_provenance_id()
        assert uid.startswith("prov_")

    def test_finding_id(self):
        uid = generate_finding_id()
        assert uid.startswith("finding_")
