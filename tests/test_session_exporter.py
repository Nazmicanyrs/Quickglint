"""Tests for deterministic, separate-file, atomic session export."""

from pathlib import Path

from PySide6.QtGui import QColor, QImage

from app.session.screenshot_session import ScreenshotSession
from app.session.session_exporter import SessionExportWorker, build_export_paths, sanitize_prefix


def make_image(color: str) -> QImage:
    image = QImage(20, 14, QImage.Format.Format_ARGB32)
    image.fill(QColor(color))
    return image


def test_prefix_is_portable_and_paths_keep_session_indexes(tmp_path):
    session = ScreenshotSession("Website Tutorial")
    first = session.add_image(make_image("#EF4444"))
    second = session.add_image(make_image("#22C55E"))
    third = session.add_image(make_image("#3B82F6"))
    second.selected = False

    plan = build_export_paths(tmp_path, "Website: Tutorial", "png", [(1, first), (3, third)])
    assert sanitize_prefix("Website: Tutorial") == "Website_Tutorial"
    assert [path.name for _, path in plan] == ["Website_Tutorial_001.png", "Website_Tutorial_003.png"]


def test_export_writes_separate_png_files_atomically(tmp_path, qapp):
    session = ScreenshotSession("Demo")
    first = session.add_image(make_image("#EF4444"))
    second = session.add_image(make_image("#22C55E"))
    plan = build_export_paths(tmp_path, "Demo", "png", [(1, first), (2, second)])
    received = []
    worker = SessionExportWorker(plan)
    worker.completed.connect(received.append)

    # Calling run directly keeps this unit test deterministic while exercising
    # exactly the same worker code used by the background QThread.
    worker.run()

    assert len(received) == 1
    result = received[0]
    assert not result.error
    assert [path.name for path in result.written] == ["Demo_001.png", "Demo_002.png"]
    assert all(path.exists() for path in result.written)
    assert not list(tmp_path.glob("*.tmp*"))


def test_existing_file_can_be_renamed_without_overwrite(tmp_path, qapp):
    session = ScreenshotSession("Demo")
    item = session.add_image(make_image("#EF4444"))
    destination = tmp_path / "Demo_001.png"
    destination.write_bytes(b"existing")
    received = []
    worker = SessionExportWorker([(item, destination)], collision_policy="rename")
    worker.completed.connect(received.append)
    worker.run()

    assert destination.read_bytes() == b"existing"
    assert received[0].written[0].name == "Demo_001 (1).png"

