class MemoryDependencyIndex:
    def __init__(self):
        self._refs = {}

    def add(self, memory_id, references):
        for reference in references:
            self._refs.setdefault(reference, set()).add(memory_id)

    def invalidate_source(self, reference):
        return sorted(self._refs.get(reference, set()))

    def can_delete_source(self, reference, *, protected_memory_ids):
        return not (self._refs.get(reference, set()) & set(protected_memory_ids))
