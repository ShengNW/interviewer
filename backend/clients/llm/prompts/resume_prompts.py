"""
简历解析提示词模块
"""


def get_resume_extraction_prompt(markdown_content: str) -> str:
    """
    从Markdown格式的简历中提取结构化数据的提示词

    Args:
        markdown_content: OCR解析后的Markdown格式简历内容

    Returns:
        LLM提示词
    """
    prompt = f"""你是一位专业的简历分析助手，请从以下Markdown格式的简历中提取完整的结构化信息。

简历内容：
{markdown_content}

请仔细分析简历内容，提取所有信息并以JSON格式返回。

**返回格式要求：**
- 必须返回标准的JSON格式
- 不要包含任何解释或额外的文字，只返回JSON对象
- 如果某个字段无法提取，使用空字符串、null或空数组
- 日期格式统一为 "YYYY-MM" 或 "YYYY"，如 "2020-06"、"2021"
- "至今"或"present"统一用 "至今" 表示

**JSON Schema（严格按此格式）：**
```json
{{
  "full_name": "姓名",
  "email": "邮箱地址",
  "phone": "电话号码",
  "location": "所在城市",
  "website": "个人网站/GitHub/LinkedIn等",
  "summary": "个人简介/自我评价",
  "education": [
    {{
      "school": "学校名称",
      "degree": "学历（本科/硕士/博士/专科）",
      "major": "专业",
      "start": "入学时间",
      "end": "毕业时间"
    }}
  ],
  "experience": [
    {{
      "company": "公司名称",
      "title": "职位名称",
      "start": "入职时间",
      "end": "离职时间或至今",
      "highlights": [
        "工作职责和成就1",
        "工作职责和成就2"
      ]
    }}
  ],
  "projects": [
    {{
      "name": "项目名称",
      "description": "项目描述（一句话概括）",
      "highlights": [
        "项目职责和成果1",
        "项目职责和成果2"
      ]
    }}
  ],
  "skills": [
    {{
      "category": "技能类别（如：编程语言、框架、数据库、工具等）",
      "items": ["技能1", "技能2", "技能3"]
    }}
  ],
  "certifications": [
    {{
      "name": "证书名称",
      "issuer": "颁发机构",
      "date": "获得时间"
    }}
  ]
}}
```

**提取要点：**
1. 教育经历按时间倒序排列（最近的在前）
2. 工作经历按时间倒序排列
3. 技能按类别分组，常见分类：编程语言、框架/库、数据库、开发工具、云服务等
4. 如果简历中技能没有分类，请根据技能类型自动分类
5. 项目经历如果在工作经历中，也要单独提取到projects中
6. highlights要具体、量化（如有数据），每条不超过50字

请严格按照JSON格式返回，不要添加任何markdown代码块标记："""

    return prompt


def get_resume_validation_prompt(extracted_data: dict, original_markdown: str) -> str:
    """
    验证和补充简历提取数据的提示词

    Args:
        extracted_data: 已提取的结构化数据
        original_markdown: 原始Markdown内容

    Returns:
        LLM提示词
    """
    prompt = f"""你是一位专业的简历审核助手，请检查以下提取的简历数据是否完整和准确。

原始简历（Markdown）：
{original_markdown}

已提取的数据（JSON）：
{extracted_data}

请执行以下任务：
1. 检查提取的信息是否准确，有无遗漏重要技能或项目
2. 如果有遗漏，补充遗漏的信息
3. 优化项目描述，使其更加清晰和结构化
4. 确保技能列表完整且去重

返回优化后的JSON数据，格式与原数据相同，不要添加解释："""

    return prompt
