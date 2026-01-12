# 简历树状管理模块设计文档

> 创建日期: 2025-01-12
> 状态: 待实现

## 1. 概述

### 1.1 目标

重构简历管理模块，支持：
- 树状版本管理（类似 Git 分支模式）
- 表单式简历编辑
- RenderCV 渲染生成 PDF
- 三态状态管理（编辑中/已发布/已删除）

### 1.2 核心特性

| 特性 | 说明 |
|------|------|
| 树状结构 | 用户可基于任意版本创建子版本，独立编辑互不影响 |
| 表单编辑 | 结构化表单输入，后端转换为 RenderCV YAML |
| PDF 渲染 | 编辑时可预览，发布时生成正式 PDF |
| 状态流转 | 编辑中 ↔ 已发布，已发布可用于面试 |

---

## 2. 数据模型

### 2.1 Resume 表（重构）

```python
class Resume(BaseModel):
    """简历模型 - 支持树状版本管理"""
    id = CharField(primary_key=True)

    # 树状结构
    parent_id = CharField(null=True, index=True)  # 父节点ID，根节点为null
    root_id = CharField(index=True)               # 根节点ID（方便查询整棵树）
    depth = IntegerField(default=0)               # 树深度，根节点为0

    # 基本信息
    name = CharField()                            # 显示名称（根节点用户自定义，子节点用时间戳）
    owner_address = CharField(index=True)

    # 状态：draft(编辑中) / published(已发布) / deleted(已删除)
    status = CharField(default='draft')

    # 元数据
    target_company = CharField(null=True)         # 目标公司
    target_position = CharField(null=True)        # 目标职位

    class Meta:
        table_name = 'resumes'
        indexes = (
            (('owner_address', 'status'), False),
            (('root_id',), False),
        )
```

### 2.2 ResumeContent 表（新增）

```python
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
```

### 2.3 字段说明

**education JSON 结构：**
```json
[
    {
        "school": "北京大学",
        "degree": "硕士",
        "major": "计算机科学",
        "start": "2015-09",
        "end": "2018-06",
        "gpa": "3.8/4.0"
    }
]
```

**experience JSON 结构：**
```json
[
    {
        "company": "字节跳动",
        "title": "高级工程师",
        "start": "2020-03",
        "end": "present",
        "highlights": [
            "负责推荐系统核心模块开发",
            "优化接口性能，QPS 提升 300%"
        ]
    }
]
```

**projects JSON 结构：**
```json
[
    {
        "name": "分布式任务调度系统",
        "description": "支持百万级任务的分布式调度平台",
        "tech": ["Go", "Redis", "Kafka"],
        "highlights": [
            "设计并实现核心调度算法",
            "支持动态扩缩容"
        ]
    }
]
```

**skills JSON 结构：**
```json
[
    {
        "category": "编程语言",
        "items": ["Python", "Go", "Java"]
    },
    {
        "category": "框架",
        "items": ["Flask", "FastAPI", "Spring Boot"]
    }
]
```

---

## 3. MinIO 存储结构

### 3.1 路径规划

```
resumes/
├── {resume_id}/
│   ├── content.json          # 简历内容（备份/同步用）
│   ├── rendercv.yaml         # RenderCV 格式文件
│   └── published.pdf         # 已发布的正式 PDF
│
└── temp/
    └── {user_address}/
        └── preview_{timestamp}.pdf   # 临时预览 PDF（定期清理）
```

### 3.2 存储策略

| 文件 | 生成时机 | 生命周期 |
|------|----------|----------|
| `content.json` | 每次保存表单 | 跟随简历 |
| `rendercv.yaml` | 每次保存/预览 | 跟随简历 |
| `published.pdf` | 点击发布 | 跟随简历，发布时覆盖 |
| `preview_*.pdf` | 点击预览 | 临时，24小时后清理 |

### 3.3 清理机制

- 删除简历时，删除整个 `resumes/{resume_id}/` 目录
- 定时任务清理 `temp/` 下超过 24 小时的预览文件

---

## 4. API 接口设计

### 4.1 接口列表

