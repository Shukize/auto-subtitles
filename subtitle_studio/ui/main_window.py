"""Main application window: drag-and-drop, transcription, editing, styling, export."""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, QMimeData
from PySide6.QtGui import QColor, QFont, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox,
    QFileDialog, QFontComboBox, QFrame, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QProgressBar,
    QPushButton, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from subtitle_studio import APP_NAME, __version__, config
from subtitle_studio.core import media, subtitles as subs_mod, transcribe, translate
from subtitle_studio.ui.util import format_timestamp, parse_timestamp
from subtitle_studio.ui.workers import Worker


# ----------------------------------------------------------------------------- drop zone
class DropZone(QFrame):
    """A large drop target that also forwards clicks to 'open file'."""

    def __init__(self, on_paths, on_click):
        super().__init__()
        self._on_paths = on_paths
        self._on_click = on_click
        self.setAcceptDrops(True)
        self.setObjectName("DropZone")
        self.setMinimumHeight(110)
        self.setFrameShape(QFrame.StyledPanel)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        title = QLabel("Drag & drop video or audio here")
        title.setAlignment(Qt.AlignCenter)
        f = title.font(); f.setPointSize(13); f.setBold(True); title.setFont(f)
        hint = QLabel("…or click to open a file  ·  use “Open Folder” for batches")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("color: #9aa0a6;")
        lay.addWidget(title)
        lay.addWidget(hint)
        self._apply_style(False)

    def _apply_style(self, active: bool) -> None:
        border = "#4c8bf5" if active else "#454545"
        bg = "#26333f" if active else "#2b2b2b"
        self.setStyleSheet(
            f"#DropZone {{ border: 2px dashed {border}; border-radius: 10px; "
            f"background: {bg}; }}"
        )

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._apply_style(True)

    def dragLeaveEvent(self, e):
        self._apply_style(False)

    def dropEvent(self, e):
        self._apply_style(False)
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self._on_paths(paths)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._on_click()


