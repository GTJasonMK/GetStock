# Common Schemas
"""
通用响应模型
"""

from typing import TypeVar, Generic, Optional, Any

from pydantic import BaseModel

T = TypeVar("T")


class Response(BaseModel, Generic[T]):
    """统一API响应结构"""
    code: int = 0
    message: str = "success"
    data: Optional[T] = None


class ErrorResponse(BaseModel):
    """错误响应"""
    code: int
    message: str
    detail: Optional[str] = None


class PaginatedResponse(BaseModel, Generic[T]):
    """分页响应"""
    code: int = 0
    message: str = "success"
    data: Optional[T] = None
    total: int = 0
    page: int = 1
    page_size: int = 20
    has_more: bool = False


# 响应码常量
class ResponseCode:
    SUCCESS = 0
    INVALID_PARAM = 400
    NOT_FOUND = 404
    INTERNAL_ERROR = 500
