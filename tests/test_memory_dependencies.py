def test_memory_dependency_invalidation_and_protected_cleanup():
    from core.memory.index import MemoryDependencyIndex
    index = MemoryDependencyIndex()
    index.add("m1", ["e1", "commit-1"])
    assert index.invalidate_source("e1") == ["m1"]
    assert index.can_delete_source("e1", protected_memory_ids={"m1"}) is False
    assert index.can_delete_source("e2", protected_memory_ids=set()) is True
