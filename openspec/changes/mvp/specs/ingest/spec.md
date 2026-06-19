# Spec: Ingest

## Purpose

从多种输入源提取清洁内容（优先 Markdown）。采用**插件架构**——每个 input type 注册多个 backend，按优先级 fallback。

## Backend Registry

```python
INGESTER_REGISTRY = {
    "pdf": [
        # 智能路由 (skill: pdf-parsing 决策树):
        ("pdfmux",      PDFMuxIngester),       # MIT, auto-routing, best headings, MCP built-in
        ("paddleocr",   PaddleOCRIngester),    # Apache 2.0, best Chinese OCR
        ("docling",     DoclingIngester),      # MIT, best tables/formulas
        ("mineru",      MinerUIngester),       # MCP available, Chinese docs, 84 langs
        ("marker",      MarkerIngester),       # Surya OCR (GPL, research only)
        ("liteparse",   LiteParseIngester),    # Apache 2.0, raw speed (0.777s/457pg)
        ("pdfplumber",  PDFPlumberIngester),   # Zero-dep fallback
    ],
    "url": [
        ("trafilatura", TrafilaturaIngester),  # Best web content extraction
        ("scrapling",   ScraplingIngester),    # skill: scrapling-fetch (anti-bot)
        ("mineru_html", MinerUHTMLIngester),   # MinerU HTML mode
    ],
    "office": [
        ("markitdown",  MarkItDownIngester),   # MIT, Office→MD (skill: officecli)
        ("python_pptx", PPTXIngester),         # skill: powerpoint
    ],
    "image": [
        ("mineru_ocr",  MinerUOCRIngester),    # MinerU OCR mode
        ("paddleocr",   PaddleOCRIngester),    # Chinese OCR
        ("vision_vlm",  VisionVLMIngester),    # skill: vision-extractor-single-pass
    ],
    "text": [
        ("passthrough", TextIngester),         # Direct pass-through
    ],
}
```

## Routing Strategy

```
PDF Input
  │
  ├─ Language detection
  │   ├─ zh → PaddleOCR / pdfmux / MinerU
  │   └─ en → Docling / Marker / LiteParse
  │
  ├─ Content type detection (first 3 pages)
  │   ├─ Tables/Formulas → Docling / pdfmux
  │   ├─ Scanned image → Marker OCR / MinerU OCR / PaddleOCR
  │   └─ Text-heavy → LiteParse / pdfplumber
  │
  └─ Smart default → pdfmux (auto-routing per page)
```

## Skill Integration

MediaForge ingest 不重复造轮子——直接调用现有 Hermes skills：

| Input | Skill / MCP | 工具 |
|-------|------------|------|
| PDF | `pdf-parsing` | 8 工具决策树 |
| URL | `scrapling-fetch` | 反爬虫提取 |
| URL | `smart-web-search` | Exa/AnySearch→Jina |
| Office | `officecli` | .docx/.pptx/.xlsx→MD |
| Office | `markdown-to-pdf` | 反向转换 |
| Office | `powerpoint` | .pptx 内容提取 |
| Image/Scan | `vision-extractor-single-pass` | VLM 结构化提取 |
| Image/Scan | `ocr-and-documents` | LiteParse/pymupdf/marker |
| Multi-format | MinerU MCP | PDF/DOCX/PPTX/XLSX/图片 |

## Contract

### `ingest(sources: list[Source]) -> str`

- **Input**: Source 列表，每个包含 type 和 content
- **Output**: Markdown 格式的拼接内容
- **Backend 选择**: registry 优先级 + 内容类型检测
- **Fallback**: 每个 backend 失败后自动尝试下一个

### Backend Interface

```python
class IngesterBackend(ABC):
    """Base interface for all ingest backends."""
    
    @abstractmethod
    def ingest(self, source: Source) -> str:
        """Extract content. Raise IngestBackendError to trigger fallback."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Backend identifier matching registry key."""
```

### IngestResult

```python
@dataclass
class IngestResult:
    content: str                    # Markdown content
    backend_used: str               # Which backend succeeded
    confidence: float = 1.0         # 0.0-1.0 (pdfmux provides this)
    warnings: list[str] = []        # Non-fatal issues
    metadata: dict = {}             # Page count, language, etc.
```

## Boundary Cases

- 所有 backend 失败 → 抛 `IngestError`，列出每个 backend 的错误
- 图片型 PDF → OCR backend 自动激活
- 混合源 → 按顺序拼接，`---` 分隔
- 超大 PDF (>100MB) → 拒绝，不尝试
- 空输入 → 空字符串，不抛异常
- MinerU MCP 不可用 → 降级到本地 backend
