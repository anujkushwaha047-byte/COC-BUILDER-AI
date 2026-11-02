"""OCR-backed, conservative extraction of visible village HUD information."""

import os
import re
import shutil
from pathlib import Path
from typing import Iterable, List, Optional

from .farming import LootOpportunity
from .models import Observation, Reading

RESOURCE_NAMES = ("gold", "elixir", "dark_elixir", "gems")
NUMBER_RE = re.compile(r"^\d[\d,.]*(?:\s*[KMB])?$", re.IGNORECASE)
TIMER_RE = re.compile(r"(?:(\d+)\s*d\s*)?(?:(\d+)\s*h\s*)?(?:(\d+)\s*m\s*)?(?:(\d+)\s*s)?", re.IGNORECASE)


def _read_words(frame) -> List[dict]:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("OpenCV dependency missing; install requirements.txt.") from exc
    try:
        import pytesseract
        from pytesseract import Output
    except ImportError as exc:
        raise RuntimeError("OCR dependency missing; install requirements.txt.") from exc

    if not shutil.which(pytesseract.pytesseract.tesseract_cmd):
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        installed_tesseract = Path(program_files) / "Tesseract-OCR" / "tesseract.exe"
        if installed_tesseract.is_file():
            pytesseract.pytesseract.tesseract_cmd = str(installed_tesseract)

    try:
        raw = pytesseract.image_to_data(
            cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY),
            output_type=Output.DICT,
            config="--psm 11",
        )
    except pytesseract.pytesseract.TesseractNotFoundError as exc:
        raise RuntimeError(
            "Tesseract OCR was not found. Install Tesseract OCR and add it to PATH."
        ) from exc

    words = []
    for i, text in enumerate(raw["text"]):
        text = text.strip()
        try:
            confidence = float(raw["conf"][i]) / 100
        except (ValueError, TypeError):
            continue
        if text and confidence >= 0:
            words.append({
                "text": text,
                "confidence": max(0.0, min(1.0, confidence)),
                "x": int(raw["left"][i]),
                "y": int(raw["top"][i]),
                "width": int(raw["width"][i]),
                "height": int(raw["height"][i]),
            })
    return words


