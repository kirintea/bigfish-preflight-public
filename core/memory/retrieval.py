from .schemas import MemoryEntry, MemorySearchResult


class MemoryIndex:
    def __init__(self, entries):
        self.entries = [entry if isinstance(entry, MemoryEntry) else MemoryEntry(**entry) for entry in entries]

    def search(self, *, world_id, npc_id, query="", valid_sources=None, limit=20):
        terms = [term.lower() for term in query.split() if term]
        valid_sources = set(valid_sources or [])
        included, excluded = [], {}
        for entry in self.entries:
            if entry.world_id != world_id:
                excluded["world"] = excluded.get("world", 0) + 1; continue
            if entry.owner_npc_id != npc_id:
                excluded["owner"] = excluded.get("owner", 0) + 1; continue
            if entry.access_state == "inaccessible":
                excluded["access"] = excluded.get("access", 0) + 1; continue
            if not entry.valid or (valid_sources and not set(entry.source_event_ids) <= valid_sources):
                excluded["source"] = excluded.get("source", 0) + 1; continue
            score = sum(entry.content.lower().count(term) for term in terms) + entry.importance
            if terms and score <= entry.importance:
                excluded["query"] = excluded.get("query", 0) + 1; continue
            included.append((score, entry))
        included.sort(key=lambda pair: (-pair[0], pair[1].memory_id))
        return MemorySearchResult([entry for _, entry in included[:limit]], excluded)