```
# 简历 CRUD
POST   /api/resumes                    # 创建根简历
POST   /api/resumes/{id}/fork          # 基于某版本创建子版本
GET    /api/resumes                    # 获取用户简历树列表
GET    /api/resumes/{id}               # 获取简历详情（含内容）
PUT    /api/resumes/{id}               # 更新简历元信息
DELETE /api/resumes/{id}               # 删除简历（及子树）

# 简历内容
PUT    /api/resumes/{id}/content       # 保存表单内容
GET    /api/resumes/{id}/content       # 获取表单内容

# 状态变更
POST   /api/resumes/{id}/publish       # 发布（生成 PDF，状态→已发布）
POST   /api/resumes/{id}/unpublish     # 取消发布（状态→编辑中）

# PDF 相关
POST   /api/resumes/{id}/preview       # 生成预览 PDF，返回临时 URL
GET    /api/resumes/{id}/pdf           # 获取已发布 PDF 下载链接

# 树操作
GET    /api/resumes/{id}/tree          # 获取某节点的完整子树

# 面试间关联
GET    /api/resumes/available          # 获取可用于面试的简历（仅已发布）
```

### 4.2 关键接口详情

#### POST /api/resumes - 创建根简历

**请求：**
```json
{
    "name": "Java简历--2025",
    "target_company": "字节跳动",
    "target_position": "后端工程师"
}
```

**响应：**
```json
{
    "code": 200,
    "data": {
        "resume": {
            "id": "uuid-xxx",
            "name": "Java简历--2025",
            "parent_id": null,
            "root_id": "uuid-xxx",
            "depth": 0,
            "status": "draft"
        }
    }
}
```

#### POST /api/resumes/{id}/fork - 创建子版本

**响应：**
```json
{
    "code": 200,
    "data": {
        "resume": {
            "id": "uuid-child",
            "name": "01122030",
            "parent_id": "uuid-parent",
            "root_id": "uuid-root",
            "depth": 1,
            "status": "draft"
        }
    },
    "message": "子版本创建成功"
}
```

#### GET /api/resumes - 获取简历树列表

**响应：**
```json
{
    "code": 200,
    "data": {
        "trees": [
            {
                "id": "uuid-root-1",
                "name": "Java简历--2025",
                "status": "published",
                "target_position": "后端工程师",
                "updated_at": "2025-01-08T21:16:00",
                "children": [
                    {
                        "id": "uuid-child-1",
                        "name": "01082116",
                        "status": "draft",
                        "children": []
                    }
                ]
            }
        ],
        "stats": {
            "total": 5,
            "published": 2,
            "draft": 3
        }
    }
}
```

---

## 5. 状态流转

### 5.1 状态定义

| 状态 | 值 | 可编辑 | 可用于面试 |
|------|-----|--------|------------|
| 编辑中 | `draft` | ✅ | ❌ |
| 已发布 | `published` | ❌ (编辑则变回draft) | ✅ |
| 已删除 | `deleted` | ❌ | ❌ |

### 5.2 状态转换规则

```
                    publish()
    ┌─────────────────────────────────┐
    │                                 ▼
 [draft] ◄────────────────────── [published]
    │         edit() / unpublish()    │
    │                                 │
    │  delete()                       │ delete()
    ▼                                 ▼
 [deleted] ◄─────────────────────────┘
```

### 5.3 关键行为

| 操作 | 状态变化 | 说明 |
|------|----------|------|
| 编辑已发布简历 | published → draft | 自动变回编辑中 |
| fork | 新节点为 draft | 复制内容，独立编辑 |
| 删除 | 级联删除子树 | 所有子节点标记 deleted |

---

## 6. 树操作逻辑

### 6.1 创建子版本 (Fork)

```python
def fork_resume(parent_id: str, user: str) -> Resume:
    parent = Resume.get_by_id(parent_id)

    # 验证权限
    if parent.owner_address != user:
        raise PermissionError("无权操作")

    # 检查深度限制
    if parent.depth >= 4:
        raise ValueError("已达最大深度限制（5层）")

    # 生成时间戳名称: MMddHHmm
    timestamp_name = datetime.now().strftime("%m%d%H%M")

    # 创建子节点
    child_id = str(uuid4())
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

    # 复制内容
    parent_content = ResumeContent.get(resume_id=parent.id)
    ResumeContent.create(
        id=str(uuid4()),
        resume_id=child.id,
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

    # 复制 MinIO 文件
    copy_resume_files(parent.id, child.id)

    return child
```

### 6.2 删除子树

