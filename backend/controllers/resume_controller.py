"""
简历Controller
负责简历上传、解析、管理相关的路由处理 - 支持树状版本管理
"""

import tempfile
import os
import json
from flask import Blueprint, request
from werkzeug.utils import secure_filename
from backend.common.response import ApiResponse
from backend.common.middleware import require_auth
from backend.clients.minio_client import (
    download_resume_data, upload_resume_data, delete_resume_data,
    minio_client
)
from backend.services.resume_service import ResumeService
from backend.models.models import ResumeContent
from backend.common.logger import get_logger

logger = get_logger(__name__)

# 创建蓝图
resume_bp = Blueprint('resume', __name__)


# ==================== 树状管理新接口 ====================

@resume_bp.route('/api/resumes', methods=['POST'])
@require_auth
def create_resume():
    """创建根简历"""
    logger.debug("Creating root resume")

    try:
        current_user = request.current_user
        data = request.get_json() or {}

        name = data.get('name', '').strip()
        if not name:
            return ApiResponse.bad_request('简历名称不能为空')

        target_company = data.get('target_company', '').strip() or None
        target_position = data.get('target_position', '').strip() or None

        resume = ResumeService.create_root_resume(
            owner_address=current_user,
            name=name,
            target_company=target_company,
            target_position=target_position
        )

        return ApiResponse.success(
            data={'resume': ResumeService.to_dict(resume)},
            message='简历创建成功'
        )

    except Exception as e:
        logger.error(f"Failed to create resume: {e}", exc_info=True)
        return ApiResponse.internal_error(f'创建失败: {str(e)}')


@resume_bp.route('/api/resumes/<resume_id>/fork', methods=['POST'])
@require_auth
def fork_resume(resume_id: str):
    """基于某版本创建子版本"""
    logger.debug(f"Forking resume: {resume_id}")

    try:
        current_user = request.current_user

        child = ResumeService.fork_resume(resume_id, current_user)

        return ApiResponse.success(
            data={'resume': ResumeService.to_dict(child)},
            message='子版本创建成功'
        )

    except PermissionError as e:
        return ApiResponse.forbidden(str(e))
    except ValueError as e:
        return ApiResponse.bad_request(str(e))
    except Exception as e:
        logger.error(f"Failed to fork resume: {e}", exc_info=True)
        return ApiResponse.internal_error(f'创建子版本失败: {str(e)}')


@resume_bp.route('/api/resumes/trees', methods=['GET'])
@require_auth
def get_resume_trees():
    """获取用户简历树列表"""
    logger.debug("Getting resume trees")

    try:
        current_user = request.current_user
        trees = ResumeService.get_resume_trees(current_user)
        stats = ResumeService.get_resume_stats(current_user)

        return ApiResponse.success(
            data={
                'trees': trees,
                'stats': stats
            }
        )

    except Exception as e:
        logger.error(f"Failed to get resume trees: {e}", exc_info=True)
        return ApiResponse.internal_error(f'获取简历树失败: {str(e)}')


@resume_bp.route('/api/resumes/available', methods=['GET'])
@require_auth
def get_available_resumes():
    """获取可用于面试的简历（仅已发布）"""
    logger.debug("Getting available resumes")

    try:
        current_user = request.current_user
        resumes = ResumeService.get_available_resumes(current_user)
        resumes_dict = [ResumeService.to_dict(r) for r in resumes]

        return ApiResponse.success(
            data={'resumes': resumes_dict}
        )

    except Exception as e:
        logger.error(f"Failed to get available resumes: {e}", exc_info=True)
        return ApiResponse.internal_error(f'获取可用简历失败: {str(e)}')


