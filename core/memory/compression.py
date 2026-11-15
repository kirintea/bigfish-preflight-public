from .schemas import CompressionCandidate


class CompressionService:
    def build_candidate(self, entries, *, target_version):
        facts, claims, interpretations, commitments, refs, ids = [], [], [], [], [], []
        for entry in entries:
            certainty = entry.get("certainty", "confirmed")
            content = entry["content"]
            (facts if certainty == "confirmed" else claims).append(content)
            refs.extend(entry.get("source_event_ids", [])); ids.append(entry["memory_id"])
            if "promised" in content.lower() or "commit" in content.lower():
                commitments.append(content)
        return CompressionCandidate(version=target_version, facts=facts, claims=claims,
            interpretations=interpretations, active_commitments=commitments,
            source_refs=sorted(set(refs)), source_memory_ids=ids)

    def validate(self, candidate, *, valid_sources):
        return set(candidate.source_refs) <= set(valid_sources) and bool(candidate.source_memory_ids)
