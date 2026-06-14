"""Unit tests for the staging store."""
from fhir_mcp.writes.staging import StagingStore, idempotency_hash


def test_stage_and_get():
    store = StagingStore()
    staged = store.stage("Observation", {"a": 1}, preview="p")
    assert store.get(staged.staged_id) is staged
    assert staged.staged_id.startswith("stg_")


def test_idempotent_staging():
    store = StagingStore()
    s1 = store.stage("Observation", {"a": 1}, preview="p")
    s2 = store.stage("Observation", {"a": 1}, preview="p")
    assert s1.staged_id == s2.staged_id  # same payload -> same staged write


def test_list_pending_excludes_committed():
    store = StagingStore()
    staged = store.stage("Observation", {"a": 1}, preview="p")
    assert len(store.list_pending()) == 1
    store.mark_committed(staged.staged_id, "Observation/123")
    assert store.list_pending() == []


def test_discard():
    store = StagingStore()
    staged = store.stage("Observation", {"a": 1}, preview="p")
    assert store.discard(staged.staged_id) is True
    assert store.get(staged.staged_id) is None
    assert store.discard("stg_nonexistent") is False


def test_idempotency_hash_ignores_key_order():
    h1 = idempotency_hash("Observation", {"a": 1, "b": 2})
    h2 = idempotency_hash("Observation", {"b": 2, "a": 1})
    assert h1 == h2
