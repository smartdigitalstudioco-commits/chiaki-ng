"""Apply small, reversible, opt-in frame-exporter to a *source* tree of chiaki-ng.

This is NOT a binary patcher. It never modifies an installed Chiaki executable.
Run: python patch_chiaki.py C:\\path\\to\\chiaki-ng-source
Tested only against source anchors from upstream main (22 Nov 2026).
"""
from __future__ import annotations
import argparse
from pathlib import Path
import shutil
import sys

MARKER = "shotlab_framebridge::offer(frame.frame);"


def edit_file(path: Path, old: str, new: str) -> bool:
    data = path.read_text(encoding="utf-8")
    if new in data:
        print("Bereits gepatcht:", path)
        return False
    if data.count(old) != 1:
        raise RuntimeError(f"Quelltext-Anker nicht eindeutig vorhanden: {path.name}; Abbruch ohne Veraenderung. ({data.count(old)} Treffer)")
    backup = path.with_suffix(path.suffix + ".shotlab-backup")
    if not backup.exists():
        shutil.copy2(path, backup)
    path.write_text(data.replace(old, new), encoding="utf-8")
    print("Gepatcht:", path, "| Backup:", backup.name)
    return True


def apply(root: Path):
    src = root / "gui" / "src" / "qmlbackend.cpp"
    gui_cmake = root / "gui" / "CMakeLists.txt"
    root_cmake = root / "CMakeLists.txt"
    for p in (src, gui_cmake, root_cmake):
        if not p.is_file():
            raise FileNotFoundError(f"Keine passende Chiaki-ng-Quellstruktur: {p}")
    # Validate ALL anchors before modifying anything.
    checks = [
        (src, '#include "qmlbackend.h"', '#include "shotlab_framebridge.h"'),
        (src, '        const qint64 prepare_end_us = static_cast<qint64>(chiaki_time_now_monotonic_us());',
              '        '+MARKER),
        (gui_cmake, 'find_package(Qt6 REQUIRED COMPONENTS Core Gui Concurrent Svg Qml Quick Widgets)',
              'find_package(Qt6 REQUIRED COMPONENTS Core Gui Concurrent Svg Qml Quick Widgets Network)'),
        (gui_cmake, 'target_link_libraries(chiaki Qt::Core Qt::Gui Qt::GuiPrivate Qt::Concurrent Qt::Svg Qt::Qml Qt::Quick Qt::Widgets)',
              'target_link_libraries(chiaki Qt::Core Qt::Gui Qt::GuiPrivate Qt::Concurrent Qt::Svg Qt::Qml Qt::Quick Qt::Widgets Qt::Network FFMPEG::swscale)'),
        (root_cmake, 'find_package(FFMPEG COMPONENTS avcodec avutil avformat)',
              'find_package(FFMPEG COMPONENTS avcodec avutil avformat swscale)'),
    ]
    for file, old, new in checks:
        text = file.read_text(encoding="utf-8")
        if new not in text and text.count(old) != 1:
            raise RuntimeError(f"Quelltext-Version nicht kompatibel oder abweichend: {file}\nFehlender Anker: {old}")
    edit_file(src, '#include "qmlbackend.h"',
              '#include "qmlbackend.h"\n#include "shotlab_framebridge.h"')
    edit_file(src, '        const qint64 prepare_end_us = static_cast<qint64>(chiaki_time_now_monotonic_us());',
              '        '+MARKER+'\n        const qint64 prepare_end_us = static_cast<qint64>(chiaki_time_now_monotonic_us());')
    edit_file(gui_cmake, 'find_package(Qt6 REQUIRED COMPONENTS Core Gui Concurrent Svg Qml Quick Widgets)',
              'find_package(Qt6 REQUIRED COMPONENTS Core Gui Concurrent Svg Qml Quick Widgets Network)')
    edit_file(gui_cmake, 'target_link_libraries(chiaki Qt::Core Qt::Gui Qt::GuiPrivate Qt::Concurrent Qt::Svg Qt::Qml Qt::Quick Qt::Widgets)',
              'target_link_libraries(chiaki Qt::Core Qt::Gui Qt::GuiPrivate Qt::Concurrent Qt::Svg Qt::Qml Qt::Quick Qt::Widgets Qt::Network FFMPEG::swscale)')
    edit_file(root_cmake, 'find_package(FFMPEG COMPONENTS avcodec avutil avformat)',
              'find_package(FFMPEG COMPONENTS avcodec avutil avformat swscale)')
    dst = src.parent / "shotlab_framebridge.h"
    if dst.exists() and dst.read_bytes() != (Path(__file__).parent/"shotlab_framebridge.h").read_bytes():
        raise RuntimeError(f"{dst} existiert mit anderem Inhalt; nicht ueberschrieben")
    shutil.copy2(Path(__file__).parent / "shotlab_framebridge.h", dst)
    print("\nFertig: Quellcode modifiziert, NICHT kompiliert. Installiertes Chiaki ist unveraendert.")
    print("Bridge nur mit Umgebungsvariable SHOTLAB_FRAME_BRIDGE=1 aktiv.")


def main():
    parser=argparse.ArgumentParser(description="ShotLab Decoder Frame Bridge: Chiaki-ng Quellen patchen")
    parser.add_argument("source_dir", type=Path, help="Ausgechecktes chiaki-ng Quellverzeichnis")
    args=parser.parse_args()
    try:
        apply(args.source_dir.expanduser().resolve())
    except Exception as exc:
        print("FEHLER:", exc, file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__': main()
