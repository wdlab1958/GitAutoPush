"""AutoGit FastAPI Server - REST API wrapper for git automation with LLM"""
import os
import sys
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List

sys.path.insert(0, os.path.dirname(__file__))
from core.git_manager import GitManager
from core.ollama_client import OllamaClient, OllamaConfig

app = FastAPI(title="AutoGit API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

ollama = OllamaClient()


class RepoRequest(BaseModel):
    project_path: str
    remote_url: Optional[str] = None


class CommitRequest(BaseModel):
    project_path: str
    message: Optional[str] = None


class AnalyzeRequest(BaseModel):
    project_path: str
    project_type_hint: Optional[str] = None


@app.get("/health")
async def health():
    available, detail = ollama.is_available()
    return {
        "status": "healthy",
        "service": "AutoGit",
        "ollama_available": available,
        "ollama_detail": detail,
        "timestamp": datetime.now().isoformat()
    }


@app.get("/")
async def root():
    return {
        "service": "AutoGit - AI-powered Git Automation API",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "git_status": "POST /git/status",
            "git_log": "POST /git/log",
            "git_commit": "POST /git/commit",
            "analyze_gitignore": "POST /analyze/gitignore",
            "generate_commit_msg": "POST /analyze/commit-message",
            "detect_sensitive": "POST /analyze/sensitive-files",
            "ollama_status": "/ollama/status"
        }
    }


@app.get("/ollama/status")
async def ollama_status():
    available, detail = ollama.is_available()
    models = ollama.get_available_models() if available else []
    return {"available": available, "detail": detail, "models": models, "config": {"model": ollama.config.model, "base_url": ollama.config.base_url}}


@app.post("/git/status")
async def git_status(req: RepoRequest):
    try:
        gm = GitManager(req.project_path, req.remote_url)
        if not gm.is_repo():
            raise HTTPException(400, "Not a git repository")
        status = gm.get_status()
        branch = gm.get_current_branch()
        return {"branch": branch, **status}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/git/log")
async def git_log(req: RepoRequest):
    try:
        gm = GitManager(req.project_path, req.remote_url)
        if not gm.is_repo():
            raise HTTPException(400, "Not a git repository")
        return {"commits": gm.get_log(10)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/git/commit")
async def git_commit(req: CommitRequest):
    try:
        gm = GitManager(req.project_path)
        if not gm.is_repo():
            raise HTTPException(400, "Not a git repository")
        gm.stage_all()
        files, insertions, deletions = gm.get_diff_stats()
        diff_summary = f"{files} files changed, {insertions} insertions(+), {deletions} deletions(-)"
        message = req.message
        if not message:
            status = gm.get_status()
            file_list = "\n".join(status.get("staged", []) + status.get("modified", []))
            ok, message = ollama.generate_commit_message(diff_summary, file_list, os.path.basename(req.project_path))
            if not ok:
                raise HTTPException(502, f"Commit message generation failed: {message}")
        ok, out, commit_hash = gm.commit(message)
        if not ok:
            raise HTTPException(400, out)
        return {"hash": commit_hash, "message": message}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/analyze/gitignore")
async def analyze_gitignore(req: AnalyzeRequest):
    try:
        tree = ollama.scan_project_tree(req.project_path)
        ok, patterns, explanation = ollama.analyze_gitignore(tree, req.project_type_hint or "")
        return {"success": ok, "patterns": patterns, "explanation": explanation}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/analyze/commit-message")
async def analyze_commit_message(req: RepoRequest):
    try:
        gm = GitManager(req.project_path)
        files, insertions, deletions = gm.get_diff_stats()
        diff_summary = f"{files} files changed, {insertions} insertions(+), {deletions} deletions(-)"
        status = gm.get_status()
        file_list = "\n".join(status.get("staged", []) + status.get("modified", []))
        ok, message = ollama.generate_commit_message(diff_summary, file_list, os.path.basename(req.project_path))
        return {"success": ok, "message": message, "diff_stats": {"files": files, "insertions": insertions, "deletions": deletions}}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/analyze/sensitive-files")
async def detect_sensitive(req: RepoRequest):
    try:
        gm = GitManager(req.project_path)
        status = gm.get_status()
        all_files = "\n".join(status.get("staged", []) + status.get("modified", []) + status.get("untracked", []))
        ok, sensitive, reason = ollama.detect_sensitive_files(all_files)
        return {"success": ok, "sensitive": sensitive, "reason": reason}
    except Exception as e:
        raise HTTPException(500, str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=4018)
