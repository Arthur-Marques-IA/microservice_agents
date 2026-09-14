from agent_service.memory.base import MemoryBackend
from agent_service.memory.common import CommonMemoryBackend
from agent_service.memory.mem0_backend import Mem0MemoryBackend

__all__ = ["MemoryBackend", "CommonMemoryBackend", "Mem0MemoryBackend", "get_memory_backend"]


def get_memory_backend(name: str = "common") -> MemoryBackend:
    if name == "common":
        return CommonMemoryBackend()
    if name == "mem0":
        return Mem0MemoryBackend()
    raise ValueError(f"Backend de memória desconhecido: {name!r}")
