from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


INVOICE_HINTS: Tuple[Tuple[str, int], ...] = (
    ("电子发票", 6),
    ("数电票", 6),
    ("数电普票", 6),
    ("普通发票", 5),
    ("增值税发票", 6),
    ("发票号码", 5),
    ("发票代码", 4),
    ("开票日期", 5),
    ("购买方信息", 4),
    ("销售方信息", 4),
    ("纳税人识别号", 4),
    ("价税合计", 4),
    ("税额", 2),
)
PAYMENT_HINTS: Tuple[Tuple[str, int], ...] = (
    ("支付成功", 7),
    ("付款成功", 7),
    ("交易成功", 7),
    ("转账成功", 7),
    ("账单详情", 6),
    ("全部账单", 4),
    ("淘宝账单", 5),
    ("支付时间", 6),
    ("付款时间", 6),
    ("交易时间", 5),
    ("转账时间", 5),
    ("支付方式", 5),
    ("付款方式", 5),
    ("交易单号", 5),
    ("交易订单号", 6),
    ("商户单号", 4),
    ("商家订单号", 5),
    ("微信支付", 5),
    ("支付宝", 5),
    ("财付通", 4),
    ("银联商务", 4),
)
CATEGORY_KEYWORDS: Mapping[str, Tuple[str, ...]] = {
    "加油": (
        "加油",
        "加油站",
        "汽油",
        "柴油",
        "燃油",
        "成品油",
        "油费",
        "92#",
        "95#",
        "中石化",
        "中国石化",
        "中石油",
        "中国石油",
        "sinopec",
        "petrochina",
        "cnpc",
    ),
    "住宿": (
        "住宿",
        "宾馆",
        "酒店",
        "客房",
        "入住",
        "旅店",
        "旅馆",
        "客栈",
        "房费",
        "携程",
        "飞猪",
        "hotel",
        "inn",
        "motel",
        "room",
    ),
    "过路费": (
        "过路费",
        "通行费",
        "过桥费",
        "高速",
        "高速公路",
        "高速费",
        "收费站",
        "路桥",
        "路桥费",
        "etc",
        "通行流水",
        "toll",
    ),
    "五金": (
        "五金",
        "劳保",
        "劳保用品",
        "工具",
        "配件",
        "耗材",
        "塑料制品",
        "塑胶制品",
        "塑料件",
        "电瓶",
        "电池",
        "铁锹",
        "铁鍬",
        "扳手",
        "锤",
        "螺丝",
        "螺栓",
        "螺母",
        "钳",
        "刀",
        "砂轮",
        "焊机",
        "焊条",
        "安全帽",
        "手套",
        "口罩",
        "hardware",
    ),
}
FORCED_CATEGORY_KEYWORDS: Mapping[str, Tuple[str, ...]] = {
    "五金": ("塑料制品", "塑胶制品", "塑料件"),
}

_DATE_PATTERN = re.compile(
    r"(?P<year>19\d{2}|20\d{2})[年/-](?P<month>1[0-2]|0?[1-9])[月/-](?P<day>3[01]|[12]\d|0?[1-9])"
)
_DATE_KEYWORD_PATTERN = re.compile(
    r"(?P<keyword>开票日期|支付时间|付款时间|交易时间|转账时间)[：:：\s]*(?P<date>(?:19\d{2}|20\d{2})[年/-](?:1[0-2]|0?[1-9])[月/-](?:3[01]|[12]\d|0?[1-9]))"
)
_MONEY_NUMBER = r"-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:[.]\d{1,2})?"
_CURRENCY_AMOUNT_PATTERN = re.compile(
    rf"(?:¥|￥|RMB|CNY)\s*({_MONEY_NUMBER})",
    re.IGNORECASE,
)
_SIGNED_AMOUNT_LINE_PATTERN = re.compile(rf"(?m)^\s*[-−]\s*({_MONEY_NUMBER})\s*$")
_AMOUNT_LABEL_PATTERN = re.compile(
    rf"(?:价税合计(?:\s*[（(]?\s*小写\s*[）)]?)?|小写(?:金额|总额)?|"
    rf"合计金额|发票金额|总金额|实际支付|支付金额|转账金额|付款金额|实付金额|"
    rf"实付款|应付金额|收款金额|交易金额|订单金额|amount|total)"
    rf"[\s：:，,、（）()\[\]【】A-Za-z\u4e00-\u9fff]{{0,24}}?"
    rf"(?:¥|￥|RMB|CNY)?\s*({_MONEY_NUMBER})",
    re.IGNORECASE,
)
PAYMENT_AMOUNT_CONTEXT_KEYWORDS = (
    "账单详情",
    "全部账单",
    "淘宝账单",
    "支付宝",
    "支付成功",
    "交易成功",
    "付款成功",
    "支付时间",
    "付款时间",
    "付款方式",
    "支付方式",
    "交易订单号",
    "商家订单号",
)
MAX_REASONABLE_AMOUNT = 10_000_000.0
_PADDLE_OCR: Any = None


