"""
简历管理Service层
负责简历的业务逻辑处理
"""

import uuid
from typing import List, Optional, Dict, Any
from backend.models.models import Resume, database
from backend.common.logger import get_logger

logger = get_logger(__name__)


class ResumeService:
    """简历管理服务"""

    @staticmethod
    def check_name_exists(owner_address: str, name: str, exclude_resume_id: Optional[str] = None) -> bool:
        """
        检查简历名称是否已存在

        Args:
            owner_address: 用户钱包地址
            name: 简历名称
            exclude_resume_id: 排除的简历ID（用于更新时检查）

        Returns:
            是否存在同名简历
        """
        query = Resume.select().where(
            (Resume.owner_address == owner_address) &
            (Resume.name == name) &
            (Resume.status == 'active')
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
        """
        创建新简历

        Args:
            owner_address: 用户钱包地址
            name: 简历名称
            file_name: 原始文件名
            file_size: 文件大小
            company: 目标公司
            position: 目标职位

        Returns:
            Resume对象

        Raises:
            ValueError: 如果简历名称已存在
        """
        # 检查名称是否重复
        if ResumeService.check_name_exists(owner_address, name):
            raise ValueError(f"简历名称 '{name}' 已存在，请使用其他名称")

        resume_id = str(uuid.uuid4())

        with database.atomic():
            resume = Resume.create(
                id=resume_id,
                name=name,
                owner_address=owner_address,
                file_name=file_name,
                file_size=file_size,
                company=company,
                position=position,
                status='active'
            )

        logger.info(f"Created resume: {resume_id} for user: {owner_address}")
        return resume

    @staticmethod
    def get_resume(resume_id: str) -> Optional[Resume]:
        """
        获取简历

        Args:
            resume_id: 简历ID

        Returns:
            Resume对象，如果不存在返回None
        """
        try:
            return Resume.get_by_id(resume_id)
        except Resume.DoesNotExist:
            return None

    @staticmethod
    def get_resumes_by_owner(owner_address: str) -> List[Resume]:
        """
        获取用户的所有简历

        Args:
            owner_address: 用户钱包地址

        Returns:
            Resume列表
        """
        return list(
            Resume.select()
            .where(
                (Resume.owner_address == owner_address) &
                (Resume.status == 'active')
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
        """
        更新简历信息

        Args:
            resume_id: 简历ID
            name: 新名称
            company: 新公司
            position: 新职位

        Returns:
            是否更新成功

        Raises:
            ValueError: 如果简历名称已存在
        """
        try:
            resume = Resume.get_by_id(resume_id)

            # 如果要更新名称，检查是否重复
            if name is not None and name != resume.name:
                if ResumeService.check_name_exists(resume.owner_address, name, exclude_resume_id=resume_id):
                    raise ValueError(f"简历名称 '{name}' 已存在，请使用其他名称")
                resume.name = name

            if company is not None:
                resume.company = company
            if position is not None:
                resume.position = position

            resume.save()
            logger.info(f"Updated resume: {resume_id}")
            return True
        except Resume.DoesNotExist:
            logger.warning(f"Resume not found: {resume_id}")
            return False

    @staticmethod
    def delete_resume(resume_id: str) -> bool:
        """
        软删除简历（标记为deleted）

        Args:
            resume_id: 简历ID

        Returns:
            是否删除成功
        """
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
        """
        获取用户简历统计信息

        Args:
            owner_address: 用户钱包地址

        Returns:
            统计信息字典
        """
        from backend.models.models import Room

        total_resumes = Resume.select().where(
            (Resume.owner_address == owner_address) &
            (Resume.status == 'active')
        ).count()

        # 统计关联的面试间数量
        linked_rooms = Room.select().where(
            (Room.owner_address == owner_address) &
            (Room.resume_id.is_null(False))
        ).count()

        return {
            'total_resumes': total_resumes,
            'linked_rooms': linked_rooms
        }

    @staticmethod
    def to_dict(resume: Resume) -> Dict[str, Any]:
        """
        将Resume对象转换为字典

        Args:
            resume: Resume对象

        Returns:
            字典格式的简历数据
        """
        from backend.models.models import Room

        # 获取使用该简历的所有面试间
        linked_rooms = Room.select().where(
            Room.resume_id == resume.id
        )
        linked_rooms_list = [{'id': room.id, 'name': room.name} for room in linked_rooms]
        linked_rooms_count = len(linked_rooms_list)

        return {
            'id': resume.id,
            'name': resume.name,
            'owner_address': resume.owner_address,
            'file_name': resume.file_name,
            'file_size': resume.file_size,
            'company': resume.company,
            'position': resume.position,
            'status': resume.status,
            'linked_rooms_count': linked_rooms_count,
            'linked_rooms': linked_rooms_list,
            'created_at': resume.created_at.isoformat() if resume.created_at else None,
            'updated_at': resume.updated_at.isoformat() if resume.updated_at else None
        }
