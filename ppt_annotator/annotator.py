from __future__ import annotations

import argparse
import gc
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(slots=True)
class AnnotatorConfig:
    input_ppt_path: Path
    file_selection: str
    context_prompt_helper: str
    temp_path: Path
    annotated_suffix: str


@dataclass(slots=True)
class SlideSnapshot:
    number: int
    title: str
    slide_text: str
    notes_text: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect PowerPoint speaker notes for the PPT annotator prototype."
    )
    parser.add_argument(
        "--env-file",
        default=Path(__file__).with_name(".env"),
        type=Path,
        help="Path to the annotator .env file.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List matching decks and exit.",
    )
    parser.add_argument(
        "--deck-index",
        type=int,
        help="1-based index of the deck to inspect.",
    )
    parser.add_argument(
        "--deck-path",
        type=Path,
        help="Explicit path to a deck to inspect or edit, bypassing deck-index selection.",
    )
    parser.add_argument(
        "--max-slides",
        type=int,
        default=5,
        help="Maximum number of slides to print during inspection.",
    )
    parser.add_argument(
        "--show-prompt",
        action="store_true",
        help="Print the drafted prompt payload for the first inspected slide.",
    )
    parser.add_argument(
        "--slide-number",
        type=int,
        help="1-based slide number to edit when writing notes.",
    )
    parser.add_argument(
        "--append-note",
        help="Append this text to the selected slide's notes in the resolved output deck.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Force the interactive menu loop even when other defaults would inspect directly.",
    )
    return parser.parse_args()


def load_env_file(env_file: Path) -> AnnotatorConfig:
    if not env_file.exists():
        raise FileNotFoundError(f"Config file not found: {env_file}")

    values: dict[str, str] = {}
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        value = raw_value.strip().strip('"').strip("'")
        values[key.strip()] = value

    required_keys = {
        "INPUT_PPT_PATH",
        "FILE_SELECTION",
        "CONTEXT_PROMPT_HELPER",
        "TEMP_PATH",
    }
    missing_keys = sorted(required_keys - values.keys())
    if missing_keys:
        raise ValueError(f"Missing required config keys: {', '.join(missing_keys)}")

    return AnnotatorConfig(
        input_ppt_path=Path(values["INPUT_PPT_PATH"]),
        file_selection=values["FILE_SELECTION"],
        context_prompt_helper=values["CONTEXT_PROMPT_HELPER"],
        temp_path=Path(values["TEMP_PATH"]),
        annotated_suffix=values.get("ANNOTATED_SUFFIX", "-Annotated"),
    )


def find_decks(config: AnnotatorConfig) -> list[Path]:
    if not config.input_ppt_path.exists():
        raise FileNotFoundError(f"Input path does not exist: {config.input_ppt_path}")
    return sorted(config.input_ppt_path.glob(config.file_selection))


def print_decks(decks: Iterable[Path]) -> None:
    for index, deck_path in enumerate(decks, start=1):
        print(f"[{index}] {deck_path.name}")


def choose_deck(decks: list[Path], deck_index: int | None) -> Path:
    if not decks:
        raise FileNotFoundError("No PowerPoint decks matched the configured search.")

    if deck_index is not None:
        if deck_index < 1 or deck_index > len(decks):
            raise IndexError(f"Deck index {deck_index} is out of range 1..{len(decks)}")
        return decks[deck_index - 1]

    if len(decks) == 1:
        return decks[0]

    print("Select a deck to inspect:")
    print_decks(decks)
    selection = input("Enter deck number: ").strip()
    if not selection.isdigit():
        raise ValueError("Deck selection must be a number.")

    selected_index = int(selection)
    if selected_index < 1 or selected_index > len(decks):
        raise IndexError(f"Deck index {selected_index} is out of range 1..{len(decks)}")

    return decks[selected_index - 1]