@resume_bp.route('/api/resumes/<resume_id>/content', methods=['GET'])
@require_auth
def get_resume_content(resume_id: str):
    """获取简历表单内容"""
    logger.debug(f"Getting resume content: {resume_id}")

    try:
        current_user = request.current_user
        resume = ResumeService.get_resume(resume_id)

        if not resume:
            return ApiResponse.not_found("简历")

        if resume.owner_address != current_user:
            return ApiResponse.forbidden()

        content = ResumeContent.get_or_none(ResumeContent.resume_id == resume_id)

        if not content:
            return ApiResponse.success(data={'content': None})

        content_dict = {
            'full_name': content.full_name,
            'email': content.email,
            'phone': content.phone,
            'location': content.location,
            'website': content.website,
            'summary': content.summary,
            'education': json.loads(content.education) if content.education else [],
            'experience': json.loads(content.experience) if content.experience else [],
            'projects': json.loads(content.projects) if content.projects else [],
            'skills': json.loads(content.skills) if content.skills else [],
            'certifications': json.loads(content.certifications) if content.certifications else []
        }

        return ApiResponse.success(data={'content': content_dict})

    except Exception as e:
        logger.error(f"Failed to get resume content: {e}", exc_info=True)
        return ApiResponse.internal_error(f'获取简历内容失败: {str(e)}')


@resume_bp.route('/api/resumes/<resume_id>/content', methods=['PUT'])
@require_auth
def update_resume_content(resume_id: str):
    """保存简历表单内容（已发布会自动变回编辑中）"""
    logger.debug(f"Updating resume content: {resume_id}")

    try:
        current_user = request.current_user
        data = request.get_json() or {}

        # 处理 JSON 字段
        content_fields = {}
        simple_fields = ['full_name', 'email', 'phone', 'location', 'website', 'summary']
        json_fields = ['education', 'experience', 'projects', 'skills', 'certifications']

        for field in simple_fields:
            if field in data:
                content_fields[field] = data[field]

        for field in json_fields:
            if field in data:
                content_fields[field] = json.dumps(data[field], ensure_ascii=False)

        ResumeService.update_content(resume_id, current_user, **content_fields)

        return ApiResponse.success(message='简历内容已保存')

    except PermissionError as e:
        return ApiResponse.forbidden(str(e))
    except Exception as e:
        logger.error(f"Failed to update resume content: {e}", exc_info=True)
        return ApiResponse.internal_error(f'保存失败: {str(e)}')


@resume_bp.route('/api/resumes/<resume_id>/publish', methods=['POST'])
@require_auth
def publish_resume(resume_id: str):
    """发布简历"""
    logger.debug(f"Publishing resume: {resume_id}")

    try:
        current_user = request.current_user

        ResumeService.publish_resume(resume_id, current_user)

        resume = ResumeService.get_resume(resume_id)

        return ApiResponse.success(
            data={'resume': ResumeService.to_dict(resume)},
            message='简历已发布'
        )

    except PermissionError as e:
        return ApiResponse.forbidden(str(e))
    except Exception as e:
        logger.error(f"Failed to publish resume: {e}", exc_info=True)
        return ApiResponse.internal_error(f'发布失败: {str(e)}')


@resume_bp.route('/api/resumes/<resume_id>/unpublish', methods=['POST'])
@require_auth
def unpublish_resume(resume_id: str):
    """取消发布简历"""
    logger.debug(f"Unpublishing resume: {resume_id}")

    try:
        current_user = request.current_user

        ResumeService.unpublish_resume(resume_id, current_user)

        resume = ResumeService.get_resume(resume_id)

        return ApiResponse.success(
            data={'resume': ResumeService.to_dict(resume)},
            message='已取消发布'
        )

    except PermissionError as e:
        return ApiResponse.forbidden(str(e))
    except Exception as e:
        logger.error(f"Failed to unpublish resume: {e}", exc_info=True)
        return ApiResponse.internal_error(f'取消发布失败: {str(e)}')


