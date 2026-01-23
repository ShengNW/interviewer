"""
RenderCV 集成服务
负责将简历内容转换为 YAML 并渲染 PDF
"""

import os
import json
import tempfile
import subprocess
import shutil
from typing import Dict, Any, Optional
from datetime import datetime
from jinja2 import Template
from backend.common.logger import get_logger
from backend.models.models import ResumeContent, Resume

logger = get_logger(__name__)


# RenderCV YAML 模板
# 注意：RenderCV 对 phone 有严格格式验证，需要国际格式如 +86 138 0000 0000
# 日期格式要求：YYYY-MM 或 YYYY，空值用 present 表示
RENDERCV_TEMPLATE = """# yaml-language-server: $schema=https://raw.githubusercontent.com/rendercv/rendercv/refs/tags/v2.3/schema.json
cv:
  name: "{{ full_name or '未命名' }}"
{% if location %}
  location: "{{ location }}"
{% endif %}
{% if email and '@' in email %}
  email: {{ email }}
{% endif %}
{% if phone and phone | length == 11 and phone.isdigit() %}
  phone: "+86 {{ phone[:3] }} {{ phone[3:7] }} {{ phone[7:] }}"
{% endif %}
{% if website %}
  website: {{ website }}
{% endif %}
  sections:
{% if summary %}
    个人简介:
      - "{{ summary | replace('"', "'") }}"
{% endif %}
{% if education %}
    教育经历:
{% for edu in education %}
{% if edu.school %}
      - institution: "{{ edu.school | replace('"', "'") }}"
        area: "{{ edu.major | default('') | replace('"', "'") }}"
        degree: "{{ edu.degree | default('') | replace('"', "'") }}"
{% if edu.start %}
        start_date: "{{ edu.start }}"
{% endif %}
        end_date: "{{ edu.end | default('present') }}"
{% if edu.gpa %}
        highlights:
          - "GPA: {{ edu.gpa }}"
{% endif %}
{% endif %}
{% endfor %}
{% endif %}
{% if experience %}
    工作经历:
{% for exp in experience %}
{% if exp.company %}
      - company: "{{ exp.company | replace('"', "'") }}"
        position: "{{ exp.title | default('') | replace('"', "'") }}"
{% if exp.start %}
        start_date: "{{ exp.start }}"
{% endif %}
        end_date: "{{ exp.end | default('present') }}"
{% if exp.highlights %}
        highlights:
{% for h in exp.highlights %}
          - "{{ h | replace('"', "'") }}"
{% endfor %}
{% endif %}
{% endif %}
{% endfor %}
{% endif %}
{% if projects %}
    项目经历:
{% for proj in projects %}
{% if proj.name %}
      - name: "{{ proj.name | replace('"', "'") }}"
{% if proj.description %}
        summary: "{{ proj.description | replace('"', "'") }}"
{% endif %}
{% if proj.highlights %}
        highlights:
{% for h in proj.highlights %}
          - "{{ h | replace('"', "'") }}"
{% endfor %}
{% endif %}
{% endif %}
{% endfor %}
{% endif %}
{% if skills %}
    技能特长:
{% for skill in skills %}
{% if skill['items'] %}
      - label: "{{ skill.category | default('技能') | replace('"', "'") }}"
        details: "{{ skill['items'] | join(', ') }}"
{% endif %}
{% endfor %}
{% endif %}
{% if certifications %}
    证书资质:
{% for cert in certifications %}
{% if cert.name %}
      - bullet: "{{ cert.name | replace('"', "'") }}{% if cert.issuer %} - {{ cert.issuer | replace('"', "'") }}{% endif %}{% if cert.date %} ({{ cert.date }}){% endif %}"
{% endif %}
{% endfor %}
{% endif %}
design:
  theme: classic
  page:
    size: a4
"""


