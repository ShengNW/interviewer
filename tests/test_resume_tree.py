#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简历树状管理模块测试
TDD: 测试先行
"""

import unittest
import os
import sys
from pathlib import Path
from datetime import datetime

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 设置测试数据库
os.environ['DATABASE_PATH'] = ':memory:'


class TestResumeModel(unittest.TestCase):
    """Resume 模型测试 - 树状字段"""

    def setUp(self):
        """每个测试前的设置"""
        from backend.models.models import database, Resume, ResumeContent
        if not database.is_closed():
            database.close()
        database.connect()
        database.create_tables([Resume, ResumeContent], safe=True)

    def tearDown(self):
        """每个测试后的清理"""
        from backend.models.models import database, Resume, ResumeContent
        ResumeContent.delete().execute()
        Resume.delete().execute()
        database.close()

    def test_resume_has_tree_fields(self):
        """Resume 模型应该有树状字段: parent_id, root_id, depth"""
        from backend.models.models import Resume

        # 验证字段存在
        fields = [f.name for f in Resume._meta.sorted_fields]
        self.assertIn('parent_id', fields)
        self.assertIn('root_id', fields)
        self.assertIn('depth', fields)

    def test_resume_status_default_is_draft(self):
        """Resume 默认状态应该是 draft"""
        from backend.models.models import Resume
        import uuid

        resume_id = str(uuid.uuid4())
        resume = Resume.create(
            id=resume_id,
            name="测试简历",
            owner_address="0x1234",
            root_id=resume_id,
            depth=0
        )

        self.assertEqual(resume.status, 'draft')

    def test_resume_root_node_has_null_parent(self):
        """根节点的 parent_id 应该是 null"""
        from backend.models.models import Resume
        import uuid

        resume_id = str(uuid.uuid4())
        resume = Resume.create(
            id=resume_id,
            name="根简历",
            owner_address="0x1234",
            parent_id=None,
            root_id=resume_id,
            depth=0
        )

        self.assertIsNone(resume.parent_id)
        self.assertEqual(resume.root_id, resume_id)
        self.assertEqual(resume.depth, 0)


class TestResumeContentModel(unittest.TestCase):
    """ResumeContent 模型测试"""

    def setUp(self):
        from backend.models.models import database, Resume, ResumeContent
        if not database.is_closed():
            database.close()
        database.connect()
        database.create_tables([Resume, ResumeContent], safe=True)

    def tearDown(self):
        from backend.models.models import database, Resume, ResumeContent
        ResumeContent.delete().execute()
        Resume.delete().execute()
        database.close()

    def test_resume_content_has_basic_fields(self):
        """ResumeContent 应该有基本信息字段"""
        from backend.models.models import ResumeContent

        fields = [f.name for f in ResumeContent._meta.sorted_fields]
        self.assertIn('resume_id', fields)
        self.assertIn('full_name', fields)
        self.assertIn('email', fields)
        self.assertIn('phone', fields)
        self.assertIn('location', fields)
        self.assertIn('summary', fields)

    def test_resume_content_has_json_fields(self):
        """ResumeContent 应该有 JSON 格式的复杂字段"""
        from backend.models.models import ResumeContent

        fields = [f.name for f in ResumeContent._meta.sorted_fields]
        self.assertIn('education', fields)
        self.assertIn('experience', fields)
        self.assertIn('projects', fields)
        self.assertIn('skills', fields)
        self.assertIn('certifications', fields)

    def test_resume_content_one_to_one_with_resume(self):
        """ResumeContent 与 Resume 应该是一对一关系"""
        from backend.models.models import Resume, ResumeContent
        import uuid

        resume_id = str(uuid.uuid4())
        Resume.create(
            id=resume_id,
            name="测试简历",
            owner_address="0x1234",
            root_id=resume_id,
            depth=0
        )

        content = ResumeContent.create(
            id=str(uuid.uuid4()),
            resume_id=resume_id,
            full_name="张三",
            email="zhangsan@example.com"
        )

        self.assertEqual(content.resume_id, resume_id)


class TestCreateRootResume(unittest.TestCase):
    """创建根简历测试"""

    def setUp(self):
        from backend.models.models import database, Resume, ResumeContent
        if not database.is_closed():
            database.close()
        database.connect()
        database.create_tables([Resume, ResumeContent], safe=True)

    def tearDown(self):
        from backend.models.models import database, Resume, ResumeContent
        ResumeContent.delete().execute()
        Resume.delete().execute()
        database.close()

    def test_create_root_resume(self):
        """应该能创建根简历"""
        from backend.services.resume_service import ResumeService

        resume = ResumeService.create_root_resume(
            owner_address="0x1234",
            name="Java简历--2025",
            target_company="字节跳动",
            target_position="后端工程师"
        )

        self.assertIsNotNone(resume)
        self.assertEqual(resume.name, "Java简历--2025")
        self.assertIsNone(resume.parent_id)
        self.assertEqual(resume.root_id, resume.id)
        self.assertEqual(resume.depth, 0)
        self.assertEqual(resume.status, 'draft')

    def test_create_root_resume_also_creates_content(self):
        """创建根简历时应该同时创建空的 ResumeContent"""
        from backend.services.resume_service import ResumeService
        from backend.models.models import ResumeContent

        resume = ResumeService.create_root_resume(
            owner_address="0x1234",
            name="测试简历"
        )

        content = ResumeContent.get_or_none(ResumeContent.resume_id == resume.id)
        self.assertIsNotNone(content)


class TestForkResume(unittest.TestCase):
    """Fork 子版本测试"""

    def setUp(self):
        from backend.models.models import database, Resume, ResumeContent
        if not database.is_closed():
            database.close()
        database.connect()
        database.create_tables([Resume, ResumeContent], safe=True)

    def tearDown(self):
        from backend.models.models import database, Resume, ResumeContent
        ResumeContent.delete().execute()
        Resume.delete().execute()
        database.close()

    def test_fork_creates_child_with_correct_tree_fields(self):
        """Fork 应该创建正确的子节点"""
        from backend.services.resume_service import ResumeService

        # 创建父节点
        parent = ResumeService.create_root_resume(
            owner_address="0x1234",
            name="Java简历--2025"
        )

        # Fork 子节点
        child = ResumeService.fork_resume(parent.id, "0x1234")

        self.assertIsNotNone(child)
        self.assertEqual(child.parent_id, parent.id)
        self.assertEqual(child.root_id, parent.root_id)
        self.assertEqual(child.depth, 1)
        self.assertEqual(child.status, 'draft')

    def test_fork_name_is_timestamp(self):
        """Fork 的子节点名称应该是时间戳格式 MMddHHmm"""
        from backend.services.resume_service import ResumeService

        parent = ResumeService.create_root_resume(
            owner_address="0x1234",
            name="Java简历--2025"
        )

        child = ResumeService.fork_resume(parent.id, "0x1234")

        # 名称应该是 8 位数字 (MMddHHmm)
        self.assertEqual(len(child.name), 8)
        self.assertTrue(child.name.isdigit())

    def test_fork_copies_content(self):
        """Fork 应该复制父节点的内容"""
        from backend.services.resume_service import ResumeService
        from backend.models.models import ResumeContent

        parent = ResumeService.create_root_resume(
            owner_address="0x1234",
            name="Java简历--2025"
        )

        # 更新父节点内容
        parent_content = ResumeContent.get(ResumeContent.resume_id == parent.id)
        parent_content.full_name = "张三"
        parent_content.email = "zhangsan@example.com"
        parent_content.save()

        # Fork
        child = ResumeService.fork_resume(parent.id, "0x1234")

        # 验证子节点有相同内容
        child_content = ResumeContent.get(ResumeContent.resume_id == child.id)
        self.assertEqual(child_content.full_name, "张三")
        self.assertEqual(child_content.email, "zhangsan@example.com")

    def test_fork_permission_check(self):
        """Fork 应该检查权限"""
        from backend.services.resume_service import ResumeService

        parent = ResumeService.create_root_resume(
            owner_address="0x1234",
            name="Java简历--2025"
        )

        # 其他用户尝试 fork 应该失败
        with self.assertRaises(PermissionError):
            ResumeService.fork_resume(parent.id, "0x5678")


class TestDeleteResumeTree(unittest.TestCase):
    """删除子树测试"""

    def setUp(self):
        from backend.models.models import database, Resume, ResumeContent
        if not database.is_closed():
            database.close()
        database.connect()
        database.create_tables([Resume, ResumeContent], safe=True)

    def tearDown(self):
        from backend.models.models import database, Resume, ResumeContent
        ResumeContent.delete().execute()
        Resume.delete().execute()
        database.close()

    def test_delete_single_node(self):
        """删除单个节点"""
        from backend.services.resume_service import ResumeService
        from backend.models.models import Resume

        resume = ResumeService.create_root_resume(
            owner_address="0x1234",
            name="测试简历"
        )

        count = ResumeService.delete_resume_tree(resume.id, "0x1234")

        self.assertEqual(count, 1)
        deleted = Resume.get_by_id(resume.id)
        self.assertEqual(deleted.status, 'deleted')

    def test_delete_cascades_to_children(self):
        """删除应该级联到所有子节点"""
        from backend.services.resume_service import ResumeService
        from backend.models.models import Resume

        # 创建树结构: root -> child1 -> grandchild
        root = ResumeService.create_root_resume(
            owner_address="0x1234",
            name="根简历"
        )
        child1 = ResumeService.fork_resume(root.id, "0x1234")
        grandchild = ResumeService.fork_resume(child1.id, "0x1234")

        # 删除 root
        count = ResumeService.delete_resume_tree(root.id, "0x1234")

        self.assertEqual(count, 3)

        # 所有节点都应该是 deleted 状态
        for resume_id in [root.id, child1.id, grandchild.id]:
            resume = Resume.get_by_id(resume_id)
            self.assertEqual(resume.status, 'deleted')

    def test_delete_subtree_only(self):
        """删除子节点不应该影响父节点"""
        from backend.services.resume_service import ResumeService
        from backend.models.models import Resume

        root = ResumeService.create_root_resume(
            owner_address="0x1234",
            name="根简历"
        )
        child = ResumeService.fork_resume(root.id, "0x1234")

        # 只删除 child
        count = ResumeService.delete_resume_tree(child.id, "0x1234")

        self.assertEqual(count, 1)

        # root 应该还在
        root_after = Resume.get_by_id(root.id)
        self.assertEqual(root_after.status, 'draft')

        # child 应该被删除
        child_after = Resume.get_by_id(child.id)
        self.assertEqual(child_after.status, 'deleted')


class TestTreeDepthLimit(unittest.TestCase):
    """树深度限制测试"""

    def setUp(self):
        from backend.models.models import database, Resume, ResumeContent
        if not database.is_closed():
            database.close()
        database.connect()
        database.create_tables([Resume, ResumeContent], safe=True)

    def tearDown(self):
        from backend.models.models import database, Resume, ResumeContent
        ResumeContent.delete().execute()
        Resume.delete().execute()
        database.close()

    def test_max_depth_is_5(self):
        """最大深度应该是 5 层 (depth 0-4)"""
        from backend.services.resume_service import ResumeService

        # 创建 5 层深的树
        current = ResumeService.create_root_resume(
            owner_address="0x1234",
            name="根简历"
        )

        for i in range(4):
            current = ResumeService.fork_resume(current.id, "0x1234")
            self.assertEqual(current.depth, i + 1)

        # 尝试创建第 6 层应该失败
        with self.assertRaises(ValueError) as context:
            ResumeService.fork_resume(current.id, "0x1234")

        self.assertIn("深度", str(context.exception))


class TestStatusTransition(unittest.TestCase):
    """状态流转测试"""

    def setUp(self):
        from backend.models.models import database, Resume, ResumeContent
        if not database.is_closed():
            database.close()
        database.connect()
        database.create_tables([Resume, ResumeContent], safe=True)

    def tearDown(self):
        from backend.models.models import database, Resume, ResumeContent
        ResumeContent.delete().execute()
        Resume.delete().execute()
        database.close()

    def test_publish_changes_status_to_published(self):
        """发布应该将状态改为 published"""
        from backend.services.resume_service import ResumeService

        resume = ResumeService.create_root_resume(
            owner_address="0x1234",
            name="测试简历"
        )

        ResumeService.publish_resume(resume.id, "0x1234")

        resume.reload()
        self.assertEqual(resume.status, 'published')

    def test_edit_published_changes_status_to_draft(self):
        """编辑已发布的简历应该将状态改回 draft"""
        from backend.services.resume_service import ResumeService

        resume = ResumeService.create_root_resume(
            owner_address="0x1234",
            name="测试简历"
        )

        # 先发布
        ResumeService.publish_resume(resume.id, "0x1234")

        # 再编辑
        ResumeService.update_content(resume.id, "0x1234", full_name="李四")

        resume.reload()
        self.assertEqual(resume.status, 'draft')

    def test_unpublish_changes_status_to_draft(self):
        """取消发布应该将状态改回 draft"""
        from backend.services.resume_service import ResumeService

        resume = ResumeService.create_root_resume(
            owner_address="0x1234",
            name="测试简历"
        )

        ResumeService.publish_resume(resume.id, "0x1234")
        ResumeService.unpublish_resume(resume.id, "0x1234")

        resume.reload()
        self.assertEqual(resume.status, 'draft')


class TestInterviewRoomLinking(unittest.TestCase):
    """面试间关联测试"""

    def setUp(self):
        from backend.models.models import database, Resume, ResumeContent, Room
        if not database.is_closed():
            database.close()
        database.connect()
        database.create_tables([Resume, ResumeContent, Room], safe=True)

    def tearDown(self):
        from backend.models.models import database, Resume, ResumeContent, Room
        Room.delete().execute()
        ResumeContent.delete().execute()
        Resume.delete().execute()
        database.close()

    def test_only_published_can_link_to_room(self):
        """只有已发布的简历才能关联到面试间"""
        from backend.services.resume_service import ResumeService
        from backend.services.interview_service import RoomService

        resume = ResumeService.create_root_resume(
            owner_address="0x1234",
            name="测试简历"
        )

        room = RoomService.create_room("测试面试间", owner_address="0x1234")

        # draft 状态不能关联
        with self.assertRaises(ValueError) as context:
            ResumeService.link_to_room(resume.id, room.id, "0x1234")

        self.assertIn("已发布", str(context.exception))

    def test_published_can_link_to_room(self):
        """已发布的简历可以关联到面试间"""
        from backend.services.resume_service import ResumeService
        from backend.services.interview_service import RoomService
        from backend.models.models import Room

        resume = ResumeService.create_root_resume(
            owner_address="0x1234",
            name="测试简历"
        )

        # 先发布
        ResumeService.publish_resume(resume.id, "0x1234")

        room = RoomService.create_room("测试面试间", owner_address="0x1234")

        # 现在可以关联
        ResumeService.link_to_room(resume.id, room.id, "0x1234")

        room_after = Room.get_by_id(room.id)
        self.assertEqual(room_after.resume_id, resume.id)

    def test_get_available_resumes_only_returns_published(self):
        """获取可用简历应该只返回已发布的"""
        from backend.services.resume_service import ResumeService

        # 创建多个简历
        resume1 = ResumeService.create_root_resume(
            owner_address="0x1234",
            name="简历1"
        )
        resume2 = ResumeService.create_root_resume(
            owner_address="0x1234",
            name="简历2"
        )
        resume3 = ResumeService.create_root_resume(
            owner_address="0x1234",
            name="简历3"
        )

        # 只发布 resume2
        ResumeService.publish_resume(resume2.id, "0x1234")

        # 获取可用简历
        available = ResumeService.get_available_resumes("0x1234")

        self.assertEqual(len(available), 1)
        self.assertEqual(available[0].id, resume2.id)


class TestGetResumeTreeList(unittest.TestCase):
    """获取简历树列表测试"""

    def setUp(self):
        from backend.models.models import database, Resume, ResumeContent
        if not database.is_closed():
            database.close()
        database.connect()
        database.create_tables([Resume, ResumeContent], safe=True)

    def tearDown(self):
        from backend.models.models import database, Resume, ResumeContent
        ResumeContent.delete().execute()
        Resume.delete().execute()
        database.close()

    def test_get_trees_returns_nested_structure(self):
        """获取树列表应该返回嵌套结构"""
        from backend.services.resume_service import ResumeService

        root = ResumeService.create_root_resume(
            owner_address="0x1234",
            name="Java简历--2025"
        )
        child = ResumeService.fork_resume(root.id, "0x1234")

        trees = ResumeService.get_resume_trees("0x1234")

        self.assertEqual(len(trees), 1)
        self.assertEqual(trees[0]['id'], root.id)
        self.assertEqual(trees[0]['name'], "Java简历--2025")
        self.assertEqual(len(trees[0]['children']), 1)
        self.assertEqual(trees[0]['children'][0]['id'], child.id)

    def test_get_trees_excludes_deleted(self):
        """获取树列表应该排除已删除的节点"""
        from backend.services.resume_service import ResumeService

        root1 = ResumeService.create_root_resume(
            owner_address="0x1234",
            name="简历1"
        )
        root2 = ResumeService.create_root_resume(
            owner_address="0x1234",
            name="简历2"
        )

        # 删除 root2
        ResumeService.delete_resume_tree(root2.id, "0x1234")

        trees = ResumeService.get_resume_trees("0x1234")

        self.assertEqual(len(trees), 1)
        self.assertEqual(trees[0]['id'], root1.id)


if __name__ == '__main__':
    print("Running resume tree management tests (TDD)...")
    unittest.main()
