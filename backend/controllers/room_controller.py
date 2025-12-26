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

    # 获取最近的简历（最多显示2个）
    from backend.services.resume_service import ResumeService
    resumes = ResumeService.get_resumes_by_owner(current_user)
    resumes_dict = [ResumeService.to_dict(resume) for resume in resumes[:2]]

    # 计算用户统计数据
    stats = _calculate_system_stats(rooms)

    return render_template('index.html',
                         rooms=rooms_dict,
                         resumes=resumes_dict,
                         stats=stats,
                         current_user=current_user)


@room_bp.route('/api/rooms/create', methods=['POST'])
@require_auth
def create_room():
    """创建新的面试间 - 需要登录并选择简历"""
    from backend.common.response import ApiResponse
    from backend.services.resume_service import ResumeService

    # 静默ping数字人
    _ping_digital_human()

    # 获取当前用户
    current_user = request.current_user

    # 获取请求参数
    data = request.get_json()
    resume_id = data.get('resume_id') if data else None

    # 验证简历ID（可选，如果不传则创建不关联简历的面试间）
    if resume_id:
        resume = ResumeService.get_resume(resume_id)
        if not resume:
            return ApiResponse.not_found("简历")

        # 验证简历所有权
        if resume.owner_address != current_user:
            return ApiResponse.forbidden()

    # 创建面试间
    room = RoomService.create_room(owner_address=current_user, resume_id=resume_id)

    return ApiResponse.success(
        data={'room_id': room.id},
        message='面试间创建成功'
    )


@room_bp.route('/api/rooms/<room_id>', methods=['PUT'])
@require_auth
@require_resource_owner('room')
def update_room(room_id: str):
    """更新面试间信息 - 需要登录且必须是owner"""
    from backend.common.response import ApiResponse

    # 获取更新数据
    data = request.get_json()
    name = data.get('name')

    # 更新面试间
    success = RoomService.update_room(room_id=room_id, name=name)

    if not success:
        return ApiResponse.internal_error('更新失败')

    # 返回更新后的面试间
    updated_room = RoomService.get_room(room_id)

    return ApiResponse.success(
        data={'room': RoomService.to_dict(updated_room)},
        message='面试间更新成功'
    )


@room_bp.route('/api/rooms/<room_id>/resume', methods=['PUT'])
@require_auth
@require_resource_owner('room')
def update_room_resume(room_id: str):
    """更新面试间的简历 - 需要登录且必须是owner"""
    from backend.common.response import ApiResponse
    from backend.services.resume_service import ResumeService

    # 获取更新数据
    data = request.get_json()
    resume_id = data.get('resume_id')

    if not resume_id:
        return ApiResponse.bad_request('简历ID不能为空')

    # 验证简历是否存在
    resume = ResumeService.get_resume(resume_id)
    if not resume:
        return ApiResponse.not_found("简历")

    # 验证简历所有权
    current_user = request.current_user
    if resume.owner_address != current_user:
        return ApiResponse.forbidden()

    # 更新面试间的简历
    success = RoomService.update_room_resume(room_id=room_id, resume_id=resume_id)

    if not success:
        return ApiResponse.internal_error('更新失败')

    return ApiResponse.success(message='简历更新成功')


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
    """简历列表页面 - 显示用户的所有简历"""
    from backend.services.resume_service import ResumeService

    current_user = request.current_user
    resumes = ResumeService.get_resumes_by_owner(current_user)
    resumes_dict = [ResumeService.to_dict(resume) for resume in resumes]

    # 获取统计信息
    stats = ResumeService.get_resume_stats(current_user)

    return render_template('resumes.html', resumes=resumes_dict, stats=stats)


@room_bp.route('/resumes/<resume_id>')
@validate_uuid_param('resume_id')
@require_auth
def resume_detail(resume_id: str):
    """简历详情页面 - 查看简历内容"""
    from backend.services.resume_service import ResumeService
    from backend.clients.minio_client import download_resume_data

    current_user = request.current_user
    resume = ResumeService.get_resume(resume_id)

    if not resume:
        logger.warning(f"Resume not found: {resume_id}")
        return "简历不存在", 404

    # 检查权限
    if resume.owner_address != current_user:
        logger.warning(f"Unauthorized access attempt to resume {resume_id} by {current_user}")
        return "无权访问此简历", 403

    # 获取简历数据
    resume_data = download_resume_data(resume_id)

    return render_template('resume_detail.html',
                         resume=ResumeService.to_dict(resume),
                         resume_data=resume_data)


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
