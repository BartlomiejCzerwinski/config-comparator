import sys
from typing import Any, Dict, Set

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (
    QApplication,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
    QPlainTextEdit,
    QCheckBox,
)

try:
    import yaml  # PyYAML
except ImportError:
    yaml = None

APP_TITLE = "Config Comparator"

GREEN = QColor(37, 143, 31)    # soft green background
RED = QColor(181, 48, 38)      # soft red background
ORANGE = QColor(217, 131, 43)  # soft orange for value mismatch


def _ensure_yaml():
    if yaml is None:
        raise RuntimeError("PyYAML is not installed. Run: pip install pyyaml")


def yaml_keys_from_text(text: str) -> Set[str]:
    _ensure_yaml()
    if not text.strip():
        raise ValueError("Empty YAML content.")
    try:
        data = yaml.safe_load(text)
    except Exception as e:
        raise ValueError(f"Invalid YAML: {e}") from e

    keys: Set[str] = set()

    def walk(node: Any, prefix: str = "") -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                key_path = f"{prefix}.{k}" if prefix else str(k)
                keys.add(key_path)
                walk(v, key_path)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                key_path = f"{prefix}[{i}]" if prefix else f"[{i}]"
                keys.add(key_path)
                walk(item, key_path)
        else:
            return

    walk(data)
    return keys


def yaml_items_from_text(text: str) -> Dict[str, Any]:
    """Map path -> value (scalar or container)."""
    _ensure_yaml()
    if not text.strip():
        raise ValueError("Empty YAML content.")
    try:
        data = yaml.safe_load(text)
    except Exception as e:
        raise ValueError(f"Invalid YAML: {e}") from e

    items: Dict[str, Any] = {}

    def walk(node: Any, prefix: str = "") -> None:
        if prefix:
            items[prefix] = node
        if isinstance(node, dict):
            for k, v in node.items():
                key_path = f"{prefix}.{k}" if prefix else str(k)
                walk(v, key_path)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                key_path = f"{prefix}[{i}]" if prefix else f"[{i}]"
                walk(item, key_path)
        else:
            return

    if not isinstance(data, (dict, list)):
        items["<root>"] = data
        return items

    walk(data)
    return items


def is_scalar(x: Any) -> bool:
    return isinstance(x, (str, int, float, bool, type(None)))


def is_container(x: Any) -> bool:
    return isinstance(x, (dict, list))


def _one_line(s: str) -> str:
    return " ".join(s.split())


def fmt_value(v: Any, max_len: int = 180) -> str:
    _ensure_yaml()
    if is_scalar(v):
        s = repr(v)
    else:
        try:
            s = yaml.safe_dump(v, sort_keys=True, default_flow_style=False).rstrip()
        except Exception:
            s = f"<{type(v).__name__}>"
    s = _one_line(s)
    if len(s) > max_len:
        s = s[: max_len - 1] + "…"
    return s


class ConfigComparator(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(1100, 720)
        self._init_ui()

    def _init_ui(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        paste_box = QGroupBox("Paste YAML configs")
        paste_layout = QGridLayout(paste_box)

        self.left_label = QLabel("Config A")
        self.right_label = QLabel("Config B")

        self.left_text = QPlainTextEdit()
        self.right_text = QPlainTextEdit()
        self.left_text.setPlaceholderText("Paste YAML A here…")
        self.right_text.setPlaceholderText("Paste YAML B here…")
        self.left_text.setTabChangesFocus(False)
        self.right_text.setTabChangesFocus(False)
        self.left_text.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.right_text.setLineWrapMode(QPlainTextEdit.NoWrap)
        mono = self.left_text.font()
        mono.setFamily("Consolas, 'Courier New', monospace")
        self.left_text.setFont(mono)
        self.right_text.setFont(mono)

        paste_layout.addWidget(self.left_label, 0, 0)
        paste_layout.addWidget(self.right_label, 0, 1)
        paste_layout.addWidget(self.left_text, 1, 0)
        paste_layout.addWidget(self.right_text, 1, 1)
        paste_layout.setColumnStretch(0, 1)
        paste_layout.setColumnStretch(1, 1)
        paste_layout.setRowStretch(1, 1)

        # Actions
        actions_row = QHBoxLayout()
        self.values_checkbox = QCheckBox("Compare values")
        self.values_checkbox.setToolTip(
            "When checked, values are compared. "
        )
        self.compare_btn = QPushButton("Compare")
        self.compare_btn.setDefault(True)
        self.compare_btn.clicked.connect(self.compare)

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self.clear)

        actions_row.addWidget(self.values_checkbox)
        actions_row.addStretch(1)
        actions_row.addWidget(self.clear_btn)
        actions_row.addWidget(self.compare_btn)

        # Results
        results_box = QGroupBox(
            "Comparison result (green = in both, red = missing in the other, orange = values differ)"
        )
        results_layout = QGridLayout(results_box)

        self.left_list = QListWidget()
        self.right_list = QListWidget()
        list_mono = self.left_list.font()
        list_mono.setFamily("Consolas, 'Courier New', monospace")
        self.left_list.setFont(list_mono)
        self.right_list.setFont(list_mono)
        self.left_list.setAlternatingRowColors(True)
        self.right_list.setAlternatingRowColors(True)

        results_layout.addWidget(QLabel("Entries from A"), 0, 0)
        results_layout.addWidget(QLabel("Entries from B"), 0, 1)
        results_layout.addWidget(self.left_list, 1, 0)
        results_layout.addWidget(self.right_list, 1, 1)
        results_layout.setColumnStretch(0, 1)
        results_layout.setColumnStretch(1, 1)
        results_layout.setRowStretch(1, 1)

        layout.addWidget(paste_box)
        layout.addLayout(actions_row)
        layout.addWidget(results_box)

        status = QStatusBar()
        self.setStatusBar(status)
        self.setCentralWidget(central)

        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction(about_action)

        self.setStyleSheet(
            """
            QGroupBox { font-weight: 600; border: 1px solid #ddd; border-radius: 10px; margin-top: 12px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QPushButton { padding: 8px 14px; border-radius: 10px; }
            QPushButton:hover { background: #f2f2f2; }
            QListWidget, QPlainTextEdit { border: 1px solid #ddd; border-radius: 10px; }
            """
        )

    def clear(self) -> None:
        self.left_text.clear()
        self.right_text.clear()
        self.left_list.clear()
        self.right_list.clear()
        self.statusBar().clearMessage()

    def compare(self) -> None:
        left_text = self.left_text.toPlainText()
        right_text = self.right_text.toPlainText()
        if not left_text.strip() or not right_text.strip():
            QMessageBox.warning(self, APP_TITLE, "Paste YAML on both sides.")
            return

        try:
            left_keys = yaml_keys_from_text(left_text)
            right_keys = yaml_keys_from_text(right_text)
            compare_values = self.values_checkbox.isChecked()
            if compare_values:
                left_items = yaml_items_from_text(left_text)
                right_items = yaml_items_from_text(right_text)
            else:
                left_items = right_items = {}
        except Exception as e:
            QMessageBox.critical(self, APP_TITLE, f"Parse error: {e}")
            return

        both = left_keys & right_keys
        only_left = left_keys - right_keys
        only_right = right_keys - left_keys

        mismatched = 0

        self.left_list.clear()
        self.right_list.clear()

        def add_item(widget: QListWidget, text: str, color: QColor) -> None:
            item = QListWidgetItem(text)
            item.setBackground(color)
            widget.addItem(item)

        if compare_values:
            for key in sorted(both):
                a_val = left_items.get(key, "<missing>")
                b_val = right_items.get(key, "<missing>")

                if is_container(a_val) and is_container(b_val):
                    add_item(self.left_list, key, GREEN)
                    add_item(self.right_list, key, GREEN)
                    continue

                if a_val == b_val:
                    add_item(self.left_list, key, GREEN)
                    add_item(self.right_list, key, GREEN)
                else:
                    mismatched += 1
                    left_line = f"{key}  (A={fmt_value(a_val)}, B={fmt_value(b_val)})"
                    right_line = f"{key}  (B={fmt_value(b_val)}, A={fmt_value(a_val)})"
                    add_item(self.left_list, left_line, ORANGE)
                    add_item(self.right_list, right_line, ORANGE)
        else:
            for key in sorted(both):
                add_item(self.left_list, key, GREEN)
                add_item(self.right_list, key, GREEN)

        for key in sorted(only_left):
            add_item(self.left_list, f"{key}  (missing in B)", RED)
        for key in sorted(only_right):
            add_item(self.right_list, f"{key}  (missing in A)", RED)

        if compare_values:
            self.statusBar().showMessage(
                f"Both: {len(both)} | Value diffs: {mismatched} | Only A: {len(only_left)} | Only B: {len(only_right)}",
                7000,
            )
        else:
            self.statusBar().showMessage(
                f"Both: {len(both)} | Only A: {len(only_left)} | Only B: {len(only_right)}",
                7000,
            )

    def show_about(self) -> None:
        QMessageBox.information(
            self,
            "About",
            (
                "YAML Config Comparator.\n"
                "Paste two YAML files and compare key presence.\n"
                "Green – key present in both, Red – missing in the other.\n"
                "Enable 'Compare values' to check values as well (orange = values differ)."
            ),
        )


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    win = ConfigComparator()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
