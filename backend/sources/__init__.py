"""Source adapters for benchmark ingestion."""

from .ailuminate import AILuminateAdapter
from .artificial_analysis import ArtificialAnalysisAdapter
from .chatbot_arena import ChatbotArenaAdapter
from .epoch_gpqa import EpochGpqaAdapter
from .faithjudge import FaithJudgeAdapter
from .helm_capabilities import HelmCapabilitiesAdapter
from .ifeval import IfevalAdapter
from .mmmu import MmmuAdapter
from .swebench import SwebenchAdapter
from .terminal_bench import TerminalBenchAdapter
from .vectara_hallucination import VectaraHallucinationAdapter


def get_phase_one_adapters():
    return [
        ArtificialAnalysisAdapter(),
        AILuminateAdapter(),
        ChatbotArenaAdapter(),
        EpochGpqaAdapter(),
        FaithJudgeAdapter(),
        HelmCapabilitiesAdapter(),
        IfevalAdapter(),
        MmmuAdapter(),
        SwebenchAdapter(),
        VectaraHallucinationAdapter(),
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
    "FaithJudgeAdapter",
    "HelmCapabilitiesAdapter",
    "IfevalAdapter",
    "MmmuAdapter",
    "TerminalBenchAdapter",
    "SwebenchAdapter",
    "VectaraHallucinationAdapter",
    "get_phase_one_adapters",
    "get_phase_two_adapters",
    "get_source_adapters",
]