```python
def delete_resume_tree(resume_id: str, user: str) -> int:
    """删除节点及所有子孙节点，返回删除数量"""

    resume = Resume.get_by_id(resume_id)
    if resume.owner_address != user:
        raise PermissionError("无权操作")

    # 递归获取所有子孙节点
    def get_descendants(node_id):
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

        # 删除 MinIO 文件
        for rid in all_ids:
            delete_resume_folder(rid)

    return len(all_ids)
```

### 6.3 深度限制

最大深度限制为 **5 层**（depth 0-4）：
```
根节点(0) → 子版本(1) → 子版本(2) → 子版本(3) → 子版本(4)
```

---

## 7. RenderCV 集成

### 7.1 转换流程

```
表单数据 (JSON) → RenderCV YAML → PDF
```

### 7.2 YAML 模板

```yaml
cv:
  name: {{ full_name }}
  location: {{ location }}
  email: {{ email }}
  phone: {{ phone }}
  website: {{ website }}

  sections:
    summary:
      - {{ summary }}

    education:
      {% for edu in education %}
      - institution: {{ edu.school }}
        area: {{ edu.major }}
        degree: {{ edu.degree }}
        start_date: {{ edu.start }}
        end_date: {{ edu.end }}
        {% if edu.gpa %}
        highlights:
          - "GPA: {{ edu.gpa }}"
        {% endif %}
      {% endfor %}

    experience:
      {% for exp in experience %}
      - company: {{ exp.company }}
        position: {{ exp.title }}
        start_date: {{ exp.start }}
        end_date: {{ exp.end }}
        highlights:
          {% for h in exp.highlights %}
          - {{ h }}
          {% endfor %}
      {% endfor %}

    projects:
      {% for proj in projects %}
      - name: {{ proj.name }}
        date: {{ proj.tech | join(', ') }}
        highlights:
          - {{ proj.description }}
          {% for h in proj.highlights %}
          - {{ h }}
          {% endfor %}
      {% endfor %}

    skills:
      {% for skill in skills %}
      - label: {{ skill.category }}
        details: {{ skill.items | join(', ') }}
      {% endfor %}
```

### 7.3 渲染服务

```python
# backend/services/rendercv_service.py

import subprocess
import tempfile
import os
from jinja2 import Template
from backend.common.logger import get_logger

logger = get_logger(__name__)

class RenderCVService:
    """RenderCV 渲染服务"""

    YAML_TEMPLATE = """..."""  # 上述模板

    def __init__(self):
        self.template = Template(self.YAML_TEMPLATE)

    def generate_yaml(self, content: dict) -> str:
        """将表单内容转换为 RenderCV YAML"""
        return self.template.render(**content)

    def render_pdf(self, yaml_content: str) -> str:
        """调用 RenderCV 生成 PDF，返回 PDF 文件路径"""

        # 创建临时目录
        work_dir = tempfile.mkdtemp()
        yaml_path = os.path.join(work_dir, "resume.yaml")

        # 写入 YAML 文件
        with open(yaml_path, 'w', encoding='utf-8') as f:
            f.write(yaml_content)

        # 调用 RenderCV CLI
        result = subprocess.run(
            ['rendercv', 'render', yaml_path],
            cwd=work_dir,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            logger.error(f"RenderCV failed: {result.stderr}")
            raise RuntimeError(f"PDF 渲染失败: {result.stderr}")

        # 查找生成的 PDF
        for f in os.listdir(work_dir):
            if f.endswith('.pdf'):
                return os.path.join(work_dir, f)

        raise RuntimeError("未找到生成的 PDF 文件")

    def preview(self, resume_id: str) -> str:
        """生成预览 PDF，返回临时 URL"""
        content = get_resume_content(resume_id)
        yaml_content = self.generate_yaml(content)
        pdf_path = self.render_pdf(yaml_content)

        # 上传到 MinIO temp 目录
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        object_name = f"resumes/temp/{resume_id}/preview_{timestamp}.pdf"
        minio_client.upload_file(object_name, pdf_path)

        # 生成预签名 URL（24小时有效）
        return minio_client.get_presigned_url(object_name, expires_hours=24)

    def publish(self, resume_id: str) -> str:
        """发布简历，生成正式 PDF"""
        content = get_resume_content(resume_id)
        yaml_content = self.generate_yaml(content)
        pdf_path = self.render_pdf(yaml_content)

        # 保存 YAML 文件
        yaml_object = f"resumes/{resume_id}/rendercv.yaml"
        minio_client.upload_json(yaml_object, {"yaml": yaml_content})

        # 保存正式 PDF
        pdf_object = f"resumes/{resume_id}/published.pdf"
        minio_client.upload_file(pdf_object, pdf_path)

        # 更新状态
        Resume.update(status='published').where(Resume.id == resume_id).execute()

        return minio_client.get_presigned_url(pdf_object)
```