@resume_bp.route('/api/resumes/<resume_id>/link/<room_id>', methods=['POST'])
@require_auth
def link_resume_to_room(resume_id: str, room_id: str):
    """将简历关联到面试间"""
    logger.debug(f"Linking resume {resume_id} to room {room_id}")

    try:
        current_user = request.current_user

        ResumeService.link_to_room(resume_id, room_id, current_user)

        return ApiResponse.success(message='简历已关联到面试间')

    except PermissionError as e:
        return ApiResponse.forbidden(str(e))
    except ValueError as e:
        return ApiResponse.bad_request(str(e))
    except Exception as e:
        logger.error(f"Failed to link resume to room: {e}", exc_info=True)
        return ApiResponse.internal_error(f'关联失败: {str(e)}')


@resume_bp.route('/api/resumes/<resume_id>/preview', methods=['POST'])
@require_auth
def preview_resume_pdf(resume_id: str):
    """生成预览 PDF，返回临时 URL"""
    logger.debug(f"Previewing resume PDF: {resume_id}")

    try:
        current_user = request.current_user
        resume = ResumeService.get_resume(resume_id)

        if not resume:
            return ApiResponse.not_found("简历")

        if resume.owner_address != current_user:
            return ApiResponse.forbidden()

        from backend.services.rendercv_service import get_rendercv_service
        rendercv = get_rendercv_service()

        url = rendercv.get_preview_url(resume_id)

        return ApiResponse.success(
            data={'preview_url': url},
            message='预览 PDF 生成成功'
        )

    except ValueError as e:
        return ApiResponse.bad_request(str(e))
    except Exception as e:
        logger.error(f"Failed to preview resume: {e}", exc_info=True)
        return ApiResponse.internal_error(f'预览失败: {str(e)}')


@resume_bp.route('/api/resumes/<resume_id>/pdf', methods=['GET'])
@require_auth
def get_resume_pdf(resume_id: str):
    """获取已发布 PDF 下载链接"""
    logger.debug(f"Getting resume PDF: {resume_id}")

    try:
        current_user = request.current_user
        resume = ResumeService.get_resume(resume_id)

        if not resume:
            return ApiResponse.not_found("简历")

        if resume.owner_address != current_user:
            return ApiResponse.forbidden()

        if resume.status != 'published':
            return ApiResponse.bad_request('简历尚未发布')

        from backend.services.rendercv_service import get_rendercv_service
        rendercv = get_rendercv_service()

        url = rendercv.get_published_url(resume_id)

        if not url:
            return ApiResponse.not_found("PDF 文件")

        return ApiResponse.success(
            data={'pdf_url': url}
        )

    except Exception as e:
        logger.error(f"Failed to get resume PDF: {e}", exc_info=True)
        return ApiResponse.internal_error(f'获取 PDF 失败: {str(e)}')


# ==================== 兼容旧接口 ====================

@resume_bp.route('/api/resumes/upload', methods=['POST'])
@require_auth
def upload_resume():
    """上传简历PDF并解析为结构化数据 - 需要登录"""
    logger.debug("Uploading resume")

    try:
        current_user = request.current_user

        # 验证文件上传
        if 'resume' not in request.files:
            return ApiResponse.bad_request('没有上传文件')

        file = request.files['resume']

        if file.filename == '':
            return ApiResponse.bad_request('没有选择文件')

        if not file.filename.lower().endswith('.pdf'):
            return ApiResponse.bad_request('只支持PDF格式')

        # 获取元数据
        name = request.form.get('name', '').strip() or file.filename
        company = request.form.get('company', '').strip() or None
        position = request.form.get('position', '').strip() or None

        # 保存临时文件
        temp_path = _save_temp_file(file)

        try:
            # 解析PDF
            markdown_content = _parse_pdf(temp_path)

            if not markdown_content:
                return ApiResponse.internal_error('PDF解析失败，请稍后重试')

            # 提取结构化数据
            resume_data = _extract_resume_data(markdown_content)

            if not resume_data:
                return ApiResponse.internal_error('简历数据提取失败')

            # 添加元数据
            if company:
                resume_data['company'] = company
            if position:
                resume_data['position'] = position

            # 创建简历记录
            try:
                resume = ResumeService.create_resume(
                    owner_address=current_user,
                    name=name,
                    file_name=secure_filename(file.filename),
                    file_size=os.path.getsize(temp_path),
                    company=company,
                    position=position
                )
            except ValueError as e:
                # 简历名称重复
                return ApiResponse.bad_request(str(e))

            # 保存到MinIO
            success = upload_resume_data(resume_data, resume.id)

            if not success:
                # 如果MinIO保存失败，删除数据库记录
                ResumeService.delete_resume(resume.id)
                return ApiResponse.internal_error('简历保存失败')

            return ApiResponse.success(
                data={
                    'resume': ResumeService.to_dict(resume),
                    'resume_data': resume_data
                },
                message='简历上传成功'
            )

        finally:
            # 删除临时文件
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    except Exception as e:
        logger.error(f"Failed to upload resume: {e}", exc_info=True)
        return ApiResponse.internal_error(f'上传失败: {str(e)}')


