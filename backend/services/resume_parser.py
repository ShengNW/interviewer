"""
简历解析服务
"""

import json
import re
from typing import Dict, Any, Optional, List
from backend.clients.llm.qwen_client import QwenClient
from backend.clients.llm.prompts.resume_prompts import get_resume_extraction_prompt
from backend.common.logger import get_logger

logger = get_logger(__name__)


class ResumeParser:
    """简历内容解析器，从Markdown提取结构化数据"""

    def __init__(self):
        self.qwen_client = QwenClient()

    def extract_resume_data(self, markdown_content: str) -> Optional[Dict[str, Any]]:
        """
        从Markdown内容中提取结构化简历数据

        Args:
            markdown_content: OCR解析后的Markdown格式内容

        Returns:
            结构化简历数据字典，格式与 ResumeContent 表对应：
            {
                "full_name": "姓名",
                "email": "邮箱",
                "phone": "电话",
                "location": "所在地",
                "website": "个人网站",
                "summary": "个人简介",
                "education": [{school, degree, major, start, end}],
                "experience": [{company, title, start, end, highlights[]}],
                "projects": [{name, description, highlights[]}],
                "skills": [{category, items[]}],
                "certifications": [{name, issuer, date}]
            }
        """
        try:
            if not markdown_content or not markdown_content.strip():
                logger.error("Empty markdown content")
                return None

            # 生成提取提示词
            prompt = get_resume_extraction_prompt(markdown_content)

            # 调用LLM提取结构化数据
            messages = [{"role": "user", "content": prompt}]
            response = self.qwen_client.chat_completion(messages, temperature=0.3, max_tokens=4000)

            if not response:
                logger.error("No response from LLM")
                return None

            # 解析JSON响应
            resume_data = self._parse_json_response(response)

            if not resume_data:
                logger.error("Failed to parse JSON from LLM response")
                return None

            # 验证数据完整性
            validated_data = self._validate_resume_data(resume_data)

            return validated_data

        except Exception as e:
            logger.error(f"Error extracting resume data: {e}", exc_info=True)
            return None

    def _parse_json_response(self, response: str) -> Optional[Dict[str, Any]]:
        """解析LLM返回的JSON响应"""
        try:
            # 清理响应内容，移除可能的markdown代码块标记
            cleaned_response = response.strip()

            # 移除```json 和 ```标记
            if cleaned_response.startswith('```'):
                # 找到第一个{和最后一个}
                start_idx = cleaned_response.find('{')
                end_idx = cleaned_response.rfind('}')
                if start_idx != -1 and end_idx != -1:
                    cleaned_response = cleaned_response[start_idx:end_idx + 1]

            # 尝试解析JSON
            resume_data = json.loads(cleaned_response)
            return resume_data

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            logger.debug(f"Response content: {response[:500]}")

            # 尝试使用正则表达式提取JSON对象
            try:
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    resume_data = json.loads(json_match.group(0))
                    return resume_data
            except Exception as ex:
                logger.error(f"Regex extraction also failed: {ex}")

            return None

        except Exception as e:
            logger.error(f"Error parsing JSON response: {e}", exc_info=True)
            return None

    def _validate_resume_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """验证和规范化简历数据，确保与 ResumeContent 格式一致"""
        validated = {
            "full_name": "",
            "email": "",
            "phone": "",
            "location": "",
            "website": "",
            "summary": "",
            "education": [],
            "experience": [],
            "projects": [],
            "skills": [],
            "certifications": []
        }

        # 基本字符串字段
        string_fields = ["full_name", "email", "phone", "location", "website", "summary"]
        for field in string_fields:
            if field in data and data[field]:
                validated[field] = str(data[field]).strip()

        # 教育经历
        if "education" in data and isinstance(data["education"], list):
            validated["education"] = self._validate_education(data["education"])

        # 工作经历
        if "experience" in data and isinstance(data["experience"], list):
            validated["experience"] = self._validate_experience(data["experience"])

        # 项目经历
        if "projects" in data and isinstance(data["projects"], list):
            validated["projects"] = self._validate_projects(data["projects"])

        # 技能
        if "skills" in data and isinstance(data["skills"], list):
            validated["skills"] = self._validate_skills(data["skills"])

        # 证书
        if "certifications" in data and isinstance(data["certifications"], list):
            validated["certifications"] = self._validate_certifications(data["certifications"])

        return validated

    def _validate_education(self, education_list: List) -> List[Dict]:
        """验证教育经历"""
        result = []
        for edu in education_list:
            if not isinstance(edu, dict):
                continue
            item = {
                "school": str(edu.get("school", "")).strip(),
                "degree": str(edu.get("degree", "")).strip(),
                "major": str(edu.get("major", "")).strip(),
                "start": str(edu.get("start", "")).strip(),
                "end": str(edu.get("end", "")).strip()
            }
            # 至少要有学校名称
            if item["school"]:
                result.append(item)
        return result

    def _validate_experience(self, experience_list: List) -> List[Dict]:
        """验证工作经历"""
        result = []
        for exp in experience_list:
            if not isinstance(exp, dict):
                continue
            item = {
                "company": str(exp.get("company", "")).strip(),
                "title": str(exp.get("title", "")).strip(),
                "start": str(exp.get("start", "")).strip(),
                "end": str(exp.get("end", "")).strip(),
                "highlights": []
            }
            # 处理 highlights
            highlights = exp.get("highlights", [])
            if isinstance(highlights, list):
                item["highlights"] = [str(h).strip() for h in highlights if h and str(h).strip()]
            # 至少要有公司名称
            if item["company"]:
                result.append(item)
        return result

    def _validate_projects(self, projects_list: List) -> List[Dict]:
        """验证项目经历"""
        result = []
        for proj in projects_list:
            if not isinstance(proj, dict):
                continue
            item = {
                "name": str(proj.get("name", "")).strip(),
                "description": str(proj.get("description", "")).strip(),
                "highlights": []
            }
            # 处理 highlights
            highlights = proj.get("highlights", [])
            if isinstance(highlights, list):
                item["highlights"] = [str(h).strip() for h in highlights if h and str(h).strip()]
            # 至少要有项目名称
            if item["name"]:
                result.append(item)
        return result

    def _validate_skills(self, skills_list: List) -> List[Dict]:
        """验证技能"""
        result = []
        for skill in skills_list:
            if not isinstance(skill, dict):
                continue
            category = str(skill.get("category", "")).strip()
            items = skill.get("items", [])
            if isinstance(items, list):
                cleaned_items = [str(i).strip() for i in items if i and str(i).strip()]
                if cleaned_items:
                    result.append({
                        "category": category or "其他",
                        "items": cleaned_items
                    })
        return result

    def _validate_certifications(self, cert_list: List) -> List[Dict]:
        """验证证书"""
        result = []
        for cert in cert_list:
            if not isinstance(cert, dict):
                continue
            item = {
                "name": str(cert.get("name", "")).strip(),
                "issuer": str(cert.get("issuer", "")).strip(),
                "date": str(cert.get("date", "")).strip()
            }
            # 至少要有证书名称
            if item["name"]:
                result.append(item)
        return result


# 全局服务实例
_resume_parser = None


def get_resume_parser() -> ResumeParser:
    """获取简历解析器实例（单例模式）"""
    global _resume_parser
    if _resume_parser is None:
        _resume_parser = ResumeParser()
    return _resume_parser