@dataclass
class LocalRecognition:
    payload: Dict[str, Any]
    text: str
    engine: str
    usable: bool
    reason: str


def recognize_local_document(path: Path) -> LocalRecognition:
    text = ""
    engine = ""
    if path.suffix.lower() == ".pdf":
        text = extract_pdf_text(path)
        engine = "pdf_text"
        if not text:
            text = recognize_with_paddle(path)
            engine = "paddleocr_pdf"
    else:
        text = recognize_with_paddle(path)
        engine = "paddleocr"

    if not text:
        return LocalRecognition(
            payload={},
            text="",
            engine=engine or "local",
            usable=False,
            reason="本地 OCR 未获取到文字",
        )

    parsed = parse_local_text(text)
    payload: Dict[str, Any] = {
        "parsed": parsed,
        "_local_ocr": {
            "engine": engine,
            "text": text,
            "reason": "本地规则解析",
        },
    }
    usable = bool(parsed.get("document_type") and parsed.get("amount") and (
        parsed.get("invoice_date") or parsed.get("payment_date")
    ))
    reason = "本地 OCR 已提取类型、日期和金额" if usable else "本地 OCR 结果不完整"
    return LocalRecognition(payload=payload, text=text, engine=engine, usable=usable, reason=reason)


def extract_pdf_text(path: Path) -> str:
    try:
        import fitz
    except ImportError:
        return ""
    try:
        document = fitz.open(path)
    except RuntimeError:
        return ""
    try:
        parts = []
        for page in document:
            page_text = page.get_text("text").strip()
            if page_text:
                parts.append(page_text)
    finally:
        document.close()
    return "\n".join(parts).strip()


def recognize_with_paddle(path: Path) -> str:
    try:
        image_path = _prepare_ocr_image(path)
        ocr = _get_paddle_ocr()
        try:
            result = ocr.ocr(str(image_path), cls=True)
        except TypeError:
            result = ocr.ocr(str(image_path))
        return "\n".join(_iter_paddle_text(result)).strip()
    except Exception:
        return ""
    finally:
        if path.suffix.lower() == ".pdf":
            try:
                image_path.unlink()  # type: ignore[possibly-undefined]
            except Exception:
                pass


def _get_paddle_ocr() -> Any:
    global _PADDLE_OCR
    if _PADDLE_OCR is not None:
        return _PADDLE_OCR
    from paddleocr import PaddleOCR

    try:
        _PADDLE_OCR = PaddleOCR(
            lang="ch",
            ocr_version="PP-OCRv4",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
    except TypeError:
        _PADDLE_OCR = PaddleOCR(use_angle_cls=False, lang="ch")
    return _PADDLE_OCR


def _prepare_ocr_image(path: Path) -> Path:
    if path.suffix.lower() != ".pdf":
        return path
    try:
        import fitz
    except ImportError:
        return path
    document = fitz.open(path)
    try:
        if document.page_count == 0:
            return path
        page = document.load_page(0)
        pix = page.get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False)
        temp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        temp.write(pix.tobytes("png"))
        temp.close()
        return Path(temp.name)
    finally:
        document.close()


