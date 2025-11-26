"""
中间件模块
提供统一的异常处理、日志记录、请求验证、JWT鉴权等中间件
"""

import os
from functools import wraps
from typing import Callable, Any, Tuple, Optional
from flask import request, Flask, Response, redirect, url_for, flash
from jose import jwt, JWTError
from backend.common.response import ApiResponse
from backend.common.exceptions import BusinessBaseException
from backend.common.logger import get_logger

logger = get_logger(__name__)

# JWT 配置 (与 auth_controller 保持一致)
JWT_SECRET = os.getenv("JWT_SECRET", "e802e988a02546cc47415e4bc76346aae7ceece97a0f950319c861a5de38b20d")
JWT_ALGORITHM = "HS256"


def error_handler(app: Flask) -> None:
    """
    全局异常处理器

    Args:
        app: Flask应用实例
    """

    @app.errorhandler(BusinessBaseException)
    def handle_custom_exception(error):
        """处理自定义异常"""
        logger.warning(f"Business exception: {error.message}", exc_info=True)
        return ApiResponse.error(
            message=error.message,
            code=error.code
        )

    @app.errorhandler(ValueError)
    def handle_value_error(error):
        """处理值错误"""
        logger.warning(f"ValueError: {str(error)}", exc_info=True)
        return ApiResponse.bad_request(str(error))

    @app.errorhandler(404)
    def handle_not_found(error):
        """处理404错误"""
        logger.warning(f"404 Not Found: {request.url}")
        return ApiResponse.not_found("页面或资源")

    @app.errorhandler(500)
    def handle_internal_error(error):
        """处理500错误"""
        logger.error(f"Internal Server Error: {str(error)}", exc_info=True)
        return ApiResponse.internal_error()

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        """处理未预期的异常"""
        logger.error(f"Unexpected error: {str(error)}", exc_info=True)
        return ApiResponse.internal_error("服务器发生未知错误")


def request_logger(app: Flask) -> None:
    """
    请求日志中间件

    Args:
        app: Flask应用实例
    """

    @app.before_request
    def log_request():
        """记录请求信息"""
        logger.info(
            f"Request: {request.method} {request.path} "
            f"from {request.remote_addr} "
            f"User-Agent: {request.user_agent}"
        )

    @app.after_request
    def log_response(response: Response) -> Response:
        """记录响应信息"""
        logger.info(
            f"Response: {request.method} {request.path} "
            f"Status: {response.status_code}"
        )
        return response


