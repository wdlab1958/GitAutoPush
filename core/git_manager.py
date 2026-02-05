"""
GitManager - Git 작업 자동화 코어 모듈
subprocess 기반으로 안정적인 Git CLI 래핑
"""

import subprocess
import os
import re
from datetime import datetime
from typing import Optional, Tuple, List, Dict


class GitManager:
    """Git 작업을 자동화하는 매니저 클래스"""

    def __init__(self, project_path: str = "", remote_url: str = ""):
        self.project_path = project_path
        self.remote_url = remote_url

    def _run_git(self, args: List[str], cwd: Optional[str] = None) -> Tuple[bool, str, str]:
        """Git 명령 실행 래퍼"""
        cmd = ["git"] + args
        work_dir = cwd or self.project_path
        try:
            result = subprocess.run(
                cmd,
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=120
            )
            return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
        except subprocess.TimeoutExpired:
            return False, "", "Git command timed out (120s)"
        except FileNotFoundError:
            return False, "", "Git is not installed or not in PATH"
        except Exception as e:
            return False, "", str(e)

    def is_git_installed(self) -> bool:
        """Git 설치 여부 확인"""
        ok, out, _ = self._run_git(["--version"], cwd="/tmp")
        return ok and "git version" in out

    def is_repo(self) -> bool:
        """현재 경로가 Git 저장소인지 확인"""
        if not self.project_path or not os.path.isdir(self.project_path):
            return False
        ok, _, _ = self._run_git(["rev-parse", "--is-inside-work-tree"])
        return ok

    def init_repo(self) -> Tuple[bool, str]:
        """새 Git 저장소 초기화"""
        if not os.path.isdir(self.project_path):
            return False, f"Directory not found: {self.project_path}"

        if self.is_repo():
            return True, "Already a git repository"

        ok, out, err = self._run_git(["init"])
        if not ok:
            return False, f"Init failed: {err}"

        # 기본 브랜치를 main으로 설정
        self._run_git(["branch", "-M", "main"])
        return True, "Repository initialized"

    def set_remote(self, url: str, name: str = "origin") -> Tuple[bool, str]:
        """원격 저장소 설정"""
        self.remote_url = url

        # 기존 remote 확인
        ok, out, _ = self._run_git(["remote", "-v"])
        if name in (out or ""):
            # remote URL 업데이트
            ok, _, err = self._run_git(["remote", "set-url", name, url])
            if ok:
                return True, f"Remote '{name}' updated to {url}"
            return False, f"Failed to update remote: {err}"

        # 새 remote 추가
        ok, _, err = self._run_git(["remote", "add", name, url])
        if ok:
            return True, f"Remote '{name}' added: {url}"
        return False, f"Failed to add remote: {err}"

    def get_current_branch(self) -> str:
        """현재 브랜치명 조회"""
        ok, out, _ = self._run_git(["branch", "--show-current"])
        return out if ok else "main"

    def get_status(self) -> Dict:
        """Git 상태 조회"""
        result = {
            "staged": [],
            "modified": [],
            "untracked": [],
            "deleted": [],
            "total_changes": 0
        }

        ok, out, _ = self._run_git(["status", "--porcelain"])
        if not ok or not out:
            return result

        for line in out.split("\n"):
            if not line.strip():
                continue
            status = line[:2]
            filepath = line[3:]

            if status[0] in ("A", "M", "R"):
                result["staged"].append(filepath)
            if status[1] == "M":
                result["modified"].append(filepath)
            if status == "??":
                result["untracked"].append(filepath)
            if "D" in status:
                result["deleted"].append(filepath)

        result["total_changes"] = (
            len(result["staged"]) + len(result["modified"]) +
            len(result["untracked"]) + len(result["deleted"])
        )
        return result

    def stage_all(self) -> Tuple[bool, str]:
        """모든 변경사항 스테이징"""
        ok, out, err = self._run_git(["add", "-A"])
        if ok:
            return True, "All changes staged"
        return False, f"Stage failed: {err}"

    def stage_files(self, files: List[str]) -> Tuple[bool, str]:
        """특정 파일만 스테이징"""
        if not files:
            return False, "No files to stage"
        ok, out, err = self._run_git(["add"] + files)
        if ok:
            return True, f"Staged {len(files)} files"
        return False, f"Stage failed: {err}"

    def commit(self, message: str) -> Tuple[bool, str, Optional[str]]:
        """커밋 수행, 커밋 해시 반환"""
        if not message.strip():
            return False, "Commit message cannot be empty", None

        ok, out, err = self._run_git(["commit", "-m", message])
        if not ok:
            if "nothing to commit" in (err + out):
                return False, "Nothing to commit", None
            return False, f"Commit failed: {err}", None

        # 커밋 해시 추출
        commit_hash = None
        hash_match = re.search(r'\[[\w/]+ ([a-f0-9]+)\]', out)
        if hash_match:
            commit_hash = hash_match.group(1)

        return True, out, commit_hash

    def push(self, remote: str = "origin", branch: Optional[str] = None,
             set_upstream: bool = True) -> Tuple[bool, str]:
        """Push 수행"""
        branch = branch or self.get_current_branch()
        args = ["push"]

        if set_upstream:
            args.extend(["-u", remote, branch])
        else:
            args.extend([remote, branch])

        ok, out, err = self._run_git(args)
        if ok:
            return True, f"Pushed to {remote}/{branch}"

        # 인증 문제 감지
        if "Authentication" in err or "403" in err:
            return False, "Authentication failed. Check your Git credentials."
        if "rejected" in err:
            return False, f"Push rejected (pull first?): {err}"

        return False, f"Push failed: {err}"

    def get_diff_stats(self) -> Tuple[int, int, int]:
        """변경 통계: (files_changed, insertions, deletions)"""
        ok, out, _ = self._run_git(["diff", "--cached", "--stat"])
        if not ok or not out:
            return 0, 0, 0

        # 마지막 줄에서 통계 추출
        lines = out.strip().split("\n")
        if not lines:
            return 0, 0, 0

        last_line = lines[-1]
        files = insertions = deletions = 0

        f_match = re.search(r'(\d+) files? changed', last_line)
        i_match = re.search(r'(\d+) insertions?', last_line)
        d_match = re.search(r'(\d+) deletions?', last_line)

        if f_match:
            files = int(f_match.group(1))
        if i_match:
            insertions = int(i_match.group(1))
        if d_match:
            deletions = int(d_match.group(1))

        return files, insertions, deletions

    def get_log(self, count: int = 10) -> List[Dict]:
        """최근 커밋 로그 조회"""
        ok, out, _ = self._run_git([
            "log", f"-{count}",
            "--pretty=format:%H|%h|%an|%ae|%ad|%s",
            "--date=iso"
        ])
        if not ok or not out:
            return []

        logs = []
        for line in out.split("\n"):
            parts = line.split("|", 5)
            if len(parts) == 6:
                logs.append({
                    "hash": parts[0],
                    "short_hash": parts[1],
                    "author": parts[2],
                    "email": parts[3],
                    "date": parts[4],
                    "message": parts[5]
                })
        return logs

    def set_user_config(self, name: str, email: str) -> Tuple[bool, str]:
        """로컬 Git 사용자 정보 설정"""
        ok1, _, err1 = self._run_git(["config", "user.name", name])
        ok2, _, err2 = self._run_git(["config", "user.email", email])
        if ok1 and ok2:
            return True, f"Git user set: {name} <{email}>"
        return False, f"Config failed: {err1} {err2}"

    def write_gitignore(self, patterns: List[str]) -> bool:
        """`.gitignore` 파일 생성/업데이트"""
        gitignore_path = os.path.join(self.project_path, ".gitignore")

        # 기존 내용 읽기
        existing = set()
        if os.path.exists(gitignore_path):
            with open(gitignore_path, "r") as f:
                existing = {line.strip() for line in f if line.strip() and not line.startswith("#")}

        # 새 패턴 병합
        all_patterns = existing | set(patterns)

        header = (
            "# ============================================\n"
            "# Auto-generated by GitAutoPush (LLM Analyzed)\n"
            f"# Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            "# ============================================\n\n"
        )

        with open(gitignore_path, "w") as f:
            f.write(header)
            for pattern in sorted(all_patterns):
                if pattern.strip():
                    f.write(pattern.strip() + "\n")

        return True

    def check_credentials(self) -> Tuple[bool, str]:
        """Git 자격 증명 확인"""
        ok, out, _ = self._run_git(["config", "--get", "credential.helper"], cwd="/tmp")
        if ok and out:
            return True, f"Credential helper: {out}"
        return False, "No credential helper configured"
