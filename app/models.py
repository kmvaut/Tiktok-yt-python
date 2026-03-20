from dataclasses import dataclass
from pathlib import Path


@dataclass
class VideoVariant:
    topic: str
    hook: str
    promise: str
    points: list[str]
    payoff: str
    cta: str
    full_script: str
    title: str
    description: str
    hashtags: list[str]
    score: float
    score_details: dict
    variant_id: str
    output_dir: Path