# -*- coding: utf-8 -*-
"""
使用 ReportLab 生成专业排版的 PDF 简历（支持中文）
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
import os


class ResumePDFGenerator:
    def __init__(self, filename):
        self.filename = filename
        self.doc = SimpleDocTemplate(
            filename,
            pagesize=A4,
            rightMargin=2*cm,
            leftMargin=2*cm,
            topMargin=1.5*cm,
            bottomMargin=1.5*cm
        )
        self.styles = getSampleStyleSheet()
        self.elements = []

        # 定义颜色
        self.primary_color = HexColor('#1a1a2e')
        self.secondary_color = HexColor('#666666')

        # 注册中文字体
        self.register_chinese_fonts()

        # 自定义样式
        self.setup_styles()

    def register_chinese_fonts(self):
        """注册中文字体"""
        try:
            # 尝试注册系统字体
            font_paths = [
                "C:/Windows/Fonts/msyh.ttc",  # 微软雅黑
                "C:/Windows/Fonts/simsun.ttc",  # 宋体
                "C:/Windows/Fonts/simhei.ttf",  # 黑体
                "C:/Windows/Fonts/simkai.ttf",  # 楷体
            ]

            self.chinese_font = None
            for font_path in font_paths:
                if os.path.exists(font_path):
                    try:
                        pdfmetrics.registerFont(TTFont('ChineseFont', font_path))
                        self.chinese_font = 'ChineseFont'
                        print(f"成功注册字体: {font_path}")
                        break
                    except Exception as e:
                        print(f"注册字体 {font_path} 失败: {e}")
                        continue

            # 如果没有找到系统字体，使用 CID 字体
            if not self.chinese_font:
                try:
                    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
                    self.chinese_font = 'STSong-Light'
                    print("使用内置 CID 字体 STSong-Light")
                except Exception as e:
                    print(f"注册 CID 字体失败: {e}")
                    self.chinese_font = 'Helvetica'

        except Exception as e:
            print(f"字体注册失败: {e}")
            self.chinese_font = 'Helvetica'

    def setup_styles(self):
        """设置自定义样式"""
        # 根据字体可用性选择字体
        if self.chinese_font:
            font_name = self.chinese_font
            bold_font = self.chinese_font
        else:
            font_name = 'Helvetica'
            bold_font = 'Helvetica-Bold'

        # 姓名样式
        self.styles.add(ParagraphStyle(
            'Name',
            parent=self.styles['Heading1'],
            fontSize=22,
            fontName=bold_font,
            textColor=self.primary_color,
            alignment=TA_CENTER,
            spaceAfter=6
        ))

        # 联系信息样式
        self.styles.add(ParagraphStyle(
            'Contact',
            parent=self.styles['Normal'],
            fontSize=10,
            fontName=font_name,
            textColor=self.secondary_color,
            alignment=TA_CENTER,
            spaceAfter=12
        ))

        # 章节标题样式
        self.styles.add(ParagraphStyle(
            'SectionTitle',
            parent=self.styles['Heading2'],
            fontSize=12,
            fontName=bold_font,
            textColor=self.primary_color,
            spaceBefore=12,
            spaceAfter=6
        ))

        # 公司名称样式
        self.styles.add(ParagraphStyle(
            'Company',
            parent=self.styles['Normal'],
            fontSize=11,
            fontName=bold_font,
            textColor=HexColor('#333333'),
            spaceAfter=2
        ))

        # 职位样式
        self.styles.add(ParagraphStyle(
            'Position',
            parent=self.styles['Normal'],
            fontSize=10,
            fontName=font_name,
            textColor=HexColor('#444444'),
            spaceAfter=2
        ))

        # 日期样式
        self.styles.add(ParagraphStyle(
            'Date',
            parent=self.styles['Normal'],
            fontSize=10,
            fontName=font_name,
            textColor=self.secondary_color,
            alignment=TA_RIGHT
        ))

        # 描述样式
        self.styles.add(ParagraphStyle(
            'Description',
            parent=self.styles['Normal'],
            fontSize=10,
            fontName=font_name,
            textColor=HexColor('#555555'),
            spaceAfter=4
        ))

        # 技术栈样式
        self.styles.add(ParagraphStyle(
            'TechStack',
            parent=self.styles['Normal'],
            fontSize=9,
            fontName=font_name,
            textColor=HexColor('#555555'),
            spaceAfter=6
        ))

        # 技能类别样式
        self.styles.add(ParagraphStyle(
            'SkillCategory',
            parent=self.styles['Normal'],
            fontSize=10,
            fontName=bold_font,
            textColor=HexColor('#333333'),
            spaceAfter=2
        ))

        # 技能内容样式
        self.styles.add(ParagraphStyle(
            'SkillItems',
            parent=self.styles['Normal'],
            fontSize=10,
            fontName=font_name,
            textColor=HexColor('#333333'),
            spaceAfter=4
        ))

        # 列表项样式
        self.styles.add(ParagraphStyle(
            'BulletItem',
            parent=self.styles['Normal'],
            fontSize=10,
            fontName=font_name,
            textColor=HexColor('#333333'),
            leftIndent=20,
            bulletIndent=10,
            spaceAfter=4,
            leading=14
        ))

        # 学校样式
        self.styles.add(ParagraphStyle(
            'School',
            parent=self.styles['Normal'],
            fontSize=11,
            fontName=bold_font,
            textColor=HexColor('#333333'),
            spaceAfter=2
        ))

        # 专业样式
        self.styles.add(ParagraphStyle(
            'Major',
            parent=self.styles['Normal'],
            fontSize=10,
            fontName=font_name,
            textColor=HexColor('#333333'),
            spaceAfter=2
        ))

    def add_name_header(self, name, phone, email):
        """添加姓名和联系信息头部"""
        # 姓名
        self.elements.append(Paragraph(name, self.styles['Name']))

        # 联系信息
        contact_text = f"{phone}  |  {email}"
        self.elements.append(Paragraph(contact_text, self.styles['Contact']))

    def add_section_title(self, title):
        """添加章节标题"""
        self.elements.append(Spacer(1, 6))
        self.elements.append(HRFlowable(
            width="100%",
            thickness=1.5,
            color=self.primary_color,
            spaceAfter=6,
            spaceBefore=6
        ))
        self.elements.append(Paragraph(title, self.styles['SectionTitle']))

    def add_education(self, school, major, degree, start_date, end_date):
        """添加教育背景"""
        self.add_section_title("EDUCATION")

        # 学校和专业
        school_text = f"{school}"
        self.elements.append(Paragraph(school_text, self.styles['School']))

        major_text = f"{major}  |  {degree}"
        self.elements.append(Paragraph(major_text, self.styles['Major']))

        # 日期
        date_text = f"{start_date} - {end_date}"
        self.elements.append(Paragraph(date_text, self.styles['Date']))

    def add_skills(self, skills_dict):
        """添加技能部分"""
        self.add_section_title("TECHNICAL SKILLS")

        for category, skills in skills_dict.items():
            # 类别
            self.elements.append(Paragraph(
                f"<b>{category}:</b>  {', '.join(skills)}",
                self.styles['SkillItems']
            ))

    def add_experience(self, company, position, start_date, end_date, highlights):
        """添加工作/项目经历"""
        # 公司和职位
        company_text = f"{company}"
        self.elements.append(Paragraph(company_text, self.styles['Company']))

        position_text = f"{position}"
        self.elements.append(Paragraph(position_text, self.styles['Position']))

        # 日期
        date_text = f"{start_date} - {end_date}"
        self.elements.append(Paragraph(date_text, self.styles['Date']))

        # 项目简介
        if "description" in highlights:
            self.elements.append(Paragraph(
                highlights["description"],
                self.styles['Description']
            ))

        # 技术栈
        if "tech_stack" in highlights:
            tech_text = f"<b>Tech Stack:</b> {highlights['tech_stack']}"
            self.elements.append(Paragraph(tech_text, self.styles['TechStack']))

        # 要点
        if "bullets" in highlights:
            for bullet in highlights["bullets"]:
                bullet_text = f"<bullet>&bull;</bullet>{bullet}"
                self.elements.append(Paragraph(
                    bullet_text,
                    self.styles['BulletItem']
                ))

            # 增加间距
            self.elements.append(Spacer(1, 8))

    def build(self):
        """构建 PDF"""
        self.doc.build(self.elements)


def create_optimized_resume_pdf():
    """创建优化后的 PDF 简历"""
    # 输出文件路径
    script_dir = os.path.dirname(os.path.abspath(__file__))
    pdf_path = os.path.join(script_dir, "Resume.pdf")

    # 创建 PDF 生成器
    generator = ResumePDFGenerator(pdf_path)

    # ============== 联系信息 ==============
    generator.add_name_header(
        name="Your Name",
        phone="1XX-XXXX-XXXX",
        email="your-email@example.com"
    )

    # ============== 教育背景 ==============
    generator.add_education(
        school="武昌首义学院",
        major="计算机科学与技术（华为云班）",
        degree="本科在读",
        start_date="2023.09",
        end_date="2027.06"
    )

    # ============== 专业技能 ==============
    skills = {
        "AI 后端与并发": [
            "Python asyncio 非阻塞编程",
            "协程并发与线程池隔离调优",
            "HTTP SSE 流式传输",
            "TCP 背压机制"
        ],
        "RAG 与检索优化": [
            "双阶段混合召回 (Dense/Sparse)",
            "RRF 倒数排名融合",
            "Cross-Encoder 精排",
            "向量语义缓存 (VSS)"
        ],
        "Agent 与智能体": [
            "状态机 (FSM) 架构",
            "ReAct 确定性运行时",
            "Tool Calling 机制",
            "任务规划与迭代控制"
        ],
        "文档解析与 ETL": [
            "多模态文档解析",
            "长上下文切分策略",
            "表格防断裂机制",
            "VLM 图像语义提取"
        ],
        "云原生与中间件": [
            "FastAPI",
            "Redis / Qdrant / Neo4j",
            "Celery 分布式调度",
            "Docker / MinIO"
        ]
    }
    generator.add_skills(skills)

    # ============== 项目经历 1: KGateway ==============
    generator.add_experience(
        company="KGateway - 企业级混合多模态 Agent 知识库网关",
        position="AI 后端研发",
        start_date="2026.04",
        end_date="2026.05",
        highlights={
            "description": "面向企业大模型落地场景的 AI 基础设施网关，基于 FastAPI 构建流式异步管道，解决长尾延迟、Token 成本高及多租户隔离问题。",
            "tech_stack": "FastAPI, Qdrant, Redis, Neo4j, BGE-Reranker, LangFuse, Locust",
            "bullets": [
                "设计 HTTP SSE 双向解耦流式网关，实现「状态流 + 文本流」架构；首创 asyncio.wait(FIRST_COMPLETED) 双路竞速守护机制，在模型思考期维持 200ms 高频客户端心跳检测，异常离线时强杀连接，有效阻止 Token 盗刷。",
                "基于 Qdrant HNSW 索引原生 Filter 实现 AND 逻辑预过滤位图剪枝，在索引遍历阶段完成租户数据硬隔离，规避后过滤导致的召回率衰减问题。",
                "构建 Dense/Sparse 双阶段混排管线：采用 2-gram 倒排索引 + RRF 融合算法（k=60）动态排序；通过 asyncio.to_thread 安全卸载 BGE-Reranker 精排推理，避免阻塞主事件循环。",
                "摒弃黑盒框架，基于 FSM 状态机自研确定性 Agent 运行时（Planner → Tool Executor → Fallback），注入最大 4 次迭代沙箱，彻底杜绝无限循环风险。",
                "实现 RediSearch 向量语义缓存，对语义相似度 >0.96 的请求实现 5ms 毫秒级拦截，Token 成本降低 42.6%；手写三态自修复熔断器防御下游 API 速率雪崩。"
            ]
        }
    )

    # ============== 项目经历 2: OmniParse ==============
    generator.add_experience(
        company="OmniParse - 企业级异步多模态文档解析与 ETL 引擎",
        position="AI 数据架构",
        start_date="2026.03",
        end_date="2026.04",
        highlights={
            "description": "面向大模型异构知识库场景的分布式数据清洗与入库流水线，支持复杂 PDF、跨页表格等多源数据，提升脏数据结构化提取的准确率。",
            "tech_stack": "Celery, Redis, MinIO, Unstructured, Qdrant, Docker Compose",
            "bullets": [
                "设计 FastAPI + Celery 异步解耦架构，将耗时文件解析从主业务分离；实现流式写入 MinIO 对象存储并生成临时签名直链，高并发场景下任务提交延迟降至毫秒级。",
                "自研 EnterpriseChunker 格式感知切分器：针对 Token 暴力切分导致的表格语义破碎问题，实现跨页表格整体还原为 Parent Doc，生成摘要 Child Chunk 并保留指针关系，杜绝碎表引发的模型幻觉。",
                "在结构化解析阶段透传 PDF 内嵌图片至轻量级 VLM 生成 Image Caption，完成富文本原位合并，最大程度保留长上下文图文关联性。",
                "设计全流式 Generator Pipeline，将 Qdrant 入库控制在 100 points/batch，高并发场景空间复杂度压制至 O(1)；基于 Docker Compose 实现多级 Worker 一键部署。"
            ]
        }
    )

    # 构建 PDF
    generator.build()
    print(f"PDF 简历已生成: {pdf_path}")


if __name__ == "__main__":
    create_optimized_resume_pdf()
