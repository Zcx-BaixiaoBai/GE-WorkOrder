"""金鹰工单KPI管理 - API路由：版本更新

更新原理：
- 版本检测：GET https://gitee.com/api/v5/repos/{owner}/{repo}/releases（公开仓库无需认证）
- 代码更新：前端发送 release zip 下载地址 → 后端下载并解压覆盖本地项目目录
- 不依赖 Git CLI，适用于无 Git 环境
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import requests
from pathlib import Path
import zipfile
import io
import shutil
import os

router = APIRouter(prefix="/api/update", tags=["更新"])

GITEE_OWNER = "Zcx-BaixiaoBai"
GITEE_REPO = "g-ai"
CURRENT_VERSION = "v1.0.0"


def _load_token() -> str:
    """从 data/gitee_token.txt 读取 Gitee Token"""
    token_file = Path(__file__).parent.parent.parent / "data" / "gitee_token.txt"
    if token_file.exists():
        return token_file.read_text(encoding="utf-8").strip()
    return os.environ.get("GITEE_TOKEN", "")


GITEE_TOKEN = _load_token()


def get_local_version() -> str:
    """读取本地版本号，优先读 VERSION 文件"""
    import sys
    # 1. 项目根目录的 VERSION 文件
    project_root = Path(__file__).parent.parent.parent
    version_file = project_root / "VERSION"
    if version_file.exists():
        return version_file.read_text(encoding="utf-8").strip()
    # 2. frozen 模式：exe 旁边的 VERSION
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).parent
        frozen_version = exe_dir / "VERSION"
        if frozen_version.exists():
            return frozen_version.read_text(encoding="utf-8").strip()
    return CURRENT_VERSION


def _version_key(tag: str) -> tuple:
    """将 v0.0.10 格式转为可比较的元组 (0, 0, 10)"""
    import re
    m = re.match(r'v?(\d+)\.(\d+)\.(\d+)', tag or '')
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return (0, 0, 0)


def fetch_gitee_releases():
    """获取 Gitee 最新 release 信息"""
    url = f"https://gitee.com/api/v5/repos/{GITEE_OWNER}/{GITEE_REPO}/releases"
    # 公开仓库无需认证；带错误 token 反而 401
    params = {"per_page": 20, "sort": "created", "direction": "desc"}
    # 清除可能干扰的代理环境变量
    proxies = {"http": None, "https": None}
    try:
        resp = requests.get(url, params=params, timeout=30, proxies=proxies)
        if resp.status_code == 200:
            releases = resp.json()
            if releases:
                # 按版本号排序，取最大的
                releases.sort(key=lambda r: _version_key(r.get("tag_name", "")), reverse=True)
            return releases
        else:
            print(f"[update] Gitee API HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[update] Gitee API 请求失败: {e}")
    return []


class CheckUpdateResponse(BaseModel):
    current_version: str
    latest_version: str
    is_latest: bool
    release_notes: str
    download_url: str


class ApplyUpdateRequest(BaseModel):
    download_url: str


@router.get("/check", response_model=CheckUpdateResponse)
def check_update():
    """
    检测更新。
    - GET https://gitee.com/api/v5/repos/{owner}/g-ai/releases 获取最新 release
    - 对比 tag_name 与本地 VERSION 文件
    """
    local_ver = get_local_version()

    releases = fetch_gitee_releases()
    if not releases:
        # 网络不通或未登录 Gitee
        return CheckUpdateResponse(
            current_version=local_ver,
            latest_version=local_ver,
            is_latest=True,
            release_notes="无法连接到 Gitee",
            download_url=""
        )

    latest = releases[0]
    tag = latest.get("tag_name", local_ver)
    notes = (latest.get("body") or "")[:500]
    assets = latest.get("assets", []) or []
    zip_url = ""
    # 优先找发布包 ZIP（文件名含 "KPI"），其次任意 .zip
    for a in assets:
        name = a.get("name", "")
        if "KPI" in name and name.endswith(".zip"):
            zip_url = a.get("browser_download_url", "")
            break
    if not zip_url:
        for a in assets:
            name = a.get("name", "")
            if name.endswith(".zip"):
                zip_url = a.get("browser_download_url", "")
                break

    return CheckUpdateResponse(
        current_version=local_ver,
        latest_version=tag,
        is_latest=(tag == local_ver),
        release_notes=notes,
        download_url=zip_url
    )


@router.post("/apply")
def apply_update(req: ApplyUpdateRequest):
    """
    应用代码更新。
    从 Gitee release 下载 zip 包，解压并覆盖本地项目目录。
    请求体: {"download_url": "https://gitee.com/.../xxx.zip"}
    """
    project_root = Path(__file__).parent.parent.parent
    download_url = req.download_url

    if not download_url:
        raise HTTPException(status_code=400, detail="缺少 download_url")

    try:
        # 下载 zip（禁用代理避免干扰）
        resp = requests.get(download_url, timeout=120, stream=True, proxies={"http": None, "https": None})
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"下载失败，HTTP {resp.status_code}")

        # 解析 zip
        z = zipfile.ZipFile(io.BytesIO(resp.content))
        members = z.namelist()
        if not members:
            raise HTTPException(status_code=400, detail="空的 zip 包")

        # Gitee release zip 通常包含一级根目录，如 "g-ai-v0.0.9/"
        top_dir = members[0].split("/")[0] + "/" if members[0].find("/") >= 0 else ""

        extracted = 0
        skipped = 0
        for member in members:
            if member.endswith("/"):
                continue
            # 去掉一级根目录
            rel_path = member[len(top_dir):] if top_dir and member.startswith(top_dir) else member
            if not rel_path:
                continue
            target = project_root / rel_path
            # 安全检查：只允许写入项目目录内
            try:
                target.resolve().relative_to(project_root.resolve())
            except ValueError:
                skipped += 1
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            extracted += 1

        return {
            "success": True,
            "extracted": extracted,
            "skipped": skipped,
            "message": f"更新完成，共覆盖 {extracted} 个文件"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")
