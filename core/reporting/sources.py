from dataclasses import dataclass, field

from fastapi import HTTPException

from .registry import DOMAINS


@dataclass(frozen=True)
class Source:
    kind: str
    source_id: str
    namespace: str
    world_ids: frozenset[str]
    domains: frozenset[str] = field(default_factory=lambda: frozenset(DOMAINS))

    def permits(self, report):
        return (report.source_kind == self.kind and report.source_id == self.source_id
                and report.world_id in self.world_ids and report.domain in self.domains)


def simulation_source(principal, config, world_id, source_id):
    if (principal.role != "simulator" or world_id not in principal.world_ids
            or source_id not in principal.source_ids):
        raise HTTPException(403, "forbidden_source")
    return Source("simulation", source_id, "production", principal.world_ids, config.simulator_domains)