@resume_bp.route('/api/resumes', methods=['GET'])
@require_auth
def list_resumes():
    """获取当前用户的所有简历 - 需要登录"""
    logger.debug("Listing resumes")

    try:
        current_user = request.current_user
        resumes = ResumeService.get_resumes_by_owner(current_user)
        resumes_dict = [ResumeService.to_dict(resume) for resume in resumes]

        # 获取统计信息
        stats = ResumeService.get_resume_stats(current_user)

        return ApiResponse.success(
            data={
                'resumes': resumes_dict,
                'stats': stats
            }
        )

    except Exception as e:
        logger.error(f"Failed to list resumes: {e}", exc_info=True)
        return ApiResponse.internal_error(f'获取简历列表失败: {str(e)}')


@resume_bp.route('/api/resumes/<resume_id>', methods=['GET'])
@require_auth
def get_resume(resume_id: str):
    """获取指定简历的详细信息 - 需要登录"""
    logger.debug(f"Getting resume: {resume_id}")

    try:
        current_user = request.current_user
        resume = ResumeService.get_resume(resume_id)

        if not resume:
            return ApiResponse.not_found("简历")

        # 验证权限
        if resume.owner_address != current_user:
            return ApiResponse.forbidden()

        # 获取MinIO中的简历数据
        resume_data = download_resume_data(resume_id)

        # 获取表单内容
        content = ResumeContent.get_or_none(ResumeContent.resume_id == resume_id)
        content_dict = None
        if content:
            content_dict = {
                'full_name': content.full_name,
                'email': content.email,
                'phone': content.phone,
                'location': content.location,
                'website': content.website,
                'summary': content.summary,
                'education': json.loads(content.education) if content.education else [],
                'experience': json.loads(content.experience) if content.experience else [],
                'projects': json.loads(content.projects) if content.projects else [],
                'skills': json.loads(content.skills) if content.skills else [],
                'certifications': json.loads(content.certifications) if content.certifications else []
            }

        return ApiResponse.success(
            data={
                'resume': ResumeService.to_dict(resume),
                'resume_data': resume_data,
                'content': content_dict
            }
        )

    except Exception as e:
        logger.error(f"Failed to get resume: {e}", exc_info=True)
        return ApiResponse.internal_error(f'获取简历失败: {str(e)}')


