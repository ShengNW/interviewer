"""
面试间Controller
负责面试间相关的路由处理
"""

import threading
from flask import Blueprint, render_template, redirect, url_for, Response, request
from typing import Union
from backend.services.interview_service import RoomService, SessionService, RoundService
from backend.clients.digitalhub_client import ping_dh
from backend.common.validators import validate_uuid_param
from backend.common.middleware import require_auth, require_resource_owner, get_current_user_optional
from backend.common.logger import get_logger

logger = get_logger(__name__)

# 创建蓝图
room_bp = Blueprint('room', __name__)


@room_bp.route('/')
def index():
    """智能首页 - 根据登录状态显示不同内容"""
    current_user = get_current_user_optional()

    if not current_user:
        # 未登录 - 显示营销页
        return render_template('landing.html')

    # 已登录 - 显示个人工作台（只查询该用户的面试间）
    rooms = RoomService.get_rooms_by_owner(current_user)
    rooms_dict = [RoomService.to_dict(room) for room in rooms]

    # 计算用户统计数据
    stats = _calculate_system_stats(rooms)

    return render_template('index.html',
                         rooms=rooms_dict,
                         stats=stats,
                         current_user=current_user)


@room_bp.route('/create_room')
@require_auth
def create_room():
    """创建新的面试间 - 需要登录"""
    # 静默ping数字人
    _ping_digital_human()

    # 获取当前用户并记录为owner
    current_user = request.current_user
    room = RoomService.create_room(owner_address=current_user)
    return redirect(url_for('room.room_detail', room_id=room.id))


@room_bp.route('/rooms')
@require_auth
def rooms_list():
    """我的面试间列表页面 - 显示所有面试间"""
    current_user = request.current_user
    rooms = RoomService.get_rooms_by_owner(current_user)
    rooms_dict = [RoomService.to_dict(room) for room in rooms]

    return render_template('rooms.html', rooms=rooms_dict)


@room_bp.route('/resumes')
@require_auth
def resumes_list():
    """我的简历列表页面"""
    # TODO: 后续实现简历管理功能
    return render_template('resumes.html')


@room_bp.route('/mistakes')
@require_auth
def mistakes_list():
    """我的错题集页面"""
    # TODO: 后续实现错题集功能
    return render_template('mistakes.html')


@room_bp.route('/room/<room_id>')
@validate_uuid_param('room_id')
@require_auth
@require_resource_owner('room')
def room_detail(room_id: str) -> Union[str, tuple[str, int]]:
    """面试间详情页面 - 需要登录且必须是owner"""
    # 异步ping数字人（不阻塞页面加载）
    _ping_digital_human_async()

    room = RoomService.get_room(room_id)
    if not room:
        logger.warning(f"Room not found: {room_id}")
        return "面试间不存在", 404

    sessions = SessionService.get_sessions_by_room(room_id)
    sessions_dict = [SessionService.to_dict(session) for session in sessions]

    return render_template('room.html',
                         room=RoomService.to_dict(room),
                         sessions=sessions_dict)


# ==================== 私有辅助函数 ====================

def _calculate_system_stats(rooms) -> dict:
    """计算系统统计数据"""
    total_sessions = 0
    total_rounds = 0
    total_questions = 0

    for room in rooms:
        sessions = SessionService.get_sessions_by_room(room.id)
        total_sessions += len(sessions)

        for session in sessions:
            rounds = RoundService.get_rounds_by_session(session.id)
            total_rounds += len(rounds)

            for round_obj in rounds:
                total_questions += round_obj.questions_count

    return {
        'total_rooms': len(rooms),
        'total_sessions': total_sessions,
        'total_rounds': total_rounds,
        'total_questions': total_questions
    }


def _ping_digital_human() -> None:
    """静默ping数字人服务（同步版本）"""
    try:
        ping_dh()
    except Exception as e:
        logger.warning(f"Failed to ping digital human: {e}")


def _ping_digital_human_async() -> None:
    """异步ping数字人服务（不阻塞主线程）"""
    def _async_ping():
        try:
            ping_dh()
            logger.info("Digital human ping successful (async)")
        except Exception as e:
            logger.warning(f"Failed to ping digital human (async): {e}")

    # 使用守护线程，不阻塞主线程
    thread = threading.Thread(target=_async_ping, daemon=True)
    thread.start()
    logger.debug("Digital human ping started in background")


@room_bp.route('/pricing')
def pricing():
    """价格页面"""
    return render_template('pricing.html')


@room_bp.route('/docs')
def docs():
    """文档页面"""
    return render_template('docs.html')


@room_bp.route('/about')
def about():
    """关于我们页面"""
    return render_template('about.html')