class RenderCVService:
    """RenderCV 渲染服务"""

    def __init__(self):
        self.template = Template(RENDERCV_TEMPLATE)

    def _clean_phone(self, phone: str) -> str:
        """清理电话号码，只保留数字"""
        if not phone:
            return ""
        # 只保留数字
        digits = ''.join(c for c in phone if c.isdigit())
        # 如果是11位中国手机号，返回
        if len(digits) == 11 and digits.startswith('1'):
            return digits
        # 如果有+86前缀（13位），去掉前缀
        if len(digits) == 13 and digits.startswith('86'):
            return digits[2:]
        # 不是有效手机号，返回空
        return ""

    def content_to_dict(self, content: ResumeContent) -> Dict[str, Any]:
        """将 ResumeContent 转换为字典（解析 JSON 字段）"""
        return {
            'full_name': content.full_name,
            'email': content.email,
            'phone': self._clean_phone(content.phone),  # 清理电话号码
            'location': content.location,
            'website': content.website,
            'summary': content.summary,
            'education': json.loads(content.education) if content.education else [],
            'experience': json.loads(content.experience) if content.experience else [],
            'projects': json.loads(content.projects) if content.projects else [],
            'skills': json.loads(content.skills) if content.skills else [],
            'certifications': json.loads(content.certifications) if content.certifications else []
        }

    def generate_yaml(self, content_dict: Dict[str, Any]) -> str:
        """将简历内容字典转换为 RenderCV YAML"""
        return self.template.render(**content_dict)

    def render_pdf(self, yaml_content: str) -> str:
        """
        调用 RenderCV 生成 PDF

        Args:
            yaml_content: YAML 格式的简历内容

        Returns:
            生成的 PDF 文件路径

        Raises:
            RuntimeError: 渲染失败
        """
        # 创建临时工作目录
        work_dir = tempfile.mkdtemp(prefix='rendercv_')

        try:
            # 写入 YAML 文件
            yaml_path = os.path.join(work_dir, 'resume.yaml')
            with open(yaml_path, 'w', encoding='utf-8') as f:
                f.write(yaml_content)

            logger.info(f"RenderCV: generating PDF from {yaml_path}")
            logger.debug(f"YAML content:\n{yaml_content[:500]}...")

            # 调用 RenderCV CLI
            result = subprocess.run(
                ['rendercv', 'render', yaml_path],
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=120  # 2分钟超时
            )

            # 记录完整输出用于调试
            if result.stdout:
                logger.debug(f"RenderCV stdout: {result.stdout}")
            if result.stderr:
                logger.debug(f"RenderCV stderr: {result.stderr}")

            if result.returncode != 0:
                error_msg = result.stderr or result.stdout or "未知错误"
                logger.error(f"RenderCV failed (code {result.returncode}): {error_msg}")
                # 也输出YAML内容帮助调试
                logger.error(f"Failed YAML:\n{yaml_content}")
                raise RuntimeError(f"PDF 渲染失败: {error_msg}")

            # 查找生成的 PDF 文件
            # RenderCV 会在 rendercv_output 目录下生成 PDF
            output_dir = os.path.join(work_dir, 'rendercv_output')

            if not os.path.exists(output_dir):
                # 可能直接在当前目录
                output_dir = work_dir

            for root, dirs, files in os.walk(output_dir):
                for f in files:
                    if f.endswith('.pdf'):
                        pdf_path = os.path.join(root, f)
                        logger.info(f"RenderCV: PDF generated at {pdf_path}")
                        return pdf_path

            # 如果没找到PDF，列出目录内容帮助调试
            all_files = []
            for root, dirs, files in os.walk(work_dir):
                for f in files:
                    all_files.append(os.path.join(root, f))
            logger.error(f"No PDF found. Files in work_dir: {all_files}")

            raise RuntimeError("未找到生成的 PDF 文件")

        except subprocess.TimeoutExpired:
            raise RuntimeError("PDF 渲染超时")
        except Exception as e:
            logger.error(f"RenderCV error: {e}")
            raise

    def preview(self, resume_id: str) -> str:
        """
        生成预览 PDF

        Args:
            resume_id: 简历 ID

        Returns:
            临时 PDF 文件路径
        """
        content = ResumeContent.get_or_none(ResumeContent.resume_id == resume_id)

        if not content:
            raise ValueError("简历内容不存在")

        content_dict = self.content_to_dict(content)
        yaml_content = self.generate_yaml(content_dict)

        return self.render_pdf(yaml_content)

    def publish(self, resume_id: str) -> str:
        """
        发布简历，生成正式 PDF 并保存到 MinIO

        Args:
            resume_id: 简历 ID

        Returns:
            PDF 在 MinIO 的路径
        """
        from backend.clients.minio_client import minio_client

        # 生成 PDF
        pdf_path = self.preview(resume_id)

        try:
            # 保存 YAML 到 MinIO
            content = ResumeContent.get(ResumeContent.resume_id == resume_id)
            content_dict = self.content_to_dict(content)
            yaml_content = self.generate_yaml(content_dict)

            yaml_object = f"resumes/{resume_id}/rendercv.yaml"
            minio_client.upload_json(yaml_object, {'yaml': yaml_content})

            # 保存 PDF 到 MinIO
            pdf_object = f"resumes/{resume_id}/published.pdf"
            minio_client.upload_file(pdf_object, pdf_path)

            logger.info(f"Published resume PDF: {pdf_object}")
            return pdf_object

        finally:
            # 清理临时文件
            if pdf_path and os.path.exists(pdf_path):
                work_dir = os.path.dirname(os.path.dirname(pdf_path))
                if work_dir.startswith(tempfile.gettempdir()):
                    shutil.rmtree(work_dir, ignore_errors=True)

    def get_preview_url(self, resume_id: str, expires_hours: int = 1) -> str:
        """
        生成预览 PDF 并返回临时 URL

        Args:
            resume_id: 简历 ID
            expires_hours: URL 有效期（小时）

        Returns:
            预签名 URL
        """
        from backend.clients.minio_client import minio_client

        pdf_path = self.preview(resume_id)

        try:
            # 上传到临时目录
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            temp_object = f"resumes/temp/{resume_id}/preview_{timestamp}.pdf"
            minio_client.upload_file(temp_object, pdf_path)

            # 生成预签名 URL（inline=True 使浏览器内联显示而非下载）
            url = minio_client.get_presigned_url(
                temp_object,
                expires_hours,
                inline=True,
                content_type='application/pdf'
            )
            return url

        finally:
            # 清理临时文件
            if pdf_path and os.path.exists(pdf_path):
                work_dir = os.path.dirname(os.path.dirname(pdf_path))
                if work_dir.startswith(tempfile.gettempdir()):
                    shutil.rmtree(work_dir, ignore_errors=True)

    def get_published_url(self, resume_id: str, expires_hours: int = 24) -> Optional[str]:
        """
        获取已发布 PDF 的下载 URL

        Args:
            resume_id: 简历 ID
            expires_hours: URL 有效期（小时）

        Returns:
            预签名 URL，如果文件不存在返回 None
        """
        from backend.clients.minio_client import minio_client

        pdf_object = f"resumes/{resume_id}/published.pdf"

        if minio_client.object_exists(pdf_object):
            return minio_client.get_presigned_url(
                pdf_object,
                expires_hours,
                inline=True,
                content_type='application/pdf'
            )

        return None


# 单例实例
_rendercv_service = None


def get_rendercv_service() -> RenderCVService:
    """获取 RenderCV 服务实例"""
    global _rendercv_service
    if _rendercv_service is None:
        _rendercv_service = RenderCVService()
    return _rendercv_service
