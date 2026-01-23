"""
数据库模型定义
使用Peewee ORM进行数据持久化
"""

from datetime import datetime
from peewee import *
import os
from dotenv import load_dotenv
from backend.common.logger import get_logger

load_dotenv()

logger = get_logger(__name__)

# 数据库配置
DATABASE_PATH = os.getenv('DATABASE_PATH', 'data/yeying_interviewer.db')

# 确保数据目录存在（除非是内存数据库）
if DATABASE_PATH != ':memory:' and os.path.dirname(DATABASE_PATH):
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)

# 数据库连接
database = SqliteDatabase(DATABASE_PATH)


class BaseModel(Model):
    """基础模型类"""
    created_at = DateTimeField(default=datetime.now)
    updated_at = DateTimeField(default=datetime.now)
    
    class Meta:
        database = database
    
    def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        return super().save(*args, **kwargs)


class Resume(BaseModel):
    """简历模型 - 支持树状版本管理"""
    id = CharField(primary_key=True)

    # 树状结构字段
    parent_id = CharField(null=True, index=True)  # 父节点ID，根节点为null
    root_id = CharField(index=True)               # 根节点ID（方便查询整棵树）
    depth = IntegerField(default=0)               # 树深度，根节点为0

    # 基本信息
    name = CharField()  # 简历名称（根节点用户自定义，子节点用时间戳）
    owner_address = CharField(max_length=64, index=True)  # 钱包地址

    # 状态：draft(编辑中) / published(已发布) / deleted(已删除)
    status = CharField(default='draft')

    # 元数据
    target_company = CharField(null=True)   # 目标公司
    target_position = CharField(null=True)  # 目标职位

    # 兼容旧字段（后续迁移后可删除）
    file_name = CharField(null=True)
    file_size = IntegerField(null=True)
    company = CharField(null=True)
    position = CharField(null=True)

    class Meta:
        table_name = 'resumes'
        indexes = (
            (('owner_address', 'status'), False),
            (('root_id',), False),
        )

    def reload(self):
        """重新从数据库加载数据"""
        fresh = Resume.get_by_id(self.id)
        for field in self._meta.sorted_fields:
            setattr(self, field.name, getattr(fresh, field.name))


class ResumeContent(BaseModel):
    """简历内容 - 结构化表单数据"""
    id = CharField(primary_key=True)
    resume_id = CharField(unique=True, index=True)  # 一对一关联 Resume

    # 基本信息
    full_name = CharField(null=True)              # 姓名
    email = CharField(null=True)
    phone = CharField(null=True)
    location = CharField(null=True)               # 所在地
    website = CharField(null=True)                # 个人网站/GitHub
    summary = TextField(null=True)                # 个人简介

    # 复杂字段存 JSON
    education = TextField(null=True)              # JSON: [{school, degree, major, start, end, gpa}]
    experience = TextField(null=True)             # JSON: [{company, title, start, end, highlights[]}]
    projects = TextField(null=True)               # JSON: [{name, description, tech[], highlights[]}]
    skills = TextField(null=True)                 # JSON: [{category, items[]}]
    certifications = TextField(null=True)         # JSON: [{name, issuer, date}]

    class Meta:
        table_name = 'resume_contents'


class Room(BaseModel):
    """面试间模型"""
    id = CharField(primary_key=True)
    memory_id = CharField(unique=True)
    name = CharField(default="面试间")
    jd_id = CharField(null=True)  # 上传的 JD ID（可选）
    owner_address = CharField(max_length=64, null=True)  # 钱包地址
    resume_id = CharField(null=True)  # 关联的简历ID

    class Meta:
        table_name = 'rooms'


class Session(BaseModel):
    """面试会话模型"""
    id = CharField(primary_key=True)
    name = CharField()
    room = ForeignKeyField(Room, backref='sessions')
    status = CharField(default='initialized')  # initialized, generating, interviewing, analyzing, round_completed
    current_round = IntegerField(default=0)  # 当前轮次号，0表示未开始

    class Meta:
        table_name = 'sessions'


class Round(BaseModel):
    """对话轮次模型"""
    id = CharField(primary_key=True)
    session = ForeignKeyField(Session, backref='rounds')
    round_index = IntegerField()
    questions_count = IntegerField(default=0)
    questions_file_path = CharField()  # MinIO中的文件路径
    round_type = CharField(default='ai_generated')  # ai_generated, manual
    current_question_index = IntegerField(default=0)  # 当前问题索引
    status = CharField(default='active')  # active, completed, paused

    class Meta:
        table_name = 'rounds'


class QuestionAnswer(BaseModel):
    """问答记录模型"""
    id = CharField(primary_key=True)
    round = ForeignKeyField(Round, backref='question_answers')
    question_index = IntegerField()  # 问题在轮次中的索引
    question_text = TextField()  # 问题内容
    answer_text = TextField(null=True)  # 用户回答
    question_category = CharField(null=True)  # 问题分类
    is_answered = BooleanField(default=False)  # 是否已回答

    class Meta:
        table_name = 'question_answers'


class RoundCompletion(BaseModel):
    """轮次完成记录模型"""

    id = CharField(primary_key=True)
    session = ForeignKeyField(Session, backref='round_completions')
    round_index = IntegerField()
    idempotency_key = CharField(unique=True)
    payload = TextField()
    occurred_at = DateTimeField()

    class Meta:
        table_name = 'round_completions'
        indexes = (
            (('session', 'round_index'), True),
        )


def create_tables() -> None:
    """创建数据库表"""
    if not database.is_closed():
        database.close()
    database.connect()
    database.create_tables([Resume, ResumeContent, Room, Session, Round, QuestionAnswer, RoundCompletion], safe=True)
    database.close()


def init_database() -> None:
    """初始化数据库"""
    create_tables()
    logger.info("Database initialized successfully")