def _parse_amount(text: str) -> Optional[int]:
    normalized = text.replace(",", "").replace(" ", "").upper()
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([KMB]?)", normalized)
    if not match:
        return None
    multiplier = {"": 1, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[match.group(2)]
    return int(float(match.group(1)) * multiplier)


def _numeric_words(words: Iterable[dict], width: int, height: int) -> List[dict]:
    return [
        word for word in words
        if word["y"] < height * 0.22
        and word["x"] > width * 0.40
        and NUMBER_RE.fullmatch(word["text"].replace(",", ""))
    ]


def _extract_resources(words: List[dict], observation: Observation) -> None:
    candidates = sorted(
        _numeric_words(words, observation.screen_width, observation.screen_height),
        key=lambda word: word["x"],
    )
    if len(candidates) != len(RESOURCE_NAMES):
        observation.notes.append(
            "Resource totals are uncertain: the four resource values could not be isolated confidently."
        )
        return
    for name, word in zip(RESOURCE_NAMES, candidates):
        value = _parse_amount(word["text"])
        if value is not None:
            observation.resources[name] = Reading(value, word["confidence"], "top HUD OCR order")


def _extract_builders(words: List[dict], observation: Observation) -> None:
    for index, word in enumerate(words):
        if "builder" not in word["text"].lower():
            continue
        nearby = sorted(
            (candidate for candidate in words if abs(candidate["y"] - word["y"]) < 90),
            key=lambda candidate: abs(candidate["x"] - word["x"]),
        )
        for candidate in nearby:
            match = re.search(r"(\d+)\s*/\s*(\d+)", candidate["text"])
            if match:
                observation.builders_available = Reading(int(match.group(1)), candidate["confidence"], "builder HUD OCR")
                observation.builders_total = Reading(int(match.group(2)), candidate["confidence"], "builder HUD OCR")
                return


def _extract_town_hall(words: List[dict], observation: Observation) -> None:
    for index, word in enumerate(words):
        if "town" in word["text"].lower() or word["text"].lower() in {"th", "hall"}:
            neighborhood = words[max(0, index - 3):index + 5]
            for candidate in neighborhood:
                match = re.search(r"(?:level\s*)?(\d{1,2})", candidate["text"].lower())
                if match and 1 <= int(match.group(1)) <= 18:
                    observation.town_hall_level = Reading(int(match.group(1)), candidate["confidence"], "Town Hall label OCR")
                    return


def _extract_timers(words: List[dict], observation: Observation) -> None:
    for word in words:
        text = word["text"].strip().lower()
        if not re.fullmatch(r"\d+[dhms](?:\d+[dhms])*", text):
            continue
        match = TIMER_RE.fullmatch(text)
        if not match:
            continue
        days, hours, minutes, seconds = (int(value or 0) for value in match.groups())
        remaining = days * 86400 + hours * 3600 + minutes * 60 + seconds
        if remaining:
            observation.active_upgrades.append({
                "remaining_seconds": remaining,
                "confidence": word["confidence"],
                "source": "visible timer OCR",
            })


def observe_frame(frame, width: int, height: int) -> Observation:
    observation = Observation.empty(width, height)
    try:
        words = _read_words(frame)
    except RuntimeError as exc:
        observation.notes.append(str(exc))
        return observation
    observation.ocr_available = True
    _extract_resources(words, observation)
    _extract_builders(words, observation)
    _extract_town_hall(words, observation)
    _extract_timers(words, observation)
    if not observation.buildings:
        observation.notes.append(
            "Building identities and levels are not reliably legible on this screen; no buildings were guessed."
        )
    observation.notes.append(
        "Obstacle and collection-indicator recognition is unavailable without a validated game-specific vision model."
    )
    return observation


def observe_loot_screenshot(path: Path, village: str) -> LootOpportunity:
    """Read loot only when a resource label can be associated with an OCR number."""
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("OpenCV dependency missing; install requirements.txt.") from exc
    image = cv2.imread(str(path))
    if image is None:
        raise RuntimeError("The selected file is not a readable image.")
    frame = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    words = _read_words(frame)
    labels = {
        "gold": {"gold"},
        "elixir": {"elixir"},
        "dark_elixir": {"dark", "elixir"},
    }
    values = {"gold": None, "elixir": None, "dark_elixir": None}
    confidences = {}
    for resource, aliases in labels.items():
        candidates = [
            word for word in words
            if word["text"].lower().strip(":") in aliases
            and (resource != "dark_elixir" or "dark" in word["text"].lower())
        ]
        if resource == "dark_elixir":
            candidates = [
                word for word in words
                if word["text"].lower().strip(":") == "dark"
                and any(
                    other["text"].lower().strip(":") == "elixir"
                    and abs(other["y"] - word["y"]) < 40
                    for other in words
                )
            ]
        for label in candidates:
            numbers = [
                word for word in words
                if NUMBER_RE.fullmatch(word["text"].replace(",", ""))
                and abs(word["x"] - label["x"]) <= frame.shape[1] * 0.2
                and abs(word["y"] - label["y"]) <= frame.shape[0] * 0.12
            ]
            if numbers:
                nearest = min(
                    numbers,
                    key=lambda word: abs(word["x"] - label["x"]) + abs(word["y"] - label["y"]),
                )
                value = _parse_amount(nearest["text"])
                if value is not None:
                    values[resource] = value
                    confidences[resource] = min(label["confidence"], nearest["confidence"])
                    break
    known_confidences = list(confidences.values())
    return LootOpportunity(
        village=village,
        gold=values["gold"],
        elixir=values["elixir"],
        dark_elixir=values["dark_elixir"],
        confidence=min(known_confidences) if known_confidences else 0.0,
        source="local screenshot OCR; resource labels required",
        resource_confidence=confidences,
    )
