"""Veille — jumeau Python du socle C (vérification indépendante, stdlib uniquement)."""
__version__ = "0.1.0"
from .chain import ChainConfig, Priority, Stage
from .state import FaultState, SensorState, BusState, PrioMode, AlarmState
from .proof import FaultMask, proof_explore, explore
from .verdict import Verdict, VerdictCode, Severity
from .report import report_text, report_json, report_markdown, exit_code
