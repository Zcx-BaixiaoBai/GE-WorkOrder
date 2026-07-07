"""金鹰工单KPI管理 - API路由：认证"""
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["认证"])


class LoginRequest(BaseModel):
    account: str
    password: str
    employeeId: str
    projectId: str | None = None


@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    """登录"""
    result = AuthService.login(
        account=req.account,
        password=req.password,
        employee_id=req.employeeId,
        project_id=req.projectId,
        db=db,
    )
    if not result.get("success"):
        code = result.get("code", 401)
        raise HTTPException(status_code=code, detail=result.get("error"))
    return result


@router.post("/logout")
def logout(authorization: str = Header(None), db: Session = Depends(get_db)):
    """登出（从Header获取token）"""
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    AuthService.logout(token, db)
    return {"success": True}


@router.get("/me")
def get_current_user(authorization: str = Header(None), db: Session = Depends(get_db)):
    """获取当前用户信息（从Header获取token）"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未授权")
    token = authorization[7:]
    user = AuthService.get_current_user(token, db)
    if not user:
        raise HTTPException(status_code=401, detail="未登录或Token已过期")
    return user