def resolve_selected_deck(args: argparse.Namespace, decks: list[Path]) -> Path:
    if args.deck_path is not None:
        if not args.deck_path.exists():
            raise FileNotFoundError(f"Deck path does not exist: {args.deck_path}")
        return args.deck_path
    return choose_deck(decks, args.deck_index)


def get_powerpoint_app():
    try:
        import pythoncom  # pyright: ignore[reportMissingImports]
        import win32com.client  # pyright: ignore[reportMissingImports]
    except ImportError as exc:
        raise RuntimeError(
            "pywin32 is not available. Install pywin32 in the active environment."
        ) from exc

    pythoncom.CoInitialize()
    app = win32com.client.DispatchEx("PowerPoint.Application")
    return app


def iter_slide_snapshots(presentation, max_slides: int) -> list[SlideSnapshot]:
    snapshots: list[SlideSnapshot] = []
    for slide_index in range(1, min(presentation.Slides.Count, max_slides) + 1):
        slide = presentation.Slides(slide_index)
        title = read_slide_title(slide)
        slide_text = read_slide_text(slide)
        notes_text = read_notes_text(slide)
        snapshots.append(
            SlideSnapshot(
                number=slide_index,
                title=title,
                slide_text=slide_text,
                notes_text=notes_text,
            )
        )
    return snapshots


def read_slide_title(slide) -> str:
    try:
        title_shape = slide.Shapes.Title
        if title_shape and title_shape.HasTextFrame and title_shape.TextFrame.HasText:
            return title_shape.TextFrame.TextRange.Text.strip()
    except Exception:
        pass
    return "(untitled)"


def read_slide_text(slide) -> str:
    text_chunks: list[str] = []
    for shape in slide.Shapes:
        try:
            if shape.HasTextFrame and shape.TextFrame.HasText:
                text = shape.TextFrame.TextRange.Text.strip()
                if text:
                    text_chunks.append(text)
        except Exception:
            continue
    return "\n".join(deduplicate_preserving_order(text_chunks))


def read_notes_text(slide) -> str:
    text_chunks: list[str] = []
    for shape in slide.NotesPage.Shapes:
        try:
            if shape.HasTextFrame and shape.TextFrame.HasText:
                text = shape.TextFrame.TextRange.Text.strip()
                if text and text != str(slide.SlideNumber):
                    text_chunks.append(text)
        except Exception:
            continue
    return "\n".join(deduplicate_preserving_order(text_chunks))


def deduplicate_preserving_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def build_prompt(config: AnnotatorConfig, deck_path: Path, snapshot: SlideSnapshot) -> str:
    title_line = snapshot.title if snapshot.title else "(untitled)"
    notes_text = snapshot.notes_text or "(no existing notes)"
    slide_text = snapshot.slide_text or "(no extractable slide text)"
    return (
        "You are enriching PowerPoint speaker notes.\n\n"
        f"Deck: {deck_path.name}\n"
        f"Slide number: {snapshot.number}\n"
        f"Slide title: {title_line}\n\n"
        "Visible slide text:\n"
        f"{slide_text}\n\n"
        "Existing speaker notes:\n"
        f"{notes_text}\n\n"
        "Shared organizational guidance:\n"
        f"{config.context_prompt_helper}\n\n"
        "Task: Return only additive speaker-note content that would improve presenter readiness. "
        "Do not repeat the slide text. Do not rewrite existing notes. Do not invent facts. "
        "If nothing useful should be added, return exactly NO_CHANGE."
    )


def resolve_output_deck_path(config: AnnotatorConfig, deck_path: Path) -> Path:
    if deck_path.stem.endswith(config.annotated_suffix):
        return deck_path
    return config.temp_path / f"{deck_path.stem}{config.annotated_suffix}{deck_path.suffix}"


