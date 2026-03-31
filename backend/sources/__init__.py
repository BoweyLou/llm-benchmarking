"""Source adapters for benchmark ingestion."""

from .ailuminate import AILuminateAdapter
from .artificial_analysis import ArtificialAnalysisAdapter
from .chatbot_arena import ChatbotArenaAdapter
from .epoch_gpqa import EpochGpqaAdapter
from .ifeval import IfevalAdapter
from .mmmu import MmmuAdapter
from .swebench import SwebenchAdapter
from .terminal_bench import TerminalBenchAdapter


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


def get_phase_two_adapters():
    return [
        TerminalBenchAdapter(),
    ]


def get_source_adapters(*, include_phase_two: bool = False):
    adapters = get_phase_one_adapters()
    if include_phase_two:
        adapters.extend(get_phase_two_adapters())
    return adapters


__all__ = [
    "AILuminateAdapter",
    "ArtificialAnalysisAdapter",
    "ChatbotArenaAdapter",
    "EpochGpqaAdapter",
    "IfevalAdapter",
    "MmmuAdapter",
    "TerminalBenchAdapter",
    "SwebenchAdapter",
    "get_phase_one_adapters",
    "get_phase_two_adapters",
    "get_source_adapters",
]