def validate_request(*required_fields: str) -> Callable:
    """
    请求参数验证装饰器

    Args:
        *required_fields: 必需的字段列表

    Usage:
        @validate_request('name', 'email')
        def create_user():
            data = request.get_json()
            ...
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated_function(*args: Any, **kwargs: Any) -> Any:
            # 获取请求数据
            if request.is_json:
                data = request.get_json() or {}
            else:
                data = request.form.to_dict()

            # 检查必需字段
            missing_fields = []
            for field in required_fields:
                if field not in data or not data[field]:
                    missing_fields.append(field)

            if missing_fields:
                logger.warning(f"Missing required fields: {missing_fields}")
                return ApiResponse.bad_request(
                    f"缺少必需参数: {', '.join(missing_fields)}"
                )

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def handle_exceptions(f: Callable) -> Callable:
    """
    异常处理装饰器 - 用于路由函数

    Usage:
        @app.route('/api/users')
        @handle_exceptions
        def get_users():
            ...
    """
    @wraps(f)
    def decorated_function(*args: Any, **kwargs: Any) -> Any:
        try:
            return f(*args, **kwargs)
        except BusinessBaseException as e:
            logger.warning(f"Business exception in {f.__name__}: {e.message}")
            return ApiResponse.error(message=e.message, code=e.code)
        except Exception as e:
            logger.error(f"Unexpected error in {f.__name__}: {str(e)}", exc_info=True)
            return ApiResponse.internal_error(f"操作失败: {str(e)}")
    return decorated_function


# ==================== JWT 鉴权中间件 ====================

def get_current_user() -> Optional[str]:
    """
    获取当前登录用户的钱包地址

    支持两种Token传递方式:
    1. Authorization Header (API请求): Bearer <token>
    2. Cookie (页面请求): auth_token=<token>

    Returns:
        钱包地址 (如: 0x1234...) 或 None
    """
    token = None

    # 方式1: 从 Authorization Header 获取 (优先级高)
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]

    # 方式2: 从 Cookie 获取
    if not token:
        token = request.cookies.get('auth_token')

    if not token:
        return None

    try:
        # 验证并解析JWT
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        wallet_address = payload.get('sub')
        return wallet_address
    except JWTError as e:
        logger.warning(f"JWT验证失败: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Token解析异常: {str(e)}", exc_info=True)
        return None


def get_current_user_optional() -> Optional[str]:
    """
    可选登录模式 - 用于首页等需要区分登录状态但不强制登录的页面

    Returns:
        钱包地址或None (不会抛出异常)
    """
    return get_current_user()


def require_auth(f: Callable) -> Callable:
    """
    垂直鉴权装饰器 - 确保用户已登录

    Usage:
        @app.route('/create_room')
        @require_auth
        def create_room():
            user = request.current_user  # 可以获取当前用户钱包地址
            ...
    """
    @wraps(f)
    def decorated_function(*args: Any, **kwargs: Any) -> Any:
        current_user = get_current_user()

        if not current_user:
            # 判断是API请求还是页面请求
            if request.path.startswith('/api/'):
                # API请求返回JSON错误
                return ApiResponse.error('未授权，请先登录', code=401)
            else:
                # 页面请求重定向到首页
                flash('请先连接钱包登录', 'warning')
                return redirect(url_for('room.index'))

        # 将当前用户钱包地址注入到request上下文
        request.current_user = current_user
        return f(*args, **kwargs)

    return decorated_function


def require_resource_owner(resource_type: str = 'room'):
    """
    水平鉴权装饰器工厂 - 确保用户是资源的所有者

    Args:
        resource_type: 资源类型 'room' 或 'session'

    Usage:
        @app.route('/room/<room_id>')
        @require_auth
        @require_resource_owner('room')
        def room_detail(room_id):
            # 此时确保用户是该room的owner
            ...
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated_function(*args: Any, **kwargs: Any) -> Any:
            # 确保 @require_auth 已经执行
            current_user = getattr(request, 'current_user', None)
            if not current_user:
                logger.error("require_resource_owner 必须在 @require_auth 之后使用")
                return ApiResponse.internal_error("服务器配置错误")

            # 获取资源ID
            resource_id = kwargs.get('room_id') or kwargs.get('session_id')
            if not resource_id:
                logger.error(f"无法获取资源ID: kwargs={kwargs}")
                return ApiResponse.bad_request("无效的资源ID")

            # 检查资源所有权
            try:
                if resource_type == 'room':
                    from backend.services.interview_service import RoomService
                    room = RoomService.get_room(resource_id)
                    if not room:
                        if request.path.startswith('/api/'):
                            return ApiResponse.not_found("面试间")
                        else:
                            flash('面试间不存在', 'danger')
                            return redirect(url_for('room.index'))

                    owner_address = room.owner_address

                elif resource_type == 'session':
                    from backend.services.interview_service import SessionService
                    session = SessionService.get_session(resource_id)
                    if not session:
                        if request.path.startswith('/api/'):
                            return ApiResponse.not_found("面试会话")
                        else:
                            flash('面试会话不存在', 'danger')
                            return redirect(url_for('room.index'))

                    owner_address = session.room.owner_address

                else:
                    logger.error(f"不支持的资源类型: {resource_type}")
                    return ApiResponse.internal_error("服务器配置错误")

                # 水平鉴权：检查所有权
                if owner_address != current_user:
                    logger.warning(
                        f"水平越权尝试: user={current_user}, resource={resource_type}:{resource_id}, owner={owner_address}"
                    )
                    if request.path.startswith('/api/'):
                        return ApiResponse.error('无权访问此资源', code=403)
                    else:
                        flash('您无权访问此资源', 'danger')
                        return redirect(url_for('room.index'))

                # 验证通过
                return f(*args, **kwargs)

            except Exception as e:
                logger.error(f"资源所有权检查失败: {str(e)}", exc_info=True)
                return ApiResponse.internal_error("权限检查失败")

        return decorated_function
    return decorator

