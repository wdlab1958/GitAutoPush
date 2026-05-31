"""
ConfigManager - 프로젝트 설정 관리
JSON 기반 설정 파일로 프로젝트 목록 및 환경 관리
"""

import json
import os
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict, field
from datetime import datetime


@dataclass
class ProjectConfig:
    name: str
    local_path: str
    remote_url: str
    branch: str = "main"
    location: str = "home"          # 'home' or 'office'
    auto_push: bool = True
    ollama_model: str = "llama3.2:3b"
    git_user_name: str = ""
    git_user_email: str = ""
    custom_gitignore: List[str] = field(default_factory=list)
    last_commit_at: str = ""
    created_at: str = ""


class ConfigManager:
    """앱 설정 및 프로젝트 관리"""

    def __init__(self, config_dir: str = ""):
        if not config_dir:
            config_dir = os.path.join(os.path.expanduser("~"), ".gitautopush")
        os.makedirs(config_dir, exist_ok=True)

        self.config_dir = config_dir
        self.config_file = os.path.join(config_dir, "config.json")
        self.projects_file = os.path.join(config_dir, "projects.json")
        self._ensure_files()

    def _ensure_files(self):
        """설정 파일 초기화"""
        if not os.path.exists(self.config_file):
            default_config = {
                "app_version": "1.0.0",
                "ollama_url": "http://localhost:11434",
                "ollama_model": "llama3.2:3b",
                "default_location": "home",
                "auto_push_after_commit": True,
                "git_user_name": "",
                "git_user_email": "",
                "github_pat": "",
                "theme": "dark",
                "language": "ko",
                "log_retention_days": 365
            }
            self._write_json(self.config_file, default_config)

        if not os.path.exists(self.projects_file):
            self._write_json(self.projects_file, {"projects": []})

    def _read_json(self, filepath: str) -> Dict:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def _write_json(self, filepath: str, data: Dict):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    # ── App Config ──────────────────────────────────────
    def get_config(self) -> Dict:
        return self._read_json(self.config_file)

    def update_config(self, updates: Dict):
        config = self.get_config()
        config.update(updates)
        self._write_json(self.config_file, config)

    def get_value(self, key: str, default=None):
        return self.get_config().get(key, default)

    # ── Project Management ──────────────────────────────
    def get_projects(self) -> List[ProjectConfig]:
        data = self._read_json(self.projects_file)
        projects = []
        for p in data.get("projects", []):
            try:
                projects.append(ProjectConfig(**p))
            except TypeError:
                continue
        return projects

    def get_project(self, name: str) -> Optional[ProjectConfig]:
        for p in self.get_projects():
            if p.name == name:
                return p
        return None

    def add_project(self, project: ProjectConfig) -> bool:
        data = self._read_json(self.projects_file)
        projects = data.get("projects", [])

        # 중복 체크
        for p in projects:
            if p.get("name") == project.name:
                return False

        project.created_at = datetime.now().isoformat()
        projects.append(asdict(project))
        data["projects"] = projects
        self._write_json(self.projects_file, data)
        return True

    def update_project(self, name: str, updates: Dict) -> bool:
        data = self._read_json(self.projects_file)
        projects = data.get("projects", [])

        for i, p in enumerate(projects):
            if p.get("name") == name:
                projects[i].update(updates)
                data["projects"] = projects
                self._write_json(self.projects_file, data)
                return True
        return False

    def remove_project(self, name: str) -> bool:
        data = self._read_json(self.projects_file)
        projects = data.get("projects", [])
        new_projects = [p for p in projects if p.get("name") != name]

        if len(new_projects) == len(projects):
            return False

        data["projects"] = new_projects
        self._write_json(self.projects_file, data)
        return True

    def get_project_names(self) -> List[str]:
        return [p.name for p in self.get_projects()]
