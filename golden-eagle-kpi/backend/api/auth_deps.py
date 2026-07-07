"""金鹰工单KPI管理 - 统一认证依赖

提供三个层级的认证依赖：
1. get_current_user      - 基础认证（任何已登录用户）
2. require_super_admin   - 系统管理员（全局配置/定时任务/同步触发）
3. require_project_admin - 项目管理员（本项目数据管理）
"""
from fastapi import Depends, HTTPException, Header, Request
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.services.auth_service import AuthService


def get_current_user(
    authorization: str = Header(None),
    db: Session = Depends(get_db),
) -> dict:
    """基础认证：任何已登录用户
    
    返回: {"employee_id", "account", "role", "project_id"}
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未授权，请登录")
    token = authorization[7:]
    user = AuthService.get_current_user(token, db)
    if not user:
        raise HTTPException(status_code=401, detail="Token无效或已过期")
    return user


def require_super_admin(
    user: dict = Depends(get_current_user),
) -> dict:
    """系统管理员权限：全局配置、定时任务、同步触发、系统管理
    
    允许的角色: 系统管理员
    """
    role = user.get("role", "")
    if role not in ("系统管理员", "super_admin"):
        raise HTTPException(status_code=403, detail="需要系统管理员权限")
    return user


def require_project_admin(
    user: dict = Depends(get_current_user),
) -> dict:
    """项目管理员权限：本项目数据管理、人员管理
    
    允许的角色: 系统管理员、项目负责人
    """
    role = user.get("role", "")
    if role not in ("系统管理员", "super_admin", "项目负责人", "project_admin"):
        raise HTTPException(status_code=403, detail="需要项目管理员权限")
    return user


def require_project_access(
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict:
    """项目数据访问权限：验证请求的项目ID与用户Token中的project_id匹配
    
    系统管理员可访问任意项目，其他用户只能访问自己的项目
    """
    role = user.get("role", "")
    
    # 系统管理员可以访问任意项目
    if role in ("系统管理员", "super_admin"):
        return user
    
    # 其他用户：检查 query 参数中的 projectId 是否匹配
    token_project_id = user.get("project_id")
    
    # 从 query params 获取 projectId
    query_pid = request.query_params.get("projectId")
    if query_pid:
        try:
            query_pid_int = int(query_pid)
            if token_project_id and query_pid_int != token_project_id:
                raise HTTPException(status_code=403, detail="无权限访问其他项目数据")
        except ValueError:
            pass
    
    return user
