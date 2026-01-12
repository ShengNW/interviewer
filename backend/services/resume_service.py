"""
简历管理Service层
负责简历的业务逻辑处理 - 支持树状版本管理
"""

import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from backend.models.models import Resume, ResumeContent, Room, database
from backend.common.logger import get_logger

logger = get_logger(__name__)

# 树最大深度限制
MAX_TREE_DEPTH = 5


class ResumeService:
    """简历管理服务 - 支持树状版本管理"""

    # ==================== 树状管理新方法 ====================

    @staticmethod
    def create_root_resume(
        owner_address: str,
        name: str,
        target_company: Optional[str] = None,
        target_position: Optional[str] = None
    ) -> Resume:
        """
        创建根简历（树的根节点）

        Args:
            owner_address: 用户钱包地址
            name: 简历名称（用户自定义）
            target_company: 目标公司
            target_position: 目标职位

        Returns:
            Resume对象
        """
        resume_id = str(uuid.uuid4())

        with database.atomic():
            resume = Resume.create(
                id=resume_id,
                parent_id=None,  # 根节点无父节点
                root_id=resume_id,  # 根节点的 root_id 是自己
                depth=0,
                name=name,
                owner_address=owner_address,
                status='draft',
                target_company=target_company,
                target_position=target_position
            )

            # 同时创建空的 ResumeContent
            ResumeContent.create(
                id=str(uuid.uuid4()),
                resume_id=resume_id
            )

        logger.info(f"Created root resume: {resume_id} for user: {owner_address}")
        return resume

    @staticmethod
    def fork_resume(parent_id: str, user: str) -> Resume:
        """
        基于父节点创建子版本

        Args:
            parent_id: 父节点ID
            user: 当前用户地址

        Returns:
            新创建的子节点 Resume

        Raises:
            PermissionError: 无权操作
            ValueError: 超过深度限制
        """
        parent = Resume.get_by_id(parent_id)

        # 权限检查
        if parent.owner_address != user:
            raise PermissionError("无权操作此简历")

        # 深度检查
        if parent.depth >= MAX_TREE_DEPTH - 1:
            raise ValueError(f"已达最大深度限制（{MAX_TREE_DEPTH}层）")

        # 生成时间戳名称: MMddHHmm
        timestamp_name = datetime.now().strftime("%m%d%H%M")

        child_id = str(uuid.uuid4())

        with database.atomic():
            # 创建子节点
            child = Resume.create(
                id=child_id,
                parent_id=parent.id,
                root_id=parent.root_id,
                depth=parent.depth + 1,
                name=timestamp_name,
                owner_address=user,
                status='draft',
                target_company=parent.target_company,
                target_position=parent.target_position
            )

            # 复制父节点内容
            parent_content = ResumeContent.get_or_none(
                ResumeContent.resume_id == parent.id
            )

            if parent_content:
                ResumeContent.create(
                    id=str(uuid.uuid4()),
                    resume_id=child_id,
                    full_name=parent_content.full_name,
                    email=parent_content.email,
                    phone=parent_content.phone,
                    location=parent_content.location,
                    website=parent_content.website,
                    summary=parent_content.summary,
                    education=parent_content.education,
                    experience=parent_content.experience,
                    projects=parent_content.projects,
                    skills=parent_content.skills,
                    certifications=parent_content.certifications
                )
            else:
                # 父节点没有内容，创建空的
                ResumeContent.create(
                    id=str(uuid.uuid4()),
                    resume_id=child_id
                )

        logger.info(f"Forked resume: {child_id} from {parent_id}")
        return child

    @staticmethod
    def delete_resume_tree(resume_id: str, user: str) -> int:
        """
        删除节点及所有子孙节点

        Args:
            resume_id: 要删除的节点ID
            user: 当前用户地址

        Returns:
            删除的节点数量

        Raises:
            PermissionError: 无权操作
        """
        resume = Resume.get_by_id(resume_id)

        if resume.owner_address != user:
            raise PermissionError("无权操作此简历")

        # 递归获取所有子孙节点
        def get_descendants(node_id: str) -> List[str]:
            children = Resume.select().where(
                (Resume.parent_id == node_id) &
                (Resume.status != 'deleted')
            )
            result = [node_id]
            for child in children:
                result.extend(get_descendants(child.id))
            return result

        all_ids = get_descendants(resume_id)

        # 批量软删除
        with database.atomic():
            Resume.update(status='deleted').where(
                Resume.id.in_(all_ids)
            ).execute()

        logger.info(f"Deleted resume tree: {resume_id}, total {len(all_ids)} nodes")
        return len(all_ids)

    @staticmethod
    def publish_resume(resume_id: str, user: str) -> None:
        """
        发布简历

        Args:
            resume_id: 简历ID
            user: 当前用户地址

        Raises:
            PermissionError: 无权操作
        """
        resume = Resume.get_by_id(resume_id)

        if resume.owner_address != user:
            raise PermissionError("无权操作此简历")

        resume.status = 'published'
        resume.save()

        logger.info(f"Published resume: {resume_id}")

    @staticmethod
    def unpublish_resume(resume_id: str, user: str) -> None:
        """
        取消发布简历

        Args:
            resume_id: 简历ID
            user: 当前用户地址

        Raises:
            PermissionError: 无权操作
        """
        resume = Resume.get_by_id(resume_id)

        if resume.owner_address != user:
            raise PermissionError("无权操作此简历")

        resume.status = 'draft'
        resume.save()

        logger.info(f"Unpublished resume: {resume_id}")

    @staticmethod
    def update_content(
        resume_id: str,
        user: str,
        **content_fields
    ) -> ResumeContent:
        """
        更新简历内容（如果是已发布状态，会自动变回 draft）

        Args:
            resume_id: 简历ID
            user: 当前用户地址
            **content_fields: 要更新的内容字段

        Returns:
            更新后的 ResumeContent

        Raises:
            PermissionError: 无权操作
        """
        resume = Resume.get_by_id(resume_id)

        if resume.owner_address != user:
            raise PermissionError("无权操作此简历")

        # 如果是已发布状态，自动变回 draft
        if resume.status == 'published':
            resume.status = 'draft'
            resume.save()
            logger.info(f"Resume {resume_id} status changed to draft due to edit")

        # 更新内容
        content = ResumeContent.get_or_none(ResumeContent.resume_id == resume_id)

        if not content:
            content = ResumeContent.create(
                id=str(uuid.uuid4()),
                resume_id=resume_id,
                **content_fields
            )
        else:
            for field, value in content_fields.items():
                if hasattr(content, field):
                    setattr(content, field, value)
            content.save()

        logger.info(f"Updated content for resume: {resume_id}")
        return content

    @staticmethod
    def link_to_room(resume_id: str, room_id: str, user: str) -> None:
        """
        将简历关联到面试间（仅已发布的简历可以关联）

        Args:
            resume_id: 简历ID
            room_id: 面试间ID
            user: 当前用户地址

        Raises:
            ValueError: 简历未发布
            PermissionError: 无权操作
        """
        resume = Resume.get_by_id(resume_id)

        if resume.owner_address != user:
            raise PermissionError("无权操作此简历")

        if resume.status != 'published':
            raise ValueError("只有已发布的简历才能用于面试")

        room = Room.get_by_id(room_id)

        if room.owner_address != user:
            raise PermissionError("无权操作此面试间")

        room.resume_id = resume_id
        room.save()

        logger.info(f"Linked resume {resume_id} to room {room_id}")

    @staticmethod
    def get_available_resumes(user: str) -> List[Resume]:
        """
        获取可用于面试的简历（仅已发布状态）

        Args:
            user: 用户地址

        Returns:
            已发布的简历列表
        """
        return list(
            Resume.select().where(
                (Resume.owner_address == user) &
                (Resume.status == 'published')
            ).order_by(Resume.updated_at.desc())
        )

    @staticmethod
    def get_resume_trees(user: str) -> List[Dict[str, Any]]:
        """
        获取用户的简历树列表

        Args:
            user: 用户地址

        Returns:
            树状结构的简历列表
        """
        # 获取所有活跃简历
        resumes = Resume.select().where(
            (Resume.owner_address == user) &
            (Resume.status != 'deleted')
        ).order_by(Resume.created_at)

        # 构建 id → node 映射
        nodes = {}
        for r in resumes:
            nodes[r.id] = {
                'id': r.id,
                'name': r.name,
                'status': r.status,
                'depth': r.depth,
                'parent_id': r.parent_id,
                'target_company': r.target_company,
                'target_position': r.target_position,
                'created_at': r.created_at.isoformat() if r.created_at else None,
                'updated_at': r.updated_at.isoformat() if r.updated_at else None,
                'children': []
            }

        # 构建树
        roots = []
        for r in resumes:
            if r.parent_id is None:
                roots.append(nodes[r.id])
            elif r.parent_id in nodes:
                nodes[r.parent_id]['children'].append(nodes[r.id])

        return roots

    # ==================== 兼容旧方法 ====================

    @staticmethod
    def check_name_exists(owner_address: str, name: str, exclude_resume_id: Optional[str] = None) -> bool:
        """检查简历名称是否已存在"""
        query = Resume.select().where(
            (Resume.owner_address == owner_address) &
            (Resume.name == name) &
            (Resume.status != 'deleted')
        )

        if exclude_resume_id:
            query = query.where(Resume.id != exclude_resume_id)

        return query.exists()

    @staticmethod
    def create_resume(
        owner_address: str,
        name: str,
        file_name: Optional[str] = None,
        file_size: Optional[int] = None,
        company: Optional[str] = None,
        position: Optional[str] = None
    ) -> Resume:
        """创建新简历（兼容旧接口）"""
        if ResumeService.check_name_exists(owner_address, name):
            raise ValueError(f"简历名称 '{name}' 已存在，请使用其他名称")

        resume_id = str(uuid.uuid4())

        with database.atomic():
            resume = Resume.create(
                id=resume_id,
                parent_id=None,
                root_id=resume_id,
                depth=0,
                name=name,
                owner_address=owner_address,
                file_name=file_name,
                file_size=file_size,
                company=company,
                position=position,
                target_company=company,
                target_position=position,
                status='draft'
            )

            # 创建空的 ResumeContent
            ResumeContent.create(
                id=str(uuid.uuid4()),
                resume_id=resume_id
            )

        logger.info(f"Created resume: {resume_id} for user: {owner_address}")
        return resume

    @staticmethod
    def get_resume(resume_id: str) -> Optional[Resume]:
        """获取简历"""
        try:
            return Resume.get_by_id(resume_id)
        except Resume.DoesNotExist:
            return None

    @staticmethod
    def get_resumes_by_owner(owner_address: str) -> List[Resume]:
        """获取用户的所有简历"""
        return list(
            Resume.select()
            .where(
                (Resume.owner_address == owner_address) &
                (Resume.status != 'deleted')
            )
            .order_by(Resume.created_at.desc())
        )

    @staticmethod
    def update_resume(
        resume_id: str,
        name: Optional[str] = None,
        company: Optional[str] = None,
        position: Optional[str] = None
    ) -> bool:
        """更新简历信息"""
        try:
            resume = Resume.get_by_id(resume_id)

            if name is not None and name != resume.name:
                if ResumeService.check_name_exists(resume.owner_address, name, exclude_resume_id=resume_id):
                    raise ValueError(f"简历名称 '{name}' 已存在，请使用其他名称")
                resume.name = name

            if company is not None:
                resume.company = company
                resume.target_company = company
            if position is not None:
                resume.position = position
                resume.target_position = position

            resume.save()
            logger.info(f"Updated resume: {resume_id}")
            return True
        except Resume.DoesNotExist:
            logger.warning(f"Resume not found: {resume_id}")
            return False

    @staticmethod
    def delete_resume(resume_id: str) -> bool:
        """软删除简历"""
        try:
            resume = Resume.get_by_id(resume_id)
            resume.status = 'deleted'
            resume.save()
            logger.info(f"Deleted resume: {resume_id}")
            return True
        except Resume.DoesNotExist:
            logger.warning(f"Resume not found: {resume_id}")
            return False

    @staticmethod
    def get_resume_stats(owner_address: str) -> Dict[str, int]:
        """获取用户简历统计信息"""
        total_resumes = Resume.select().where(
            (Resume.owner_address == owner_address) &
            (Resume.status != 'deleted')
        ).count()

        published_resumes = Resume.select().where(
            (Resume.owner_address == owner_address) &
            (Resume.status == 'published')
        ).count()

        draft_resumes = Resume.select().where(
            (Resume.owner_address == owner_address) &
            (Resume.status == 'draft')
        ).count()

        linked_rooms = Room.select().where(
            (Room.owner_address == owner_address) &
            (Room.resume_id.is_null(False))
        ).count()

        return {
            'total_resumes': total_resumes,
            'published': published_resumes,
            'draft': draft_resumes,
            'linked_rooms': linked_rooms
        }

    @staticmethod
    def to_dict(resume: Resume) -> Dict[str, Any]:
        """将Resume对象转换为字典"""
        linked_rooms = Room.select().where(
            Room.resume_id == resume.id
        )
        linked_rooms_list = [{'id': room.id, 'name': room.name} for room in linked_rooms]
        linked_rooms_count = len(linked_rooms_list)

        return {
            'id': resume.id,
            'name': resume.name,
            'parent_id': resume.parent_id,
            'root_id': resume.root_id,
            'depth': resume.depth,
            'owner_address': resume.owner_address,
            'file_name': resume.file_name,
            'file_size': resume.file_size,
            'target_company': resume.target_company,
            'target_position': resume.target_position,
            'status': resume.status,
            'linked_rooms_count': linked_rooms_count,
            'linked_rooms': linked_rooms_list,
            'created_at': resume.created_at.isoformat() if resume.created_at else None,
            'updated_at': resume.updated_at.isoformat() if resume.updated_at else None
        }
