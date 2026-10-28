from dataclasses import dataclass, field
from uuid import UUID


@dataclass
class CopyProjectInput:
    project_id: UUID
    user_id: UUID


@dataclass
class CopyProjectOutput:
    project_id: UUID
    order_ids: list[UUID] = field(default_factory=list)