---

## 8. 面试间集成

### 8.1 关联规则

```python
def link_resume_to_room(room_id: str, resume_id: str, user: str):
    """将简历关联到面试间"""
    resume = Resume.get_by_id(resume_id)

    # 验证状态
    if resume.status != 'published':
        raise ValueError("只有已发布的简历才能用于面试")

    # 验证权限
    if resume.owner_address != user:
        raise PermissionError("无权操作此简历")

    # 关联
    room = Room.get_by_id(room_id)
    room.resume_id = resume_id
    room.save()
```

### 8.2 状态联动

| 场景 | 行为 |
|------|------|
| 简历被面试间使用中，用户编辑 | 状态变 draft，面试间关联保留 |
| 简历被删除 | 面试间的 `resume_id` 置空 |
| 查询可用简历 | 只返回 `status='published'` 的简历 |

---

## 9. 数据迁移

### 9.1 现有数据迁移策略

```python
def migrate_existing_resumes():
    """迁移现有简历数据"""

    resumes = Resume.select().where(Resume.status == 'active')

    for resume in resumes:
        # 设置树状字段
        resume.parent_id = None
        resume.root_id = resume.id
        resume.depth = 0

        # 状态映射: active → draft
        resume.status = 'draft'

        # 字段重命名
        resume.target_company = resume.company
        resume.target_position = resume.position

        resume.save()

        # 创建 ResumeContent（从 MinIO 读取现有数据）
        existing_data = download_resume_data(resume.id)
        if existing_data:
            ResumeContent.create(
                id=str(uuid4()),
                resume_id=resume.id,
                full_name=existing_data.get('name'),
                email=existing_data.get('email'),
                phone=existing_data.get('phone'),
                # ... 映射其他字段
            )
```

---

## 10. 实现计划

### 10.1 改动文件列表

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `backend/models/models.py` | 修改 | Resume 模型重构，新增 ResumeContent |
| `backend/services/resume_service.py` | 重写 | 树操作、状态流转逻辑 |
| `backend/controllers/resume_controller.py` | 重写 | 新增 fork/publish/preview 等接口 |
| `backend/clients/minio_client.py` | 扩展 | 新增简历文件操作函数 |
| `backend/services/rendercv_service.py` | 新增 | RenderCV 转换和渲染服务 |
| `requirements.txt` | 修改 | 添加 rendercv 依赖 |
| `frontend/templates/resumes.html` | 重写 | 树状展示 UI |
| `scripts/migrate_resumes.py` | 新增 | 数据迁移脚本 |

### 10.2 实现顺序

1. 数据模型改造（Resume + ResumeContent）
2. 数据库迁移脚本（兼容现有数据）
3. ResumeService 重写（树操作核心逻辑）
4. RenderCV 集成服务
5. API 接口实现
6. MinIO 存储函数扩展
7. 前端树状展示
8. 测试验证

---

## 11. 风险与注意事项

1. **RenderCV 依赖**: 需要确认服务器环境是否支持 LaTeX（RenderCV 底层依赖）
2. **树深度**: 限制最大 5 层，避免性能问题
3. **并发编辑**: 当前设计不支持多人协作，同一用户多端编辑需考虑冲突
4. **PDF 生成耗时**: 可能需要异步处理，避免请求超时

---

## 附录：状态图

```
                         ┌──────────────────┐
                         │                  │
        ┌───────────────►│     draft        │◄──────────────┐
        │                │   (编辑中)        │               │
        │                └────────┬─────────┘               │
        │                         │                         │
        │                         │ publish()               │
        │                         ▼                         │
        │                ┌──────────────────┐               │
        │   edit()       │                  │   unpublish() │
        └────────────────│   published      │───────────────┘
                         │   (已发布)        │
                         └────────┬─────────┘
                                  │
                                  │ delete()
                                  ▼
                         ┌──────────────────┐
                         │                  │
                         │    deleted       │
                         │   (已删除)        │
                         └──────────────────┘
```