def ensure_output_deck_path(config: AnnotatorConfig, deck_path: Path) -> Path:
    output_path = resolve_output_deck_path(config, deck_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path != deck_path and not output_path.exists():
        shutil.copy2(deck_path, output_path)
    return output_path


def append_note_live(config: AnnotatorConfig, deck_path: Path, slide_number: int, note_text: str) -> Path:
    output_path = ensure_output_deck_path(config, deck_path)
    app = get_powerpoint_app()
    presentation = None
    target_slide = None
    notes_shape = None
    try:
        presentation = app.Presentations.Open(str(output_path), WithWindow=False)
        if slide_number < 1 or slide_number > presentation.Slides.Count:
            raise IndexError(
                f"Slide number {slide_number} is out of range 1..{presentation.Slides.Count}"
            )

        target_slide = presentation.Slides(slide_number)
        notes_shape = find_notes_body_shape(target_slide)
        existing_text = ""
        if notes_shape.TextFrame.HasText:
            existing_text = notes_shape.TextFrame.TextRange.Text.strip()

        merged_text = merge_notes(existing_text, note_text)
        notes_shape.TextFrame.TextRange.Text = merged_text
        presentation.Save()
        return output_path
    finally:
        notes_shape = None
        target_slide = None
        if presentation is not None:
            presentation.Close()
        presentation = None
        gc.collect()
        try:
            app.Quit()
        except Exception as exc:
            print(f"WARNING: failed to close PowerPoint cleanly: {exc}", file=sys.stderr)
        finally:
            try:
                import pythoncom  # pyright: ignore[reportMissingImports]

                pythoncom.CoUninitialize()
            except ImportError:
                pass


def find_notes_body_shape(slide):
    for shape in slide.NotesPage.Shapes:
        try:
            if shape.PlaceholderFormat.Type == 2:
                return shape
        except Exception:
            continue
    raise RuntimeError(f"Could not find the editable notes placeholder for slide {slide.SlideNumber}")


def merge_notes(existing_text: str, note_text: str) -> str:
    existing_text = existing_text.strip()
    note_text = note_text.strip()
    if not existing_text:
        return note_text
    if not note_text:
        return existing_text
    if note_text in existing_text:
        return existing_text
    return f"{existing_text}\n\n{note_text}"


def has_explicit_cli_action(args: argparse.Namespace) -> bool:
    return any(
        [
            args.list,
            args.deck_path is not None,
            args.deck_index is not None,
            args.append_note is not None,
            args.slide_number is not None,
            args.show_prompt,
            args.interactive,
        ]
    )


def prompt_for_int(prompt_text: str, minimum: int = 1, maximum: int | None = None) -> int:
    while True:
        raw_value = input(prompt_text).strip()
        if not raw_value.isdigit():
            print("Enter a whole number.")
            continue
        value = int(raw_value)
        if value < minimum:
            print(f"Enter a value >= {minimum}.")
            continue
        if maximum is not None and value > maximum:
            print(f"Enter a value <= {maximum}.")
            continue
        return value


def prompt_for_multiline_note() -> str:
    print("Enter note text. Submit an empty line to finish:")
    lines: list[str] = []
    while True:
        line = input()
        if not line and lines:
            break
        if not line and not lines:
            print("Note text cannot be empty.")
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def run_interactive_session(config: AnnotatorConfig, decks: list[Path]) -> int:
    deck_path = choose_deck(decks, deck_index=None)
    while True:
        output_path = resolve_output_deck_path(config, deck_path)
        print()
        print(f"Selected deck: {deck_path.name}")
        print(f"Resolved output deck: {output_path}")
        print("[1] Inspect slides")
        print("[2] Show prompt preview for a slide")
        print("[3] Append note live")
        print("[4] Choose another deck")
        print("[5] Exit")
        choice = prompt_for_int("Select an action: ", minimum=1, maximum=5)

        if choice == 1:
            max_slides = prompt_for_int("How many slides should be shown? ", minimum=1)
            inspect_deck(config=config, deck_path=deck_path, max_slides=max_slides, show_prompt=False)
            continue

        if choice == 2:
            slide_number = prompt_for_int("Slide number for prompt preview: ", minimum=1)
            inspect_single_slide_prompt(config=config, deck_path=deck_path, slide_number=slide_number)
            continue

        if choice == 3:
            slide_number = prompt_for_int("Slide number to update: ", minimum=1)
            note_text = prompt_for_multiline_note()
            updated_path = append_note_live(
                config=config,
                deck_path=deck_path,
                slide_number=slide_number,
                note_text=note_text,
            )
            print(f"Updated notes in: {updated_path}")
            continue

        if choice == 4:
            deck_path = choose_deck(decks, deck_index=None)
            continue

        return 0


def inspect_single_slide_prompt(config: AnnotatorConfig, deck_path: Path, slide_number: int) -> None:
    app = get_powerpoint_app()
    presentation = None
    try:
        presentation = app.Presentations.Open(str(deck_path), WithWindow=False)
        if slide_number < 1 or slide_number > presentation.Slides.Count:
            raise IndexError(
                f"Slide number {slide_number} is out of range 1..{presentation.Slides.Count}"
            )
        slide = presentation.Slides(slide_number)
        snapshot = SlideSnapshot(
            number=slide_number,
            title=read_slide_title(slide),
            slide_text=read_slide_text(slide),
            notes_text=read_notes_text(slide),
        )
        print()
        print(build_prompt(config, deck_path, snapshot))
    finally:
        if presentation is not None:
            presentation.Close()
        presentation = None
        gc.collect()
        try:
            app.Quit()
        except Exception as exc:
            print(f"WARNING: failed to close PowerPoint cleanly: {exc}", file=sys.stderr)
        finally:
            try:
                import pythoncom  # pyright: ignore[reportMissingImports]

                pythoncom.CoUninitialize()
            except ImportError:
                pass


def inspect_deck(config: AnnotatorConfig, deck_path: Path, max_slides: int, show_prompt: bool) -> int:
    app = get_powerpoint_app()
    presentation = None
    snapshots: list[SlideSnapshot] = []
    try:
        presentation = app.Presentations.Open(str(deck_path), WithWindow=False)
        print(f"Inspecting: {deck_path}")
        print(f"Configured output folder: {config.temp_path}")
        print()

        snapshots = iter_slide_snapshots(presentation, max_slides=max_slides)
        for snapshot in snapshots:
            print(f"Slide {snapshot.number}: {snapshot.title}")
            if snapshot.notes_text:
                print("Notes:")
                print(snapshot.notes_text)
            else:
                print("Notes:")
                print("(no speaker notes)")
            print("-" * 60)

        if show_prompt and snapshots:
            print("Prompt preview for first inspected slide:")
            print(build_prompt(config, deck_path, snapshots[0]))

        return 0
    finally:
        if presentation is not None:
            presentation.Close()
        presentation = None
        snapshots.clear()
        gc.collect()
        try:
            app.Quit()
        except Exception as exc:
            print(f"WARNING: failed to close PowerPoint cleanly: {exc}", file=sys.stderr)
        finally:
            try:
                import pythoncom  # pyright: ignore[reportMissingImports]

                pythoncom.CoUninitialize()
            except ImportError:
                pass


def main() -> int:
    args = parse_args()
    config = load_env_file(args.env_file)
    decks = find_decks(config)

    if args.list:
        print_decks(decks)
        return 0

    if args.interactive or not has_explicit_cli_action(args):
        return run_interactive_session(config=config, decks=decks)

    deck_path = resolve_selected_deck(args, decks)
    if args.append_note:
        if args.slide_number is None:
            raise ValueError("--slide-number is required when using --append-note.")
        output_path = append_note_live(
            config=config,
            deck_path=deck_path,
            slide_number=args.slide_number,
            note_text=args.append_note,
        )
        print(f"Updated notes in: {output_path}")
        return 0

    return inspect_deck(
        config=config,
        deck_path=deck_path,
        max_slides=max(1, args.max_slides),
        show_prompt=args.show_prompt,
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc