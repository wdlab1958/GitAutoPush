"""
GitAutoPush - Desktop Application
PyQt6 기반 Git 자동화 도구 (Ollama LLM 통합)
"""

import sys
import os
import threading
from datetime import datetime
from typing import Optional

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QTextEdit, QComboBox,
    QFileDialog, QTabWidget, QTableWidget, QTableWidgetItem,
    QGroupBox, QSplitter, QStatusBar, QMessageBox, QProgressBar,
    QCheckBox, QSpinBox, QHeaderView, QFrame, QDialog, QFormLayout,
    QDialogButtonBox, QPlainTextEdit
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QFont, QColor, QIcon, QPalette, QAction

# Core imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.git_manager import GitManager
from core.ollama_client import OllamaClient, OllamaConfig
from core.version_manager import VersionManager, LogManager, CommitRecord
from core.config_manager import ConfigManager, ProjectConfig


# ═══════════════════════════════════════════════════════
#  Worker Thread - 백그라운드 Git/LLM 작업
# ═══════════════════════════════════════════════════════
class WorkerThread(QThread):
    """비동기 작업 처리 스레드"""
    log_signal = pyqtSignal(str)           # 로그 메시지
    progress_signal = pyqtSignal(int)       # 진행률 (0-100)
    finished_signal = pyqtSignal(bool, str) # 완료 (성공여부, 메시지)
    gitignore_signal = pyqtSignal(list, str)  # .gitignore 패턴 결과

    def __init__(self, task: str, **kwargs):
        super().__init__()
        self.task = task
        self.kwargs = kwargs

    def run(self):
        try:
            if self.task == "full_commit_push":
                self._full_commit_push()
            elif self.task == "analyze_gitignore":
                self._analyze_gitignore()
            elif self.task == "check_ollama":
                self._check_ollama()
        except Exception as e:
            self.finished_signal.emit(False, f"Error: {str(e)}")

    def _full_commit_push(self):
        """전체 커밋 → Push 파이프라인"""
        git: GitManager = self.kwargs["git"]
        ollama: OllamaClient = self.kwargs["ollama"]
        log_mgr: LogManager = self.kwargs["log_mgr"]
        ver_mgr: VersionManager = self.kwargs["ver_mgr"]
        project: ProjectConfig = self.kwargs["project"]
        commit_msg: str = self.kwargs.get("commit_msg", "")
        auto_push: bool = self.kwargs.get("auto_push", True)

        # Step 1: Init / Check repo
        self.log_signal.emit("🔍 Checking repository...")
        self.progress_signal.emit(5)

        if not git.is_repo():
            ok, msg = git.init_repo()
            if not ok:
                self.finished_signal.emit(False, f"Repo init failed: {msg}")
                return
            self.log_signal.emit(f"  ✅ {msg}")

        # Step 2: Set remote
        self.progress_signal.emit(10)
        if project.remote_url:
            ok, msg = git.set_remote(project.remote_url)
            self.log_signal.emit(f"  🔗 {msg}")

        # Step 3: Stage all files
        self.log_signal.emit("📦 Staging changes...")
        self.progress_signal.emit(20)
        ok, msg = git.stage_all()
        if not ok:
            self.finished_signal.emit(False, f"Stage failed: {msg}")
            return
        self.log_signal.emit(f"  ✅ {msg}")

        # Step 4: Check status
        status = git.get_status()
        if status["total_changes"] == 0:
            self.finished_signal.emit(False, "Nothing to commit - working tree clean")
            return

        total = status["total_changes"]
        self.log_signal.emit(f"  📊 {total} changes detected")

        # Step 5: Get diff stats
        files_changed, insertions, deletions = git.get_diff_stats()
        self.progress_signal.emit(30)

        # Step 6: Generate commit message via LLM if not provided
        if not commit_msg:
            self.log_signal.emit("🤖 Generating commit message via LLM...")
            self.progress_signal.emit(40)

            file_list = "\n".join(
                status["staged"] + status["modified"] + status["untracked"]
            )
            diff_summary = f"{files_changed} files, +{insertions} -{deletions}"

            version = ver_mgr.get_version(project.name)
            ok, generated_msg = ollama.generate_commit_message(
                diff_summary, file_list, project.name, version
            )
            if ok:
                commit_msg = generated_msg
                self.log_signal.emit(f"  💬 Message: {commit_msg[:80]}")
            else:
                # LLM 실패 시 기본 메시지
                commit_msg = (
                    f"chore: update {project.name} - "
                    f"{files_changed} files changed (+{insertions}/-{deletions})"
                )
                self.log_signal.emit(f"  ⚠️ LLM unavailable, using default message")

        # Step 7: Commit
        self.log_signal.emit("💾 Committing...")
        self.progress_signal.emit(60)
        ok, msg, commit_hash = git.commit(commit_msg)
        if not ok:
            self.finished_signal.emit(False, f"Commit failed: {msg}")
            return
        self.log_signal.emit(f"  ✅ Committed: {commit_hash or 'OK'}")

        # Step 8: Increment version
        new_version = ver_mgr.increment_patch(project.name)
        self.log_signal.emit(f"  🏷️ Version: {new_version}")

        # Step 9: Create log record
        record = CommitRecord(
            project_name=project.name,
            repo_url=project.remote_url,
            commit_hash=commit_hash or "",
            commit_message=commit_msg,
            version=new_version,
            location=project.location,
            branch=git.get_current_branch(),
            files_changed=files_changed,
            insertions=insertions,
            deletions=deletions,
            status="committed"
        )
        log_id = log_mgr.add_log(record)
        self.progress_signal.emit(75)

        # Step 10: Push
        if auto_push:
            self.log_signal.emit("🚀 Pushing to remote...")
            self.progress_signal.emit(85)
            ok, msg = git.push()
            if ok:
                log_mgr.update_push_status(log_id)
                self.log_signal.emit(f"  ✅ {msg}")
            else:
                self.log_signal.emit(f"  ❌ Push failed: {msg}")
                self.finished_signal.emit(False, f"Committed but push failed: {msg}")
                return

        self.progress_signal.emit(100)
        self.finished_signal.emit(
            True,
            f"✅ Complete! {new_version} | {commit_hash or 'OK'} | "
            f"{files_changed} files (+{insertions}/-{deletions})"
        )

    def _analyze_gitignore(self):
        """LLM 기반 .gitignore 분석"""
        ollama: OllamaClient = self.kwargs["ollama"]
        project_path: str = self.kwargs["project_path"]

        self.log_signal.emit("🤖 Scanning project structure...")
        self.progress_signal.emit(20)

        tree = ollama.scan_project_tree(project_path)
        self.log_signal.emit(f"  📁 Scanned {len(tree.splitlines())} items")

        self.log_signal.emit("🧠 Analyzing with LLM...")
        self.progress_signal.emit(50)

        ok, patterns, explanation = ollama.analyze_gitignore(tree)

        self.progress_signal.emit(100)
        if ok:
            self.log_signal.emit(f"  ✅ Found {len(patterns)} patterns to ignore")
            self.gitignore_signal.emit(patterns, explanation)
        else:
            self.log_signal.emit(f"  ⚠️ Using fallback patterns (LLM unavailable)")
            self.gitignore_signal.emit(patterns, "Fallback patterns applied")

        self.finished_signal.emit(ok, f"Analysis complete: {len(patterns)} patterns")

    def _check_ollama(self):
        """Ollama 연결 확인"""
        ollama: OllamaClient = self.kwargs["ollama"]
        ok, msg = ollama.is_available()
        self.finished_signal.emit(ok, msg)


# ═══════════════════════════════════════════════════════
#  Gitignore Editor Dialog
# ═══════════════════════════════════════════════════════
class GitignoreDialog(QDialog):
    """LLM 분석 결과 편집 다이얼로그"""

    def __init__(self, patterns: list, explanation: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📋 .gitignore Editor (LLM Analyzed)")
        self.setMinimumSize(600, 500)
        self.patterns = patterns
        self.result_patterns = []

        layout = QVBoxLayout(self)

        # 설명
        info_label = QLabel(f"🤖 LLM Analysis Result — {len(patterns)} patterns found")
        info_label.setStyleSheet("font-weight: bold; font-size: 14px; padding: 8px;")
        layout.addWidget(info_label)

        # 패턴 편집기
        self.editor = QPlainTextEdit()
        self.editor.setPlainText("\n".join(patterns))
        self.editor.setStyleSheet("""
            QPlainTextEdit {
                font-family: 'JetBrains Mono', 'Consolas', 'Courier New', monospace;
                font-size: 13px;
                background: #1e1e2e;
                color: #cdd6f4;
                padding: 10px;
                border: 1px solid #45475a;
                border-radius: 6px;
            }
        """)
        layout.addWidget(self.editor)

        # LLM 설명
        if explanation:
            exp_label = QLabel("💡 LLM Explanation:")
            exp_label.setStyleSheet("font-weight: bold; margin-top: 8px;")
            layout.addWidget(exp_label)

            exp_text = QLabel(explanation[:500])
            exp_text.setWordWrap(True)
            exp_text.setStyleSheet("color: #a6adc8; padding: 4px;")
            layout.addWidget(exp_text)

        # 버튼
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept(self):
        text = self.editor.toPlainText()
        self.result_patterns = [
            line.strip() for line in text.split("\n")
            if line.strip() and not line.strip().startswith("#")
        ]
        self.accept()


# ═══════════════════════════════════════════════════════
#  Main Window
# ═══════════════════════════════════════════════════════
class MainWindow(QMainWindow):
    """GitAutoPush 메인 윈도우"""

    def __init__(self):
        super().__init__()

        # Core managers
        self.config_mgr = ConfigManager()
        self.log_mgr = LogManager()
        self.ver_mgr = VersionManager()
        self.ollama = OllamaClient(OllamaConfig(
            base_url=self.config_mgr.get_value("ollama_url", "http://localhost:11434"),
            model=self.config_mgr.get_value("ollama_model", "llama3.1:8b")
        ))
        self.git = GitManager()
        self.worker: Optional[WorkerThread] = None
        self.current_project: Optional[ProjectConfig] = None

        self._init_ui()
        self._apply_dark_theme()
        self._load_projects()
        self._check_ollama_status()

    def _init_ui(self):
        """UI 초기화"""
        self.setWindowTitle("🚀 GitAutoPush - Automated Git Workflow")
        self.setMinimumSize(1100, 780)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # ── Header ──────────────────────────────────────
        header = QHBoxLayout()
        title = QLabel("🚀 GitAutoPush")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #89b4fa;")
        header.addWidget(title)

        self.ollama_status = QLabel("⏳ Checking Ollama...")
        self.ollama_status.setStyleSheet("font-size: 12px; color: #a6adc8;")
        header.addStretch()
        header.addWidget(self.ollama_status)
        main_layout.addLayout(header)

        # ── Tab Widget ──────────────────────────────────
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #45475a; border-radius: 6px; }
            QTabBar::tab { 
                padding: 8px 20px; margin: 2px;
                background: #313244; color: #cdd6f4;
                border-radius: 4px;
            }
            QTabBar::tab:selected { background: #45475a; color: #89b4fa; }
        """)
        main_layout.addWidget(self.tabs)

        # Tab 1: Dashboard
        self.tabs.addTab(self._create_dashboard_tab(), "📋 Dashboard")
        # Tab 2: Commit Log
        self.tabs.addTab(self._create_log_tab(), "📜 Commit Log")
        # Tab 3: Settings
        self.tabs.addTab(self._create_settings_tab(), "⚙️ Settings")

        # ── Progress & Status ───────────────────────────
        bottom_layout = QVBoxLayout()

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #45475a; border-radius: 4px;
                background: #1e1e2e; text-align: center; color: #cdd6f4;
                height: 20px;
            }
            QProgressBar::chunk { background: #89b4fa; border-radius: 3px; }
        """)
        bottom_layout.addWidget(self.progress_bar)

        self.status_bar = QStatusBar()
        self.status_bar.setStyleSheet("color: #a6adc8; font-size: 11px;")
        self.status_bar.showMessage("Ready")
        self.setStatusBar(self.status_bar)

        main_layout.addLayout(bottom_layout)

    def _create_dashboard_tab(self) -> QWidget:
        """대시보드 탭"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)

        # ── Project Selection ───────────────────────────
        proj_group = QGroupBox("📁 Project")
        proj_group.setStyleSheet(self._group_style())
        proj_layout = QHBoxLayout(proj_group)

        self.project_combo = QComboBox()
        self.project_combo.setMinimumWidth(200)
        self.project_combo.currentTextChanged.connect(self._on_project_changed)
        proj_layout.addWidget(QLabel("Project:"))
        proj_layout.addWidget(self.project_combo)

        btn_new = QPushButton("➕ New Project")
        btn_new.clicked.connect(self._add_project_dialog)
        btn_new.setStyleSheet(self._btn_style("#a6e3a1"))
        proj_layout.addWidget(btn_new)

        btn_remove = QPushButton("🗑️ Remove")
        btn_remove.clicked.connect(self._remove_project)
        btn_remove.setStyleSheet(self._btn_style("#f38ba8"))
        proj_layout.addWidget(btn_remove)

        proj_layout.addStretch()

        # 위치 선택
        proj_layout.addWidget(QLabel("📍 Location:"))
        self.location_combo = QComboBox()
        self.location_combo.addItems(["🏠 Home", "🏢 Office"])
        self.location_combo.setMinimumWidth(120)
        proj_layout.addWidget(self.location_combo)

        layout.addWidget(proj_group)

        # ── Git Config ──────────────────────────────────
        git_group = QGroupBox("🔗 Git Configuration")
        git_group.setStyleSheet(self._group_style())
        git_layout = QVBoxLayout(git_group)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Remote URL:"))
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://github.com/username/repo.git")
        row1.addWidget(self.url_input)
        git_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Local Path:"))
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("/home/user/projects/my-project")
        row2.addWidget(self.path_input)
        btn_browse = QPushButton("📂 Browse")
        btn_browse.clicked.connect(self._browse_folder)
        btn_browse.setStyleSheet(self._btn_style("#89b4fa"))
        row2.addWidget(btn_browse)
        git_layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Branch:"))
        self.branch_input = QLineEdit("main")
        self.branch_input.setMaximumWidth(150)
        row3.addWidget(self.branch_input)
        row3.addStretch()

        self.version_label = QLabel("Version: v1.0.0-000")
        self.version_label.setStyleSheet("font-weight: bold; color: #f9e2af; font-size: 13px;")
        row3.addWidget(self.version_label)
        git_layout.addLayout(row3)

        layout.addWidget(git_group)

        # ── Commit Section ──────────────────────────────
        commit_group = QGroupBox("💬 Commit")
        commit_group.setStyleSheet(self._group_style())
        commit_layout = QVBoxLayout(commit_group)

        msg_row = QHBoxLayout()
        msg_row.addWidget(QLabel("Message:"))
        self.commit_msg_input = QLineEdit()
        self.commit_msg_input.setPlaceholderText("Leave empty for AI-generated message (Ollama)")
        msg_row.addWidget(self.commit_msg_input)
        commit_layout.addLayout(msg_row)

        option_row = QHBoxLayout()
        self.auto_push_check = QCheckBox("Auto Push after Commit")
        self.auto_push_check.setChecked(True)
        option_row.addWidget(self.auto_push_check)
        option_row.addStretch()
        commit_layout.addLayout(option_row)

        layout.addWidget(commit_group)

        # ── Action Buttons ──────────────────────────────
        btn_layout = QHBoxLayout()

        btn_analyze = QPushButton("🧠 Analyze .gitignore (LLM)")
        btn_analyze.clicked.connect(self._analyze_gitignore)
        btn_analyze.setStyleSheet(self._btn_style("#cba6f7", large=True))
        btn_analyze.setMinimumHeight(44)
        btn_layout.addWidget(btn_analyze)

        btn_commit = QPushButton("🚀 Commit & Push")
        btn_commit.clicked.connect(self._do_commit_push)
        btn_commit.setStyleSheet(self._btn_style("#a6e3a1", large=True))
        btn_commit.setMinimumHeight(44)
        btn_layout.addWidget(btn_commit)

        layout.addWidget(self._hline())
        layout.addLayout(btn_layout)

        # ── Live Log ────────────────────────────────────
        self.live_log = QTextEdit()
        self.live_log.setReadOnly(True)
        self.live_log.setMaximumHeight(200)
        self.live_log.setStyleSheet("""
            QTextEdit {
                font-family: 'JetBrains Mono', 'Consolas', monospace;
                font-size: 12px;
                background: #11111b;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 8px;
            }
        """)
        layout.addWidget(self.live_log)

        return tab

    def _create_log_tab(self) -> QWidget:
        """커밋 로그 탭"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 필터
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filter:"))

        self.log_project_filter = QComboBox()
        self.log_project_filter.addItem("All Projects")
        filter_row.addWidget(self.log_project_filter)

        self.log_location_filter = QComboBox()
        self.log_location_filter.addItems(["All Locations", "🏠 Home", "🏢 Office"])
        filter_row.addWidget(self.log_location_filter)

        btn_refresh = QPushButton("🔄 Refresh")
        btn_refresh.clicked.connect(self._refresh_logs)
        btn_refresh.setStyleSheet(self._btn_style("#89b4fa"))
        filter_row.addWidget(btn_refresh)

        btn_export = QPushButton("📥 Export CSV")
        btn_export.clicked.connect(self._export_logs)
        btn_export.setStyleSheet(self._btn_style("#f9e2af"))
        filter_row.addWidget(btn_export)

        filter_row.addStretch()
        layout.addLayout(filter_row)

        # 테이블
        self.log_table = QTableWidget()
        self.log_table.setColumnCount(10)
        self.log_table.setHorizontalHeaderLabels([
            "Date", "Project", "Version", "Location", "Branch",
            "Hash", "Message", "Files", "+/-", "Status"
        ])
        self.log_table.horizontalHeader().setStretchLastSection(True)
        self.log_table.setAlternatingRowColors(True)
        self.log_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.log_table.verticalHeader().setDefaultSectionSize(32)
        self.log_table.setStyleSheet("""
            QTableWidget {
                background: #1e1e2e; color: #cdd6f4;
                gridline-color: #313244;
                border: 1px solid #45475a;
                border-radius: 6px;
            }
            QTableWidget::item { padding: 4px 8px; }
            QTableWidget::item:selected { background: #45475a; }
            QHeaderView::section {
                background: #313244; color: #89b4fa;
                padding: 6px; border: 1px solid #45475a;
                font-weight: bold;
            }
        """)

        # 컬럼 너비 조정
        header = self.log_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.log_table.setColumnWidth(0, 160)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.log_table.setColumnWidth(5, 80)

        layout.addWidget(self.log_table)

        # 통계
        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet("color: #a6adc8; font-size: 12px; padding: 4px;")
        layout.addWidget(self.stats_label)

        return tab

    def _create_settings_tab(self) -> QWidget:
        """설정 탭"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(12)

        # Ollama Settings
        ollama_group = QGroupBox("🤖 Ollama (Local LLM)")
        ollama_group.setStyleSheet(self._group_style())
        o_layout = QFormLayout(ollama_group)

        self.ollama_url_input = QLineEdit(
            self.config_mgr.get_value("ollama_url", "http://localhost:11434")
        )
        o_layout.addRow("Server URL:", self.ollama_url_input)

        self.ollama_model_combo = QComboBox()
        self.ollama_model_combo.setEditable(True)
        self.ollama_model_combo.addItems([
            "llama3.1:8b", "llama3.2:3b", "codellama:13b",
            "qwen2.5:7b", "qwen2.5-coder:7b", "mistral:7b",
            "gemma2:9b", "deepseek-coder-v2:16b"
        ])
        current_model = self.config_mgr.get_value("ollama_model", "llama3.1:8b")
        self.ollama_model_combo.setCurrentText(current_model)
        o_layout.addRow("Model:", self.ollama_model_combo)

        btn_test = QPushButton("🔍 Test Connection")
        btn_test.clicked.connect(self._check_ollama_status)
        btn_test.setStyleSheet(self._btn_style("#89b4fa"))
        o_layout.addRow("", btn_test)

        layout.addWidget(ollama_group)

        # Git Settings
        git_group = QGroupBox("👤 Git Default User")
        git_group.setStyleSheet(self._group_style())
        g_layout = QFormLayout(git_group)

        self.git_name_input = QLineEdit(
            self.config_mgr.get_value("git_user_name", "")
        )
        self.git_name_input.setPlaceholderText("Your Name")
        g_layout.addRow("Name:", self.git_name_input)

        self.git_email_input = QLineEdit(
            self.config_mgr.get_value("git_user_email", "")
        )
        self.git_email_input.setPlaceholderText("you@email.com")
        g_layout.addRow("Email:", self.git_email_input)

        layout.addWidget(git_group)

        # Save Button
        btn_save = QPushButton("💾 Save Settings")
        btn_save.clicked.connect(self._save_settings)
        btn_save.setStyleSheet(self._btn_style("#a6e3a1", large=True))
        btn_save.setMinimumHeight(40)
        layout.addWidget(btn_save)

        layout.addStretch()
        return tab

    # ═══════════════════════════════════════════════════
    #  Actions
    # ═══════════════════════════════════════════════════
    def _add_project_dialog(self):
        """새 프로젝트 추가 다이얼로그"""
        dialog = QDialog(self)
        dialog.setWindowTitle("➕ Add New Project")
        dialog.setMinimumWidth(500)

        form = QFormLayout(dialog)

        name_input = QLineEdit()
        name_input.setPlaceholderText("my-awesome-project")
        form.addRow("Project Name:", name_input)

        url_input = QLineEdit()
        url_input.setPlaceholderText("https://github.com/user/repo.git")
        form.addRow("Remote URL:", url_input)

        path_row = QHBoxLayout()
        path_input = QLineEdit()
        path_input.setPlaceholderText("/home/user/project")
        path_row.addWidget(path_input)
        btn_b = QPushButton("📂")
        btn_b.clicked.connect(lambda: path_input.setText(
            QFileDialog.getExistingDirectory(dialog, "Select Project Folder")
        ))
        path_row.addWidget(btn_b)
        form.addRow("Local Path:", path_row)

        branch_input = QLineEdit("main")
        form.addRow("Branch:", branch_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = name_input.text().strip()
            if not name:
                QMessageBox.warning(self, "Error", "Project name is required")
                return

            project = ProjectConfig(
                name=name,
                local_path=path_input.text().strip(),
                remote_url=url_input.text().strip(),
                branch=branch_input.text().strip() or "main",
                location="home" if self.location_combo.currentIndex() == 0 else "office"
            )

            if self.config_mgr.add_project(project):
                self._load_projects()
                self.project_combo.setCurrentText(name)
                self._log(f"✅ Project '{name}' added")
            else:
                QMessageBox.warning(self, "Error", f"Project '{name}' already exists")

    def _remove_project(self):
        """프로젝트 삭제"""
        name = self.project_combo.currentText()
        if not name:
            return

        reply = QMessageBox.question(
            self, "Confirm",
            f"Remove project '{name}' from GitAutoPush?\n(This won't delete any files)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.config_mgr.remove_project(name)
            self._load_projects()
            self._log(f"🗑️ Project '{name}' removed")

    def _browse_folder(self):
        """폴더 선택"""
        folder = QFileDialog.getExistingDirectory(self, "Select Project Folder")
        if folder:
            self.path_input.setText(folder)

    def _on_project_changed(self, name: str):
        """프로젝트 선택 변경"""
        project = self.config_mgr.get_project(name)
        if not project:
            return

        self.current_project = project
        self.url_input.setText(project.remote_url)
        self.path_input.setText(project.local_path)
        self.branch_input.setText(project.branch)
        self.location_combo.setCurrentIndex(
            0 if project.location == "home" else 1
        )

        # 버전 표시
        version = self.ver_mgr.get_version(name)
        self.version_label.setText(f"Version: {version}")

        # Git 매니저 업데이트
        self.git.project_path = project.local_path
        self.git.remote_url = project.remote_url

    def _analyze_gitignore(self):
        """LLM으로 .gitignore 분석"""
        path = self.path_input.text().strip()
        if not path or not os.path.isdir(path):
            QMessageBox.warning(self, "Error", "Please select a valid project folder first")
            return

        self._start_worker("analyze_gitignore",
                           ollama=self.ollama,
                           project_path=path)

    def _on_gitignore_result(self, patterns: list, explanation: str):
        """LLM 분석 결과 표시"""
        dialog = GitignoreDialog(patterns, explanation, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if dialog.result_patterns:
                path = self.path_input.text().strip()
                if path:
                    self.git.project_path = path
                    self.git.write_gitignore(dialog.result_patterns)
                    self._log(f"✅ .gitignore updated with {len(dialog.result_patterns)} patterns")

    def _do_commit_push(self):
        """커밋 & Push 실행"""
        path = self.path_input.text().strip()
        url = self.url_input.text().strip()
        name = self.project_combo.currentText()

        if not path or not os.path.isdir(path):
            QMessageBox.warning(self, "Error", "Please select a valid project folder")
            return

        if not name:
            QMessageBox.warning(self, "Error", "Please select or create a project")
            return

        # 현재 설정 업데이트
        location = "home" if self.location_combo.currentIndex() == 0 else "office"
        project = ProjectConfig(
            name=name,
            local_path=path,
            remote_url=url,
            branch=self.branch_input.text().strip() or "main",
            location=location
        )
        self.config_mgr.update_project(name, {
            "local_path": path,
            "remote_url": url,
            "location": location,
            "last_commit_at": datetime.now().isoformat()
        })

        self.git.project_path = path
        self.git.remote_url = url

        self._start_worker(
            "full_commit_push",
            git=self.git,
            ollama=self.ollama,
            log_mgr=self.log_mgr,
            ver_mgr=self.ver_mgr,
            project=project,
            commit_msg=self.commit_msg_input.text().strip(),
            auto_push=self.auto_push_check.isChecked()
        )

    def _check_ollama_status(self):
        """Ollama 상태 확인"""
        url = getattr(self, 'ollama_url_input', None)
        if url:
            self.ollama.config.base_url = url.text().strip()
        model = getattr(self, 'ollama_model_combo', None)
        if model:
            self.ollama.config.model = model.currentText().strip()

        # 동기 확인 (빠르므로)
        ok, msg = self.ollama.is_available()
        if ok:
            self.ollama_status.setText(f"✅ {msg}")
            self.ollama_status.setStyleSheet("font-size: 12px; color: #a6e3a1;")
        else:
            self.ollama_status.setText(f"❌ Ollama: Disconnected")
            self.ollama_status.setStyleSheet("font-size: 12px; color: #f38ba8;")
            self._log(f"⚠️ Ollama: {msg}")

    def _refresh_logs(self):
        """로그 테이블 새로고침"""
        project_filter = self.log_project_filter.currentText()
        location_filter = self.log_location_filter.currentText()

        project = "" if project_filter == "All Projects" else project_filter
        location = ""
        if "Home" in location_filter:
            location = "home"
        elif "Office" in location_filter:
            location = "office"

        logs = self.log_mgr.get_logs(project_name=project, location=location)

        self.log_table.setRowCount(len(logs))
        for i, log in enumerate(logs):
            loc_icon = "🏠" if log["location"] == "home" else "🏢"
            status_icon = "✅" if log["status"] == "pushed" else "⏳"

            items = [
                log.get("committed_at", "")[:19],
                log.get("project_name", ""),
                log.get("version", ""),
                f"{loc_icon} {log.get('location', '').title()}",
                log.get("branch", ""),
                log.get("commit_hash", "")[:8],
                log.get("commit_message", "")[:60],
                str(log.get("files_changed", 0)),
                f"+{log.get('insertions', 0)}/-{log.get('deletions', 0)}",
                f"{status_icon} {log.get('status', '').title()}"
            ]

            for j, text in enumerate(items):
                item = QTableWidgetItem(str(text))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.log_table.setItem(i, j, item)

        # 통계 업데이트
        stats = self.log_mgr.get_stats(project)
        self.stats_label.setText(
            f"📊 Total: {stats['total_commits']} commits | "
            f"🏠 Home: {stats['home_commits']} | "
            f"🏢 Office: {stats['office_commits']}"
        )

    def _export_logs(self):
        """로그 CSV 내보내기"""
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export Logs", "commit_logs.csv", "CSV Files (*.csv)"
        )
        if filepath:
            project = self.log_project_filter.currentText()
            project = "" if project == "All Projects" else project
            if self.log_mgr.export_logs_csv(filepath, project):
                self._log(f"📥 Logs exported to {filepath}")
            else:
                QMessageBox.warning(self, "Error", "No logs to export")

    def _save_settings(self):
        """설정 저장"""
        self.config_mgr.update_config({
            "ollama_url": self.ollama_url_input.text().strip(),
            "ollama_model": self.ollama_model_combo.currentText().strip(),
            "git_user_name": self.git_name_input.text().strip(),
            "git_user_email": self.git_email_input.text().strip(),
        })

        # Ollama 클라이언트 업데이트
        self.ollama.config.base_url = self.ollama_url_input.text().strip()
        self.ollama.config.model = self.ollama_model_combo.currentText().strip()

        self._log("💾 Settings saved")
        self._check_ollama_status()

    # ═══════════════════════════════════════════════════
    #  Helper Methods
    # ═══════════════════════════════════════════════════
    def _load_projects(self):
        """프로젝트 목록 로드"""
        self.project_combo.clear()
        self.log_project_filter.clear()
        self.log_project_filter.addItem("All Projects")

        for name in self.config_mgr.get_project_names():
            self.project_combo.addItem(name)
            self.log_project_filter.addItem(name)

    def _start_worker(self, task: str, **kwargs):
        """Worker 스레드 시작"""
        if self.worker and self.worker.isRunning():
            self._log("⚠️ Another task is running...")
            return

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        self.worker = WorkerThread(task, **kwargs)
        self.worker.log_signal.connect(self._log)
        self.worker.progress_signal.connect(self.progress_bar.setValue)
        self.worker.finished_signal.connect(self._on_worker_finished)
        self.worker.gitignore_signal.connect(self._on_gitignore_result)
        self.worker.start()

    def _on_worker_finished(self, success: bool, message: str):
        """Worker 완료 처리"""
        self.progress_bar.setVisible(False)
        if success:
            self._log(f"\n{'='*50}\n{message}\n{'='*50}")
            self.status_bar.showMessage(f"✅ {message}", 10000)
            # 버전 갱신
            name = self.project_combo.currentText()
            if name:
                version = self.ver_mgr.get_version(name)
                self.version_label.setText(f"Version: {version}")
            # 로그 새로고침
            self._refresh_logs()
        else:
            self._log(f"\n❌ {message}")
            self.status_bar.showMessage(f"❌ {message}", 10000)

    def _log(self, message: str):
        """실시간 로그 추가"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.live_log.append(f"[{timestamp}] {message}")
        # 자동 스크롤
        scrollbar = self.live_log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _hline(self) -> QFrame:
        """구분선"""
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #45475a;")
        return line

    # ═══════════════════════════════════════════════════
    #  Styling
    # ═══════════════════════════════════════════════════
    def _apply_dark_theme(self):
        """Catppuccin Mocha 다크 테마"""
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #1e1e2e;
                color: #cdd6f4;
                font-family: 'Segoe UI', 'Noto Sans KR', sans-serif;
                font-size: 13px;
            }
            QLineEdit, QComboBox, QSpinBox {
                background: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 5px;
                padding: 6px 10px;
                min-height: 24px;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #89b4fa;
            }
            QComboBox::drop-down {
                border: none;
                padding-right: 8px;
            }
            QComboBox QAbstractItemView {
                background: #313244;
                color: #cdd6f4;
                selection-background-color: #45475a;
            }
            QCheckBox {
                spacing: 8px;
                color: #cdd6f4;
            }
            QCheckBox::indicator {
                width: 18px; height: 18px;
                border: 2px solid #45475a;
                border-radius: 4px;
                background: #313244;
            }
            QCheckBox::indicator:checked {
                background: #89b4fa;
                border-color: #89b4fa;
            }
            QScrollBar:vertical {
                background: #1e1e2e;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: #45475a;
                border-radius: 5px;
                min-height: 30px;
            }
            QLabel { color: #cdd6f4; }
        """)

    def _group_style(self) -> str:
        return """
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                color: #89b4fa;
                border: 1px solid #45475a;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 18px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 6px;
            }
        """

    def _btn_style(self, color: str, large: bool = False) -> str:
        size = "font-size: 14px; font-weight: bold;" if large else "font-size: 12px;"
        return f"""
            QPushButton {{
                background: {color}22;
                color: {color};
                border: 1px solid {color}66;
                border-radius: 6px;
                padding: 6px 16px;
                {size}
            }}
            QPushButton:hover {{
                background: {color}44;
                border-color: {color};
            }}
            QPushButton:pressed {{
                background: {color}66;
            }}
        """


# ═══════════════════════════════════════════════════════
#  Entry Point
# ═══════════════════════════════════════════════════════
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("GitAutoPush")
    app.setApplicationVersion("1.0.0")

    # High DPI 지원
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
