"""Source adapters for benchmark ingestion."""

from .ailuminate import AILuminateAdapter
from .artificial_analysis import ArtificialAnalysisAdapter
from .chatbot_arena import ChatbotArenaAdapter
from .epoch_gpqa import EpochGpqaAdapter
from .ifeval import IfevalAdapter
from .mmmu import MmmuAdapter
from .swebench import SwebenchAdapter


def get_phase_one_adapters():
    return [
        ArtificialAnalysisAdapter(),
        AILuminateAdapter(),
        ChatbotArenaAdapter(),
        EpochGpqaAdapter(),
        IfevalAdapter(),
        MmmuAdapter(),
        SwebenchAdapter(),
    ]


__all__ = [
    "AILuminateAdapter",
    "ArtificialAnalysisAdapter",
    "ChatbotArenaAdapter",
    "EpochGpqaAdapter",
    "IfevalAdapter",
    "MmmuAdapter",
    "SwebenchAdapter",
    "get_phase_one_adapters",
]