@resume_bp.route('/api/resumes/<resume_id>', methods=['PUT'])
@require_auth
def update_resume(resume_id: str):
    """更新简历元信息 - 需要登录"""
    logger.debug(f"Updating resume: {resume_id}")

    try:
        current_user = request.current_user
        resume = ResumeService.get_resume(resume_id)

        if not resume:
            return ApiResponse.not_found("简历")

        # 验证权限
        if resume.owner_address != current_user:
            return ApiResponse.forbidden()

        # 获取更新数据
        data = request.get_json()
        name = data.get('name')
        company = data.get('company') or data.get('target_company')
        position = data.get('position') or data.get('target_position')

        # 更新简历
        try:
            success = ResumeService.update_resume(
                resume_id=resume_id,
                name=name,
                company=company,
                position=position
            )
        except ValueError as e:
            # 简历名称重复
            return ApiResponse.bad_request(str(e))

        if not success:
            return ApiResponse.internal_error('更新失败')

        # 返回更新后的简历
        updated_resume = ResumeService.get_resume(resume_id)

        return ApiResponse.success(
            data={'resume': ResumeService.to_dict(updated_resume)},
            message='简历更新成功'
        )

    except Exception as e:
        logger.error(f"Failed to update resume: {e}", exc_info=True)
        return ApiResponse.internal_error(f'更新失败: {str(e)}')


@resume_bp.route('/api/resumes/<resume_id>', methods=['DELETE'])
@require_auth
def delete_resume(resume_id: str):
    """删除简历（及子树） - 需要登录"""
    logger.debug(f"Deleting resume: {resume_id}")

    try:
        current_user = request.current_user
        resume = ResumeService.get_resume(resume_id)

        if not resume:
            return ApiResponse.not_found("简历")

        # 验证权限
        if resume.owner_address != current_user:
            return ApiResponse.forbidden()

        # 删除子树
        count = ResumeService.delete_resume_tree(resume_id, current_user)

        return ApiResponse.success(message=f'已删除 {count} 个简历版本')

    except PermissionError as e:
        return ApiResponse.forbidden(str(e))
    except Exception as e:
        logger.error(f"Failed to delete resume: {e}", exc_info=True)
        return ApiResponse.internal_error(f'删除失败: {str(e)}')


@resume_bp.route('/api/resume/<room_id>', methods=['GET'])
@require_auth
def get_resume_by_room(room_id: str):
    """根据面试间ID获取关联的简历信息 - 需要登录"""
    logger.debug(f"Getting resume for room: {room_id}")

    try:
        from backend.services.interview_service import RoomService

        current_user = request.current_user

        # 获取面试间
        room = RoomService.get_room(room_id)
        if not room:
            return ApiResponse.not_found("面试间")

        # 验证权限
        if room.owner_address != current_user:
            return ApiResponse.forbidden()

        # 检查是否有关联的简历
        if not room.resume_id:
            return ApiResponse.success(
                data={'resume': None},
                message='该面试间尚未关联简历'
            )

        # 获取简历信息
        resume = ResumeService.get_resume(room.resume_id)
        if not resume:
            # 简历已被删除，但面试间还在引用
            logger.warning(f"Room {room_id} references non-existent resume {room.resume_id}")
            return ApiResponse.success(
                data={'resume': None},
                message='关联的简历不存在'
            )

        # 获取MinIO中的简历数据
        resume_data = download_resume_data(room.resume_id)

        return ApiResponse.success(
            data={
                'resume': ResumeService.to_dict(resume),
                'resume_data': resume_data
            }
        )

    except Exception as e:
        logger.error(f"Failed to get resume by room: {e}", exc_info=True)
        return ApiResponse.internal_error(f'获取简历失败: {str(e)}')


# ==================== 私有辅助函数 ====================

def _save_temp_file(file):
    """保存上传文件到临时目录"""
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
        temp_path = temp_file.name
        file.save(temp_path)
    return temp_path


def _parse_pdf(file_path):
    """调用MinerU服务解析PDF"""
    from backend.clients.mineru_client import get_mineru_client
    mineru_service = get_mineru_client()
    return mineru_service.parse_pdf(file_path)


def _extract_resume_data(markdown_content):
    """使用LLM从Markdown提取结构化数据"""
    from backend.services.resume_parser import get_resume_parser
    resume_parser = get_resume_parser()
    return resume_parser.extract_resume_data(markdown_content)
