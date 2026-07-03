"""Source adapters for benchmark ingestion."""

from .ailuminate import AILuminateAdapter
from .artificial_analysis import ArtificialAnalysisAdapter
from .artificial_analysis_ifbench import ArtificialAnalysisIfbenchAdapter
from .artificial_analysis_tts import ArtificialAnalysisTtsAdapter
from .bfcl import BfclAdapter
from .bigcodebench import BigCodeBenchAdapter
from .chatbot_arena import ChatbotArenaAdapter
from .epoch_gpqa import EpochGpqaAdapter
from .faithjudge import FaithJudgeAdapter
from .helm_capabilities import HelmCapabilitiesAdapter
from .ifeval import IfevalAdapter
from .livebench import LiveBenchAdapter
from .livecodebench import LiveCodeBenchAdapter
from .mmmu import MmmuAdapter
from .mteb import MtebAdapter
from .open_asr_leaderboard import OpenAsrLeaderboardAdapter
from .ragtruth import RagtruthAdapter
from .swebench import SwebenchAdapter
from .taubench import TaubenchAdapter
from .terminal_bench import TerminalBenchAdapter
from .vectara_hallucination import VectaraHallucinationAdapter


def get_phase_one_adapters():
    return [
        ArtificialAnalysisAdapter(),
        ArtificialAnalysisIfbenchAdapter(),
        ArtificialAnalysisTtsAdapter(),
        AILuminateAdapter(),
        BfclAdapter(),
        BigCodeBenchAdapter(),
        ChatbotArenaAdapter(),
        EpochGpqaAdapter(),
        FaithJudgeAdapter(),
        HelmCapabilitiesAdapter(),
        IfevalAdapter(),
        LiveBenchAdapter(),
        LiveCodeBenchAdapter(),
        MmmuAdapter(),
        MtebAdapter(),
        OpenAsrLeaderboardAdapter(),
        RagtruthAdapter(),
        SwebenchAdapter(),
        TaubenchAdapter(),
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
    "ArtificialAnalysisIfbenchAdapter",
    "ArtificialAnalysisTtsAdapter",
    "BfclAdapter",
    "BigCodeBenchAdapter",
    "ChatbotArenaAdapter",
    "EpochGpqaAdapter",
    "FaithJudgeAdapter",
    "HelmCapabilitiesAdapter",
    "IfevalAdapter",
    "LiveBenchAdapter",
    "LiveCodeBenchAdapter",
    "MmmuAdapter",
    "MtebAdapter",
    "OpenAsrLeaderboardAdapter",
    "RagtruthAdapter",
    "TerminalBenchAdapter",
    "TaubenchAdapter",
    "SwebenchAdapter",
    "VectaraHallucinationAdapter",
    "get_phase_one_adapters",
    "get_phase_two_adapters",
    "get_source_adapters",
]
