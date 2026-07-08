"""金鹰工单KPI管理 - API路由：AI配置管理

仅系统管理员可访问，读取/修改 .env 文件中的AI相关配置
"""
import os
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from backend.api.auth_deps import require_super_admin
from backend.config import _load_dotenv, AppConfig

_load_dotenv()

router = APIRouter(prefix="/api/config/ai", tags=["AI配置"])


@router.get("")
def get_ai_config(user: dict = Depends(require_super_admin)):
    """获取当前AI配置"""
    return {
        "model": os.environ.get("AI_MODEL", "qwen/qwen3.5-122b-a10b"),
        "apiKey": os.environ.get("AI_API_KEY", ""),
        "invokeUrl": os.environ.get("AI_INVOKE_URL", "https://integrate.api.nvidia.com/v1/chat/completions"),
        "maxTokens": int(os.environ.get("AI_MAX_TOKENS", "16384")),
        "temperature": float(os.environ.get("AI_TEMPERATURE", "0.60")),
    }


class AIConfigUpdate(BaseModel):
    model: str | None = None
    apiKey: str | None = None
    invokeUrl: str | None = None
    maxTokens: int | None = None
    temperature: float | None = None


@router.put("")
def update_ai_config(req: AIConfigUpdate, user: dict = Depends(require_super_admin)):
    """更新AI配置（写入.env文件 + 更新环境变量 + 热重载ai_chat配置）"""
    # 读取当前.env
    from pathlib import Path
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if not env_path.exists():
        # frozen模式
        if getattr(__import__('sys'), 'frozen', False):
            env_path = Path(__import__('sys').executable).parent / ".env"
    
    lines = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
    
    # 更新对应的行
    updates = {
        "AI_MODEL": req.model,
        "AI_API_KEY": req.apiKey,
        "AI_INVOKE_URL": req.invokeUrl,
        "AI_MAX_TOKENS": str(req.maxTokens) if req.maxTokens else None,
        "AI_TEMPERATURE": str(req.temperature) if req.temperature else None,
    }
    
    updated_keys = set()
    new_lines = []
    for line in lines:
        if "=" in line and not line.strip().startswith("#"):
            key = line.split("=")[0].strip()
            if key in updates and updates[key] is not None:
                new_lines.append(f"{key}={updates[key]}")
                os.environ[key] = updates[key]
                updated_keys.add(key)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)
    
    # 添加不存在的key
    for key, val in updates.items():
        if val is not None and key not in updated_keys:
            new_lines.append(f"{key}={val}")
            os.environ[key] = val
    
    env_path.write_text("\n".join(new_lines), encoding="utf-8")
    
    # 热重载ai_chat配置
    try:
        from backend.api.ai_chat import _load_ai_config, AI_CONFIG
        import backend.api.ai_chat as ai_module
        ai_module.AI_CONFIG = _load_ai_config()
    except Exception as e:
        print(f"[AI配置] 热重载失败: {e}")
    
    return {"success": True, "message": "AI配置已更新并生效"}
