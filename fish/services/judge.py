"""Judge — the statistical prosecutor.

Judge never trades. Judge's only purpose is to destroy strategies.

THIS IS NOW A RE-EXPORT FROM judge_v2.py.
There is only one Judge. Use it directly:
    from fish.services.judge_v2 import judge_strategy, JudgeVerdict
"""
from fish.services.judge_v2 import judge_strategy, JudgeVerdict, JudgeMetrics

__all__ = ["judge_strategy", "JudgeVerdict", "JudgeMetrics"]