# ----------------------------------------------------------------------------- main window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = config.Settings.load()
        self.document: Optional[subs_mod.SubtitleDocument] = None
        self.current_file: Optional[Path] = None
        self.worker: Optional[Worker] = None

        self.setWindowTitle(f"{APP_NAME}  v{__version__}")
        self.resize(1180, 760)
        self._build_ui()
        self._apply_dark_theme()
        self._sync_settings_to_ui()

    # ---- layout -------------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # Top: drop zone + open buttons
        top = QHBoxLayout()
        self.drop = DropZone(self._add_paths, self._open_files)
        top.addWidget(self.drop, 1)
        btn_col = QVBoxLayout()
        b_file = QPushButton("Open File…"); b_file.clicked.connect(self._open_files)
        b_folder = QPushButton("Open Folder…"); b_folder.clicked.connect(self._open_folder)
        b_subs = QPushButton("Import Subtitles…"); b_subs.clicked.connect(self._import_subs)
        for b in (b_file, b_folder, b_subs):
            btn_col.addWidget(b)
        btn_col.addStretch(1)
        top.addLayout(btn_col)
        root.addLayout(top)

        # Middle splitter: left (queue + settings) | right (table + style)
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([330, 850])
        root.addWidget(splitter, 1)

        # Bottom: progress + status
        bottom = QHBoxLayout()
        self.progress = QProgressBar(); self.progress.setValue(0)
        self.status = QLabel("Ready")
        self.status.setStyleSheet("color: #9aa0a6;")
        self.cancel_btn = QPushButton("Cancel"); self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)
        bottom.addWidget(self.progress, 1)
        bottom.addWidget(self.cancel_btn)
        root.addLayout(bottom)
        root.addWidget(self.status)

    def _build_left_panel(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)

        # Queue
        qbox = QGroupBox("Files")
        qlay = QVBoxLayout(qbox)
        self.queue = QListWidget()
        self.queue.setSelectionMode(QAbstractItemView.SingleSelection)
        self.queue.currentRowChanged.connect(self._on_queue_select)
        qlay.addWidget(self.queue)
        qrow = QHBoxLayout()
        b_rm = QPushButton("Remove"); b_rm.clicked.connect(self._remove_selected)
        b_clr = QPushButton("Clear"); b_clr.clicked.connect(self._clear_queue)
        qrow.addWidget(b_rm); qrow.addWidget(b_clr)
        qlay.addLayout(qrow)
        lay.addWidget(qbox)

        # Transcription settings
        sbox = QGroupBox("Transcription")
        sl = QVBoxLayout(sbox)

        sl.addWidget(QLabel("Accuracy / model"))
        self.model_combo = QComboBox()
        labels = {
            "tiny": "Tiny (fastest)", "base": "Base", "small": "Small",
            "medium": "Medium", "large-v3": "Large-v3 (most accurate)",
        }
        for m in config.WHISPER_MODELS:
            self.model_combo.addItem(labels.get(m, m), m)
        sl.addWidget(self.model_combo)

        sl.addWidget(QLabel("Spoken language"))
        self.src_combo = QComboBox()
        self.src_combo.addItem("Auto-detect", "auto")
        for name, code in translate.LANGUAGES.items():
            self.src_combo.addItem(name, code)
        sl.addWidget(self.src_combo)

        sl.addWidget(QLabel("Translate subtitles to"))
        self.tgt_combo = QComboBox()
        self.tgt_combo.addItem("No translation", "")
        for name, code in translate.LANGUAGES.items():
            self.tgt_combo.addItem(name, code)
        sl.addWidget(self.tgt_combo)

        row = QHBoxLayout()
        row.addWidget(QLabel("Max chars/line"))
        self.cpl_spin = QSpinBox(); self.cpl_spin.setRange(20, 90)
        row.addWidget(self.cpl_spin)
        row.addWidget(QLabel("Max lines"))
        self.lines_spin = QSpinBox(); self.lines_spin.setRange(1, 4)
        row.addWidget(self.lines_spin)
        sl.addLayout(row)

        self.gen_btn = QPushButton("⚡  Generate Subtitles")
        self.gen_btn.setObjectName("Primary")
        self.gen_btn.clicked.connect(self._generate_current)
        sl.addWidget(self.gen_btn)

        self.batch_btn = QPushButton("Batch: generate + save .srt for all")
        self.batch_btn.clicked.connect(self._batch_process)
        sl.addWidget(self.batch_btn)

        lay.addWidget(sbox)
        lay.addStretch(1)
        return w

    def _build_right_panel(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)

        # Editable subtitle table
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Start", "End", "Subtitle text"])
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked
            | QAbstractItemView.EditKeyPressed
        )
        self.table.itemChanged.connect(self._on_item_changed)
        lay.addWidget(self.table, 1)

        # Row tools
        rtools = QHBoxLayout()
        for text, fn in [
            ("Add row", self._add_row), ("Delete row", self._delete_row),
            ("Merge with next", self._merge_next), ("Split at cursor", self._split_row),
        ]:
            b = QPushButton(text); b.clicked.connect(fn); rtools.addWidget(b)
        rtools.addStretch(1)
        self.retranslate_btn = QPushButton("Translate current")
        self.retranslate_btn.clicked.connect(self._translate_current_doc)
        rtools.addWidget(self.retranslate_btn)
        lay.addLayout(rtools)

        # Styling
        lay.addWidget(self._build_style_box())

        # Export
        ebox = QHBoxLayout()
        for text, fn in [
            ("Save .srt", lambda: self._save_subs("srt")),
            ("Save .vtt", lambda: self._save_subs("vtt")),
            ("Save .ass (styled)", lambda: self._save_subs("ass")),
        ]:
            b = QPushButton(text); b.clicked.connect(fn); ebox.addWidget(b)
        ebox.addStretch(1)
        self.burn_btn = QPushButton("🔥  Burn into video")
        self.burn_btn.setObjectName("Primary")
        self.burn_btn.clicked.connect(self._burn_video)
        ebox.addWidget(self.burn_btn)
        lay.addLayout(ebox)
        return w

    def _build_style_box(self) -> QGroupBox:
        box = QGroupBox("Subtitle style (for burn-in & .ass export)")
        lay = QHBoxLayout(box)

        col1 = QVBoxLayout()
        col1.addWidget(QLabel("Font"))
        self.font_combo = QFontComboBox()
        self.font_combo.currentFontChanged.connect(self._on_style_change)
        col1.addWidget(self.font_combo)
        srow = QHBoxLayout()
        srow.addWidget(QLabel("Size"))
        self.size_spin = QSpinBox(); self.size_spin.setRange(8, 120)
        self.size_spin.valueChanged.connect(self._on_style_change)
        srow.addWidget(self.size_spin)
        self.bold_chk = QCheckBox("Bold"); self.bold_chk.toggled.connect(self._on_style_change)
        self.italic_chk = QCheckBox("Italic"); self.italic_chk.toggled.connect(self._on_style_change)
        srow.addWidget(self.bold_chk); srow.addWidget(self.italic_chk)
        col1.addLayout(srow)
        lay.addLayout(col1)

        col2 = QVBoxLayout()
        self.text_color_btn = QPushButton("Text colour")
        self.text_color_btn.clicked.connect(lambda: self._pick_color("primary_color"))
        self.outline_color_btn = QPushButton("Outline colour")
        self.outline_color_btn.clicked.connect(lambda: self._pick_color("outline_color"))
        col2.addWidget(self.text_color_btn)
        col2.addWidget(self.outline_color_btn)
        orow = QHBoxLayout()
        orow.addWidget(QLabel("Outline"))
        self.outline_spin = QDoubleSpinBox(); self.outline_spin.setRange(0, 10)
        self.outline_spin.setSingleStep(0.5)
        self.outline_spin.valueChanged.connect(self._on_style_change)
        orow.addWidget(self.outline_spin)
        col2.addLayout(orow)
        lay.addLayout(col2)

        col3 = QVBoxLayout()
        col3.addWidget(QLabel("Position"))
        self.pos_combo = QComboBox()
        # ASS numpad alignment values
        for label, val in [
            ("Bottom", 2), ("Bottom-left", 1), ("Bottom-right", 3),
            ("Middle", 5), ("Top", 8), ("Top-left", 7), ("Top-right", 9),
        ]:
            self.pos_combo.addItem(label, val)
        self.pos_combo.currentIndexChanged.connect(self._on_style_change)
        col3.addWidget(self.pos_combo)
        mrow = QHBoxLayout()
        mrow.addWidget(QLabel("V-margin"))
        self.marginv_spin = QSpinBox(); self.marginv_spin.setRange(0, 400)
        self.marginv_spin.valueChanged.connect(self._on_style_change)
        mrow.addWidget(self.marginv_spin)
        col3.addLayout(mrow)
        lay.addLayout(col3)
        return box

    # ---- settings <-> UI ---------------------------------------------
    def _sync_settings_to_ui(self) -> None:
        s = self.settings
        self._set_combo_data(self.model_combo, s.model)
        self._set_combo_data(self.src_combo, s.source_language)
        self._set_combo_data(self.tgt_combo, s.translate_to)
        self.cpl_spin.setValue(s.max_chars_per_line)
        self.lines_spin.setValue(s.max_lines)
        st = s.style
        self.font_combo.setCurrentFont(QFont(st.font_name))
        self.size_spin.setValue(st.font_size)
        self.bold_chk.setChecked(st.bold)
        self.italic_chk.setChecked(st.italic)
        self.outline_spin.setValue(st.outline)
        self._set_combo_data(self.pos_combo, st.alignment)
        self.marginv_spin.setValue(st.margin_v)
        self._refresh_color_buttons()

    def _collect_settings(self) -> None:
        s = self.settings
        s.model = self.model_combo.currentData()
        s.source_language = self.src_combo.currentData()
        s.translate_to = self.tgt_combo.currentData()
        s.max_chars_per_line = self.cpl_spin.value()
        s.max_lines = self.lines_spin.value()
        st = s.style
        st.font_name = self.font_combo.currentFont().family()
        st.font_size = self.size_spin.value()
        st.bold = self.bold_chk.isChecked()
        st.italic = self.italic_chk.isChecked()
        st.outline = self.outline_spin.value()
        st.alignment = self.pos_combo.currentData()
        st.margin_v = self.marginv_spin.value()
        s.save()

    def _on_style_change(self, *_):
        self._collect_settings()

    def _pick_color(self, attr: str) -> None:
        current = getattr(self.settings.style, attr)
        col = QColorDialog.getColor(QColor(current), self, "Choose colour")
        if col.isValid():
            setattr(self.settings.style, attr, col.name().upper())
            self._refresh_color_buttons()
            self.settings.save()

    def _refresh_color_buttons(self) -> None:
        for btn, attr in [
            (self.text_color_btn, "primary_color"),
            (self.outline_color_btn, "outline_color"),
        ]:
            c = getattr(self.settings.style, attr)
            fg = "#000" if QColor(c).lightnessF() > 0.6 else "#fff"
            btn.setStyleSheet(f"background:{c}; color:{fg};")

    @staticmethod
    def _set_combo_data(combo: QComboBox, data) -> None:
        idx = combo.findData(data)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    # ---- file queue ---------------------------------------------------
    def _open_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Open media", "",
            "Media files (*.mp4 *.mkv *.mov *.avi *.webm *.flv *.wmv *.m4v "
            "*.mp3 *.wav *.m4a *.aac *.flac *.ogg);;All files (*.*)",
        )
        if paths:
            self._add_paths(paths)

    def _open_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Open folder")
        if folder:
            found = [
                str(p) for p in sorted(Path(folder).iterdir())
                if p.is_file() and media.is_media_file(p)
            ]
            if found:
                self._add_paths(found)
            else:
                self.status.setText("No media files found in that folder.")

    def _import_subs(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import subtitles", "", "Subtitles (*.srt *.vtt *.ass *.ssa)"
        )
        if not path:
            return
        try:
            self.document = subs_mod.SubtitleDocument.load(path)
            self._populate_table()
            self.status.setText(f"Imported {len(self.document.lines)} lines from {Path(path).name}")
        except Exception as exc:
            QMessageBox.critical(self, "Import failed", str(exc))

    def _add_paths(self, paths: List[str]) -> None:
        added = 0
        existing = {self.queue.item(i).data(Qt.UserRole) for i in range(self.queue.count())}
        for p in paths:
            if media.is_media_file(p) and p not in existing:
                item = QListWidgetItem(Path(p).name)
                item.setData(Qt.UserRole, p)
                item.setToolTip(p)
                self.queue.addItem(item)
                existing.add(p)
                added += 1
        if added and self.queue.currentRow() < 0:
            self.queue.setCurrentRow(0)
        self.status.setText(f"Added {added} file(s). {self.queue.count()} in queue.")

    def _on_queue_select(self, row: int) -> None:
        if 0 <= row < self.queue.count():
            self.current_file = Path(self.queue.item(row).data(Qt.UserRole))

    def _remove_selected(self) -> None:
        row = self.queue.currentRow()
        if row >= 0:
            self.queue.takeItem(row)

    def _clear_queue(self) -> None:
        self.queue.clear()
        self.current_file = None

    # ---- table --------------------------------------------------------
    def _populate_table(self) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        if self.document:
            for ln in self.document.lines:
                self._append_table_row(ln.start, ln.end, ln.text)
        self.table.blockSignals(False)

    def _append_table_row(self, start: float, end: float, text: str) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(format_timestamp(start)))
        self.table.setItem(r, 1, QTableWidgetItem(format_timestamp(end)))
        self.table.setItem(r, 2, QTableWidgetItem(text))

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        """Push table edits back into the document model, validating times."""
        if not self.document:
            return
        r, c = item.row(), item.column()
        if r >= len(self.document.lines):
            return
        ln = self.document.lines[r]
        if c == 0 or c == 1:
            try:
                val = parse_timestamp(item.text())
            except ValueError:
                self.table.blockSignals(True)
                item.setText(format_timestamp(ln.start if c == 0 else ln.end))
                self.table.blockSignals(False)
                return
            if c == 0:
                ln.start = val
            else:
                ln.end = val
        else:
            ln.text = item.text()

    def _sync_table_to_document(self) -> None:
        """Ensure the model reflects the table before exporting."""
        if not self.document:
            return
        for r, ln in enumerate(self.document.lines):
            t0 = self.table.item(r, 0)
            t1 = self.table.item(r, 1)
            t2 = self.table.item(r, 2)
            try:
                if t0:
                    ln.start = parse_timestamp(t0.text())
                if t1:
                    ln.end = parse_timestamp(t1.text())
            except ValueError:
                pass
            if t2:
                ln.text = t2.text()

    def _add_row(self) -> None:
        if self.document is None:
            self.document = subs_mod.SubtitleDocument()
        row = self.table.currentRow()
        idx = row + 1 if row >= 0 else len(self.document.lines)
        prev_end = self.document.lines[row].end if 0 <= row < len(self.document.lines) else 0.0
        new = subs_mod.SubtitleLine(prev_end, prev_end + 2.0, "")
        self.document.lines.insert(idx, new)
        self._populate_table()
        self.table.setCurrentCell(idx, 2)

    def _delete_row(self) -> None:
        row = self.table.currentRow()
        if self.document and 0 <= row < len(self.document.lines):
            del self.document.lines[row]
            self._populate_table()

    def _merge_next(self) -> None:
        row = self.table.currentRow()
        if self.document and 0 <= row < len(self.document.lines) - 1:
            a = self.document.lines[row]
            b = self.document.lines[row + 1]
            a.end = b.end
            a.text = (a.text + " " + b.text).strip()
            del self.document.lines[row + 1]
            self._populate_table()
            self.table.setCurrentCell(row, 2)

    def _split_row(self) -> None:
        row = self.table.currentRow()
        if not (self.document and 0 <= row < len(self.document.lines)):
            return
        ln = self.document.lines[row]
        words = ln.text.split()
        if len(words) < 2:
            return
        mid = len(words) // 2
        midtime = (ln.start + ln.end) / 2
        first = subs_mod.SubtitleLine(ln.start, midtime, " ".join(words[:mid]))
        second = subs_mod.SubtitleLine(midtime, ln.end, " ".join(words[mid:]))
        self.document.lines[row:row + 1] = [first, second]
        self._populate_table()
        self.table.setCurrentCell(row, 2)

    # ---- jobs ---------------------------------------------------------
    def _busy(self, busy: bool, msg: str = "") -> None:
        for b in (self.gen_btn, self.batch_btn, self.burn_btn,
                  self.retranslate_btn):
            b.setEnabled(not busy)
        self.cancel_btn.setEnabled(busy)
        if msg:
            self.status.setText(msg)
        if not busy:
            self.progress.setValue(0)

    def _cancel(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.status.setText("Cancelling…")

    def _on_progress(self, frac: float, msg: str) -> None:
        self.progress.setValue(int(frac * 100))
        if msg:
            self.status.setText(msg)

    def _generate_current(self) -> None:
        if not self.current_file:
            QMessageBox.information(self, APP_NAME, "Add and select a file first.")
            return
        self._collect_settings()
        media_path = self.current_file
        settings = self.settings
        tmp_wav = Path(config.app_data_dir()) / "_extract.wav"
        do_translate = bool(settings.translate_to)

        def job(progress, is_cancelled):
            dur = media.probe_duration(media_path)
            progress(0.0, "Extracting audio…")
            media.extract_audio(
                media_path, tmp_wav,
                progress=lambda f: progress(f * 0.1, "Extracting audio…"),
                duration=dur,
            )
            if is_cancelled():
                raise RuntimeError("Cancelled")
            result = transcribe.transcribe(
                tmp_wav, settings,
                progress=lambda f, m: progress(0.1 + f * 0.8, m),
                cancelled=is_cancelled,
            )
            doc = subs_mod.SubtitleDocument.from_result(result)
            if do_translate and doc.lines:
                progress(0.9, f"Translating → {settings.translate_to}…")
                translated = translate.translate_lines(
                    doc.texts(), settings.translate_to,
                    source=settings.source_language,
                    progress=lambda f: progress(0.9 + f * 0.1, "Translating…"),
                    cancelled=is_cancelled,
                )
                doc.set_texts(translated)
            progress(1.0, "Done")
            return doc

        self._run_job(job, self._on_generated)

    def _on_generated(self, doc: subs_mod.SubtitleDocument) -> None:
        self.document = doc
        self._populate_table()
        self._busy(False, f"Generated {len(doc.lines)} subtitle lines "
                          f"(language: {doc.language}).")

    def _translate_current_doc(self) -> None:
        if not self.document or not self.document.lines:
            QMessageBox.information(self, APP_NAME, "Generate or import subtitles first.")
            return
        self._collect_settings()
        target = self.settings.translate_to
        if not target:
            QMessageBox.information(
                self, APP_NAME, "Choose a target language in “Translate subtitles to”.")
            return
        self._sync_table_to_document()
        doc = self.document
        src = self.settings.source_language

        def job(progress, is_cancelled):
            progress(0.0, f"Translating → {target}…")
            translated = translate.translate_lines(
                doc.texts(), target, source=src,
                progress=lambda f: progress(f, "Translating…"),
                cancelled=is_cancelled,
            )
            doc.set_texts(translated)
            return doc

        self._run_job(job, self._on_generated)

    def _batch_process(self) -> None:
        if self.queue.count() == 0:
            QMessageBox.information(self, APP_NAME, "Add files to the queue first.")
            return
        self._collect_settings()
        settings = self.settings
        files = [Path(self.queue.item(i).data(Qt.UserRole)) for i in range(self.queue.count())]
        tmp_wav = Path(config.app_data_dir()) / "_extract.wav"
        do_translate = bool(settings.translate_to)

        def job(progress, is_cancelled):
            n = len(files)
            saved = []
            for i, f in enumerate(files):
                if is_cancelled():
                    raise RuntimeError("Cancelled")
                base = i / n

                def p(frac, msg=""):
                    progress(base + frac / n, f"[{i+1}/{n}] {f.name}  {msg}")

                dur = media.probe_duration(f)
                media.extract_audio(f, tmp_wav,
                                    progress=lambda fr: p(fr * 0.1, "extracting"),
                                    duration=dur)
                result = transcribe.transcribe(
                    tmp_wav, settings,
                    progress=lambda fr, m: p(0.1 + fr * 0.8, m),
                    cancelled=is_cancelled,
                )
                doc = subs_mod.SubtitleDocument.from_result(result)
                if do_translate and doc.lines:
                    translated = translate.translate_lines(
                        doc.texts(), settings.translate_to,
                        source=settings.source_language,
                        progress=lambda fr: p(0.9 + fr * 0.1, "translating"),
                        cancelled=is_cancelled,
                    )
                    doc.set_texts(translated)
                out = f.with_suffix(".srt")
                doc.save(out)
                saved.append(out)
            return saved

        def on_done(saved):
            self._busy(False, f"Batch complete: saved {len(saved)} .srt file(s).")
            QMessageBox.information(
                self, APP_NAME,
                "Saved:\n" + "\n".join(str(s) for s in saved[:20]))

        self._run_job(job, on_done)

    def _burn_video(self) -> None:
        if not self.document or not self.document.lines:
            QMessageBox.information(self, APP_NAME, "Generate or import subtitles first.")
            return
        if not self.current_file or not media.is_video_file(self.current_file):
            QMessageBox.information(self, APP_NAME, "Select a video file to burn into.")
            return
        self._sync_table_to_document()
        self._collect_settings()
        src_video = self.current_file
        default_out = str(src_video.with_name(src_video.stem + "_subtitled.mp4"))
        out_path, _ = QFileDialog.getSaveFileName(
            self, "Save subtitled video", default_out, "MP4 video (*.mp4)")
        if not out_path:
            return
        doc = self.document
        style = self.settings.style
        ass_path = Path(config.app_data_dir()) / "_burn.ass"

        def job(progress, is_cancelled):
            progress(0.0, "Preparing subtitles…")
            doc.save_styled_ass(ass_path, style)
            dur = media.probe_duration(src_video)
            media.burn_subtitles(
                src_video, ass_path, out_path,
                progress=lambda f: progress(f, "Burning subtitles into video…"),
                duration=dur,
            )
            return out_path

        def on_done(path):
            self._busy(False, f"Saved subtitled video: {path}")
            QMessageBox.information(self, APP_NAME, f"Done!\nSaved to:\n{path}")

        self._run_job(job, on_done)

    def _save_subs(self, fmt: str) -> None:
        if not self.document or not self.document.lines:
            QMessageBox.information(self, APP_NAME, "Nothing to save yet.")
            return
        self._sync_table_to_document()
        self._collect_settings()
        base = self.current_file.stem if self.current_file else "subtitles"
        start_dir = str(self.current_file.with_suffix("." + fmt)) if self.current_file \
            else f"{base}.{fmt}"
        path, _ = QFileDialog.getSaveFileName(
            self, f"Save .{fmt}", start_dir, f"{fmt.upper()} (*.{fmt})")
        if not path:
            return
        try:
            style = self.settings.style if fmt == "ass" else None
            self.document.save(path, style)
            self.status.setText(f"Saved {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))

    # ---- worker plumbing ---------------------------------------------
    def _run_job(self, job, on_done) -> None:
        if self.worker and self.worker.isRunning():
            return
        self._busy(True, "Working…")
        self.worker = Worker(job)
        self.worker.progress.connect(self._on_progress)

        def done(result):
            on_done(result)
            self.worker = None

        def failed(msg):
            self._busy(False, "Failed.")
            if msg != "Cancelled":
                QMessageBox.critical(self, "Error", msg)
            else:
                self.status.setText("Cancelled.")
            self.worker = None

        self.worker.done.connect(done)
        self.worker.failed.connect(failed)
        self.worker.start()

    # ---- theme --------------------------------------------------------
    def _apply_dark_theme(self) -> None:
        self.setStyleSheet(
            """
            QWidget { background:#1f1f1f; color:#e8eaed; font-size:13px; }
            QGroupBox { border:1px solid #3a3a3a; border-radius:8px; margin-top:10px;
                        padding-top:10px; }
            QGroupBox::title { subcontrol-origin: margin; left:10px; padding:0 4px;
                               color:#9aa0a6; }
            QPushButton { background:#333; border:1px solid #444; border-radius:6px;
                          padding:6px 10px; }
            QPushButton:hover { background:#3c3c3c; }
            QPushButton:disabled { color:#777; }
            QPushButton#Primary { background:#1a73e8; border:none; font-weight:bold;
                                  padding:9px 14px; }
            QPushButton#Primary:hover { background:#2b7df0; }
            QPushButton#Primary:disabled { background:#2a3a55; color:#9aa0a6; }
            QComboBox, QSpinBox, QDoubleSpinBox, QListWidget, QTableWidget {
                background:#2b2b2b; border:1px solid #3a3a3a; border-radius:6px;
                padding:3px; }
            QHeaderView::section { background:#2b2b2b; border:none; padding:6px;
                                   color:#9aa0a6; }
            QTableWidget { gridline-color:#333; }
            QProgressBar { border:1px solid #3a3a3a; border-radius:6px; text-align:center;
                           background:#2b2b2b; }
            QProgressBar::chunk { background:#1a73e8; border-radius:6px; }
            """
        )

    def closeEvent(self, e):
        self._collect_settings()
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(2000)
        super().closeEvent(e)