def _iter_paddle_text(result: Any) -> Iterable[str]:
    if isinstance(result, str):
        yield result
        return
    if isinstance(result, Mapping):
        for key in ("rec_text", "text", "transcription"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                yield value.strip()
        for value in result.values():
            yield from _iter_paddle_text(value)
        return
    if isinstance(result, Iterable) and not isinstance(result, (bytes, bytearray)):
        items = list(result)
        if len(items) >= 2 and isinstance(items[1], (tuple, list)):
            maybe_text = items[1][0] if items[1] else None
            if isinstance(maybe_text, str) and maybe_text.strip():
                yield maybe_text.strip()
                return
        for item in items:
            yield from _iter_paddle_text(item)


def parse_local_text(text: str) -> Dict[str, Any]:
    document_type, confidence, evidence = infer_document_type(text)
    date_text = extract_date(text, document_type)
    amount = extract_amount(text)
    category = infer_category(text)
    return {
        "document_type": document_type,
        "invoice_date": date_text if document_type == "invoice" else None,
        "payment_date": date_text if document_type == "payment_proof" else None,
        "category": category,
        "amount": amount,
        "type_confidence": confidence,
        "type_evidence": evidence,
    }


def infer_document_type(text: str) -> Tuple[str, float, str]:
    lowered = text.lower()
    invoice_hits = _collect_hits(text, lowered, INVOICE_HINTS)
    payment_hits = _collect_hits(text, lowered, PAYMENT_HINTS)
    invoice_score = sum(weight for _, weight in invoice_hits)
    payment_score = sum(weight for _, weight in payment_hits)
    if payment_score > invoice_score:
        confidence = min(0.99, 0.55 + (payment_score - invoice_score) / 20)
        return "payment_proof", confidence, "、".join(hit for hit, _ in payment_hits[:4])
    confidence = min(0.99, 0.55 + (invoice_score - payment_score) / 20)
    evidence = "、".join(hit for hit, _ in invoice_hits[:4]) or "默认发票"
    return "invoice", confidence, evidence


def _collect_hits(
    text: str,
    lowered: str,
    hints: Tuple[Tuple[str, int], ...],
) -> List[Tuple[str, int]]:
    hits: List[Tuple[str, int]] = []
    for keyword, weight in hints:
        if keyword in text or keyword.lower() in lowered:
            hits.append((keyword, weight))
    return hits


def extract_date(text: str, document_type: str) -> Optional[str]:
    keyword_matches = list(_DATE_KEYWORD_PATTERN.finditer(text))
    if keyword_matches:
        if document_type == "invoice":
            preferred = [match for match in keyword_matches if match.group("keyword") == "开票日期"]
        else:
            preferred = [
                match
                for match in keyword_matches
                if match.group("keyword") in {"支付时间", "付款时间", "交易时间", "转账时间"}
            ]
        target = (preferred or keyword_matches)[0].group("date")
        return _normalize_date(target)
    match = _DATE_PATTERN.search(text)
    if match:
        return _normalize_date(match.group(0))
    return None


def _normalize_date(raw: str) -> Optional[str]:
    match = _DATE_PATTERN.search(raw)
    if not match:
        return None
    year = int(match.group("year"))
    month = int(match.group("month"))
    day = int(match.group("day"))
    return f"{year:04d}-{month:02d}-{day:02d}"


def infer_category(text: str) -> str:
    lowered = text.lower()
    for category, keywords in FORCED_CATEGORY_KEYWORDS.items():
        if any(keyword in text or keyword.lower() in lowered for keyword in keywords):
            return category
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in text or keyword.lower() in lowered for keyword in keywords):
            return category
    return "其他"


def extract_amount(text: str) -> Optional[float]:
    for label_match in _AMOUNT_LABEL_PATTERN.finditer(text):
        parsed = _coerce_amount(label_match.group(1))
        if parsed is not None:
            return parsed
    currency_amounts = [
        amount
        for amount in (
            _coerce_amount(match.group(1))
            for match in _CURRENCY_AMOUNT_PATTERN.finditer(text)
        )
        if amount is not None
    ]
    if currency_amounts:
        return max(currency_amounts)
    if any(keyword in text for keyword in PAYMENT_AMOUNT_CONTEXT_KEYWORDS):
        signed_amounts = [
            amount
            for amount in (
                _coerce_amount(match.group(1))
                for match in _SIGNED_AMOUNT_LINE_PATTERN.finditer(text)
            )
            if amount is not None
        ]
        if signed_amounts:
            return max(signed_amounts)
    return None


def _coerce_amount(raw: str) -> Optional[float]:
    cleaned = (
        raw.strip()
        .replace(",", "")
        .replace("￥", "")
        .replace("¥", "")
        .replace("RMB", "")
        .replace("CNY", "")
        .strip()
    )
    try:
        value = abs(float(cleaned))
    except ValueError:
        return None
    if value <= 0 or value > MAX_REASONABLE_AMOUNT:
        return None
    return value
