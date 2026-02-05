"""
VersionManager & LogManager - 버전 관리 및 커밋 로그 기록
SQLite 기반 영구 저장, 자동 버전 증가
"""

import sqlite3
import os
import json
from datetime import datetime
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass, asdict


@dataclass
class CommitRecord:
    project_name: str
    repo_url: str
    commit_hash: str
    commit_message: str
    version: str
    location: str  # 'home' or 'office'
    branch: str
    files_changed: int
    insertions: int
    deletions: int
    status: str  # 'committed', 'pushed', 'failed'
    committed_at: Optional[str] = None
    pushed_at: Optional[str] = None
    id: Optional[int] = None


class LogManager:
    """SQLite 기반 커밋 로그 관리"""

    def __init__(self, db_path: str = ""):
        if not db_path:
            app_dir = os.path.join(os.path.expanduser("~"), ".gitautopush")
            os.makedirs(app_dir, exist_ok=True)
            db_path = os.path.join(app_dir, "commit_logs.db")

        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """데이터베이스 테이블 초기화"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS commit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_name TEXT NOT NULL,
                    repo_url TEXT,
                    commit_hash TEXT,
                    commit_message TEXT,
                    version TEXT,
                    location TEXT CHECK(location IN ('home', 'office', 'other')),
                    branch TEXT DEFAULT 'main',
                    files_changed INTEGER DEFAULT 0,
                    insertions INTEGER DEFAULT 0,
                    deletions INTEGER DEFAULT 0,
                    committed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    pushed_at DATETIME,
                    status TEXT CHECK(status IN ('committed', 'pushed', 'failed'))
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS project_versions (
                    project_name TEXT PRIMARY KEY,
                    major INTEGER DEFAULT 1,
                    minor INTEGER DEFAULT 0,
                    patch INTEGER DEFAULT 0,
                    build INTEGER DEFAULT 0,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_logs_project
                ON commit_logs(project_name)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_logs_date
                ON commit_logs(committed_at)
            """)

    def add_log(self, record: CommitRecord) -> int:
        """커밋 로그 추가"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                INSERT INTO commit_logs 
                (project_name, repo_url, commit_hash, commit_message, version,
                 location, branch, files_changed, insertions, deletions,
                 committed_at, pushed_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.project_name, record.repo_url, record.commit_hash,
                record.commit_message, record.version, record.location,
                record.branch, record.files_changed, record.insertions,
                record.deletions,
                record.committed_at or datetime.now().isoformat(),
                record.pushed_at, record.status
            ))
            return cursor.lastrowid

    def update_push_status(self, log_id: int) -> bool:
        """Push 완료 상태 업데이트"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE commit_logs 
                SET status = 'pushed', pushed_at = ?
                WHERE id = ?
            """, (datetime.now().isoformat(), log_id))
            return True

    def get_logs(self, project_name: str = "", limit: int = 50,
                 location: str = "") -> List[Dict]:
        """커밋 로그 조회"""
        query = "SELECT * FROM commit_logs WHERE 1=1"
        params = []

        if project_name:
            query += " AND project_name = ?"
            params.append(project_name)
        if location:
            query += " AND location = ?"
            params.append(location)

        query += " ORDER BY committed_at DESC LIMIT ?"
        params.append(limit)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def get_stats(self, project_name: str = "") -> Dict:
        """프로젝트 통계"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            query_base = "FROM commit_logs"
            params = []
            if project_name:
                query_base += " WHERE project_name = ?"
                params.append(project_name)

            total = conn.execute(
                f"SELECT COUNT(*) as cnt {query_base}", params
            ).fetchone()["cnt"]

            home_count = conn.execute(
                f"SELECT COUNT(*) as cnt {query_base}"
                + (" AND" if project_name else " WHERE") + " location = 'home'",
                params
            ).fetchone()["cnt"]

            office_count = conn.execute(
                f"SELECT COUNT(*) as cnt {query_base}"
                + (" AND" if project_name else " WHERE") + " location = 'office'",
                params
            ).fetchone()["cnt"]

            return {
                "total_commits": total,
                "home_commits": home_count,
                "office_commits": office_count,
            }

    def export_logs_csv(self, filepath: str, project_name: str = "") -> bool:
        """로그를 CSV로 내보내기"""
        import csv
        logs = self.get_logs(project_name=project_name, limit=10000)
        if not logs:
            return False

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=logs[0].keys())
            writer.writeheader()
            writer.writerows(logs)
        return True


class VersionManager:
    """시맨틱 버전 관리 (자동 증가)"""

    def __init__(self, db_path: str = ""):
        if not db_path:
            app_dir = os.path.join(os.path.expanduser("~"), ".gitautopush")
            os.makedirs(app_dir, exist_ok=True)
            db_path = os.path.join(app_dir, "commit_logs.db")

        self.db_path = db_path

    def get_version(self, project_name: str) -> str:
        """현재 버전 문자열 조회"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM project_versions WHERE project_name = ?",
                (project_name,)
            ).fetchone()

            if row:
                return f"v{row['major']}.{row['minor']}.{row['patch']}-{row['build']:03d}"
            else:
                # 새 프로젝트 초기화
                conn.execute(
                    "INSERT INTO project_versions (project_name) VALUES (?)",
                    (project_name,)
                )
                return "v1.0.0-000"

    def increment_patch(self, project_name: str) -> str:
        """패치 버전 + 빌드 번호 자동 증가"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM project_versions WHERE project_name = ?",
                (project_name,)
            ).fetchone()

            if row:
                new_patch = row["patch"] + 1
                new_build = row["build"] + 1
                conn.execute("""
                    UPDATE project_versions 
                    SET patch = ?, build = ?, updated_at = ?
                    WHERE project_name = ?
                """, (new_patch, new_build, datetime.now().isoformat(), project_name))
                return f"v{row['major']}.{row['minor']}.{new_patch}-{new_build:03d}"
            else:
                conn.execute(
                    "INSERT INTO project_versions (project_name, build) VALUES (?, 1)",
                    (project_name,)
                )
                return "v1.0.0-001"

    def set_version(self, project_name: str, major: int, minor: int,
                    patch: int = 0) -> str:
        """수동 버전 설정"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT build FROM project_versions WHERE project_name = ?",
                (project_name,)
            ).fetchone()

            build = (row["build"] if row else 0)

            conn.execute("""
                INSERT INTO project_versions (project_name, major, minor, patch, build, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_name) DO UPDATE SET
                    major = ?, minor = ?, patch = ?, updated_at = ?
            """, (
                project_name, major, minor, patch, build, datetime.now().isoformat(),
                major, minor, patch, datetime.now().isoformat()
            ))
            return f"v{major}.{minor}.{patch}-{build:03d}"

    def get_all_versions(self) -> List[Dict]:
        """모든 프로젝트의 버전 정보"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM project_versions ORDER BY updated_at DESC"
            ).fetchall()
            return [dict(row) for row in rows]
