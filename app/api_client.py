from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import random
import re
import string
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple, List, cast

from .constants import DEFAULT_SILICONFLOW_MODEL

try:
    import requests
except ImportError:  # pragma: no cover - handled at runtime
    requests = None  # type: ignore


_RANDOM_CHARSET = string.ascii_letters + string.digits
_KNOWN_DATE_KEYS = (
    "date",
    "invoice_date",
    "billing_date",
    "payment_date",
    "pay_date",
    "trade_date",
    "issue_date",
    "transaction_date",
)
_DATE_PATTERN = re.compile(
    r"(?P<year>19\d{2}|20\d{2})[-/年](?P<month>1[0-2]|0?[1-9])[-/月](?P<day>3[01]|[12][0-9]|0?[1-9])"
)
_EIGHT_DIGIT_PATTERN = re.compile(r"^(?P<year>\d{4})(?P<month>\d{2})(?P<day>\d{2})$")
_KEYWORD_DATE_PATTERN = re.compile(
    r"(?P<keyword>开票日期|支付时间)[：:：\s]*(?P<year>19\d{2}|20\d{2})[年/-](?P<month>1[0-2]|0?[1-9])[月/-](?P<day>3[01]|[12][0-9]|0?[1-9])",
)
_KEYWORD_PRIORITY = {"开票日期": 0, "支付时间": 1}
_KEY_FIELDS = ("key", "name", "label", "field", "title")
_VALUE_FIELDS = ("value", "text", "content", "word", "words", "val")
_SILICONFLOW_URL = "https://api.siliconflow.cn/v1/chat/completions"
_DEFAULT_SF_MODEL = DEFAULT_SILICONFLOW_MODEL
_DEFAULT_SF_PROMPT = (
    "你是报销票据分类与结构化识别助手。请先判断图片/文档到底是“发票”还是“支付凭证”，"
    "再提取日期、类别和金额，并严格只返回以下JSON（不要包含Markdown或额外文本）：\n"
    "{\n"
    '  "document_type": "invoice" | "payment_proof",\n'
    '  "invoice_date": "YYYY-MM-DD" 或 null,\n'
    '  "payment_date": "YYYY-MM-DD" 或 null,\n'
    '  "category": "加油" | "住宿" | "过路费" | "五金" | "其他",\n'
    '  "amount": 数字或 null,\n'
    '  "type_confidence": 0到1之间的数字,\n'
    '  "type_evidence": "用于判断类型的关键文字，20字以内"\n'
    "}\n"
    "类型判断规则（非常重要）：\n"
    "1) 判为 invoice 的强特征：出现“电子发票”“数电票”“普通发票”“增值税发票”“发票号码”“发票代码”"
    "“开票日期”“购买方信息”“销售方信息”“纳税人识别号”“价税合计”“税额”等。"
    "高德/飞猪/平台的“电子发票”“行程单”“报销凭证”，只要没有支付成功/交易单号等支付流水特征，也按 invoice。\n"
    "2) 判为 payment_proof 的强特征：手机支付详情截图，出现“支付成功”“当前状态 支付成功”“付款成功”“转账成功”"
    "“支付时间”“转账时间”“支付方式”“交易单号”“转账单号”“商户单号”“收单机构”“银行卡”“零钱”"
    "“微信支付”“支付宝”“财付通”“银联商务”“扫码付款”“二维码收款”等。\n"
    "3) 如果同时出现发票和支付信息，优先看核心版式：含发票号码/开票日期/购销方/税额的是 invoice；"
    "含支付状态/交易单号/付款方式/支付时间的是 payment_proof。\n"
    "4) 不要因为发票里的“收款人/销售方银行账号/价税合计”误判为 payment_proof；"
    "也不要因为支付截图里的商户名称含“发票/服务/加油站/五金”误判为 invoice。\n"
    "5) 不要根据文件名判断类型，文件名可能是随机字母、哈希或用户后期手动改名；必须只依据画面/文档正文内容判断。\n"
    "日期与金额规则：\n"
    "6) document_type=invoice 时，invoice_date 取“开票日期”，payment_date 返回 null；amount 只能取“价税合计(小写)”或“小写总额”的人民币金额。\n"
    "7) document_type=payment_proof 时，payment_date 取“支付时间/转账时间/交易时间”，invoice_date 返回 null；amount 只能取实际支付金额，负号不影响金额本身。\n"
    "8) 日期只能取票据上出现的明确日期；未找到则返回 null，不要猜测或使用固定日期。\n"
    "9) amount 必须是元为单位的金额数字，例如 16.50；严禁把发票号码、发票代码、纳税人识别号、税号、银行账号、交易单号、订单号、流水号、手机号、日期、数量、单价、税率、税额当作 amount。\n"
    "10) 如果只看到税额/不含税金额但看不到价税合计或实际支付金额，amount 返回 null。\n"
    "11) 类别只能在以下映射中选择，如无匹配填\"其他\"：\n"
    "   - 加油：加油、加油站、汽油、柴油、燃油、成品油、油费、92#、95#、中石化、中石油、Sinopec、PetroChina、CNPC\n"
    "   - 住宿：住宿、宾馆、酒店、客房、入住、旅店、旅馆、客栈、房费、飞猪、携程、hotel、inn、motel、room\n"
    "   - 过路费：过路费、通行费、过桥费、高速、高速公路、高速费、收费站、路桥、路桥费、ETC、通行流水、toll\n"
    "   - 五金：五金、劳保、劳保用品、工具、配件、耗材、电瓶、电池、铁锹、扳手、螺丝、螺栓、螺母、钳、刀、砂轮、焊机、焊条、安全帽、手套、口罩、hardware\n"
    "请只输出JSON，不要包含解释。"
)


class RecognitionAPIError(RuntimeError):
    """Raised when calling the recognition API fails."""


def _normalize_to_date(dt: datetime) -> datetime:
    """Return a timezone-aware datetime representing only the date portion."""

    return datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc)


def _build_keyword_datetime(year: str, month: str, day: str) -> Optional[datetime]:
    try:
        return datetime(
            year=int(year),
            month=int(month),
            day=int(day),
            tzinfo=timezone.utc,
        )
    except ValueError:
        return None


def _parse_candidate_value(value: Any) -> Optional[datetime]:
    if isinstance(value, str):
        match = _KEYWORD_DATE_PATTERN.search(value)
        if match:
            built = _build_keyword_datetime(
                match.group("year"), match.group("month"), match.group("day")
            )
            if built:
                return built
        return _parse_date_string(value)
    if isinstance(value, (int, float)):
        return _parse_timestamp(value)
    if isinstance(value, Mapping):
        for item in value.values():
            parsed = _parse_candidate_value(item)
            if parsed:
                return parsed
        return None
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        for item in value:
            parsed = _parse_candidate_value(item)
            if parsed:
                return parsed
    return None


def _iter_keyword_dates(obj: Any) -> Iterable[Tuple[str, datetime]]:
    if isinstance(obj, str):
        for match in _KEYWORD_DATE_PATTERN.finditer(obj):
            built = _build_keyword_datetime(
                match.group("year"), match.group("month"), match.group("day")
            )
            if built:
                yield match.group("keyword"), built
        return
    if isinstance(obj, Mapping):
        normalized: Dict[str, Any] = {}
        for key, value in obj.items():
            normalized[str(key)] = value
        for key_field in _KEY_FIELDS:
            keyword_candidate = normalized.get(key_field)
            if isinstance(keyword_candidate, str):
                keyword = keyword_candidate.strip()
                if keyword in _KEYWORD_PRIORITY:
                    for value_field in _VALUE_FIELDS:
                        if value_field in normalized:
                            parsed = _parse_candidate_value(normalized[value_field])
                            if parsed:
                                yield keyword, parsed
                                break
        for value in normalized.values():
            yield from _iter_keyword_dates(value)
        return
    if isinstance(obj, Iterable) and not isinstance(obj, (bytes, bytearray)):
        for item in obj:
            yield from _iter_keyword_dates(item)

def _random_string(length: int = 16) -> str:
    rng = random.SystemRandom()
    return "".join(rng.choice(_RANDOM_CHARSET) for _ in range(length))


def _normalize_payload(data: Optional[Mapping[str, Any]]) -> Dict[str, str]:
    normalized: Dict[str, str] = {}
    if not data:
        return normalized
    for key, value in data.items():
        if value is None:
            continue
        normalized[str(key)] = str(value)
    return normalized


def build_signed_headers(app_id: str, app_secret: str, data: Optional[Mapping[str, Any]] = None) -> Dict[str, str]:
    """Create headers with SimpleTex-style signing."""

    if not app_id:
        raise RecognitionAPIError("缺少APP ID")
    if not app_secret:
        raise RecognitionAPIError("缺少APP Secret")

    payload = _normalize_payload(data)
    timestamp = str(int(time.time()))
    base_headers = {
        "app-id": app_id,
        "timestamp": timestamp,
        "random-str": _random_string(16),
    }
    signing_items = {**payload, **base_headers}
    sorted_items = sorted(signing_items.items(), key=lambda item: item[0])
    sign_source = "&".join(f"{key}={value}" for key, value in sorted_items)
    sign_source_with_secret = f"{sign_source}&secret={app_secret}"
    signature = hashlib.md5(sign_source_with_secret.encode("utf-8")).hexdigest()
    base_headers["sign"] = signature
    return base_headers


def build_auth_headers(
    *,
    app_id: Optional[str],
    app_secret: Optional[str],
    token: Optional[str],
    data: Optional[Mapping[str, Any]],
) -> Dict[str, str]:
    """Assemble headers using either token-based auth or request signing."""

    headers: Dict[str, str] = {}
    if token:
        headers["token"] = token
    if app_id and app_secret:
        signed = build_signed_headers(app_id, app_secret, data)
        headers.update(signed)
    if not headers:
        raise RecognitionAPIError("缺少鉴权信息，请配置UAT Token或APP ID/Secret")
    return headers


def call_recognition_api(
    *,
    endpoint: str,
    app_id: Optional[str],
    app_secret: Optional[str],
    file_path: Path,
    token: Optional[str] = None,
    data: Optional[Mapping[str, Any]] = None,
    timeout: int = 30,
    use_siliconflow: bool = False,
    siliconflow_token: Optional[str] = None,
    siliconflow_model: Optional[str] = None,
    siliconflow_prompt: Optional[str] = None,
) -> Mapping[str, Any]:
    """Send a recognition request and return the decoded JSON payload."""

    path = Path(file_path)
    if not path.is_file():
        raise RecognitionAPIError(f"文件不存在: {path}")

    if use_siliconflow:
        if requests is None:
            raise RecognitionAPIError("缺少requests依赖，请先安装requests库")
        if not siliconflow_token:
            raise RecognitionAPIError("未配置硅基流动API Token")
        return _call_siliconflow_recognition(
            file_path=path,
            token=siliconflow_token,
            model=siliconflow_model,
            prompt=siliconflow_prompt,
            extra_params=data,
            timeout=timeout,
        )

    if requests is None:
        raise RecognitionAPIError("缺少requests依赖，请先安装requests库")
    if not endpoint:
        raise RecognitionAPIError("未配置识别接口地址")

    payload = _normalize_payload(data)
    headers = build_auth_headers(
        app_id=app_id,
        app_secret=app_secret,
        token=token,
        data=payload,
    )

    try:
        with path.open("rb") as file_handle:
            files = {"file": file_handle}
            response = requests.post(
                endpoint,
                data=payload,
                files=files,
                headers=headers,
                timeout=timeout,
            )
    except requests.RequestException as exc:  # type: ignore[attr-defined]
        raise RecognitionAPIError(f"识别请求失败: {exc}") from exc

    if response.status_code != 200:
        snippet = response.text[:200]
        raise RecognitionAPIError(
            f"识别请求返回错误状态码 {response.status_code}: {snippet}"
        )

    try:
        result = response.json()
    except ValueError as exc:
        raise RecognitionAPIError("识别结果不是有效的JSON格式") from exc
    return result


def _call_siliconflow_recognition(
    *,
    file_path: Path,
    token: str,
    model: Optional[str],
    prompt: Optional[str],
    extra_params: Optional[Mapping[str, Any]],
    timeout: int,
) -> Mapping[str, Any]:
    encoded_image, mime_type = _encode_media_for_siliconflow(file_path)
    overrides: Dict[str, Any] = {}
    if extra_params:
        overrides.update({str(key): value for key, value in extra_params.items()})

    model_override = overrides.get("model")
    model_name = (model_override or model or _DEFAULT_SF_MODEL).strip()
    if not model_name:
        model_name = _DEFAULT_SF_MODEL

    user_prompt = overrides.get("user_prompt")
    if not isinstance(user_prompt, str) or not user_prompt.strip():
        user_prompt = prompt or _DEFAULT_SF_PROMPT

    system_prompt = overrides.get("system_prompt")
    if system_prompt is not None and not isinstance(system_prompt, str):
        system_prompt = None

    temperature = _coerce_float(overrides.get("temperature"))
    top_p = _coerce_float(overrides.get("top_p"))
    max_tokens = _coerce_int(overrides.get("max_tokens"))
    api_url = overrides.get("api_url")
    if not isinstance(api_url, str) or not api_url.strip():
        api_url = _SILICONFLOW_URL

    user_content: List[Dict[str, Any]] = []
    if user_prompt:
        user_content.append({"type": "text", "text": user_prompt})
    user_content.append(
        {
            "type": "image_url",
            "image_url": {"url": f"data:{mime_type};base64,{encoded_image}"},
        }
    )

    messages: List[Dict[str, Any]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_content})

    payload: Dict[str, Any] = {"model": model_name, "messages": messages}
    if temperature is not None:
        payload["temperature"] = temperature
    if top_p is not None:
        payload["top_p"] = top_p
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(  # type: ignore[attr-defined]
            api_url,
            json=payload,
            headers=headers,
            timeout=timeout,
        )
    except requests.RequestException as exc:  # type: ignore[attr-defined]
        raise RecognitionAPIError(f"硅基流动请求失败: {exc}") from exc

    if response.status_code != 200:
        error_code = None
        error_message = None
        snippet = response.text[:200]
        try:
            error_payload = response.json()
        except ValueError:
            error_payload = None
        if isinstance(error_payload, Mapping):
            error_code = error_payload.get("code")
            error_message = error_payload.get("message")
        if error_code == 20041:
            raise RecognitionAPIError(
                "所选硅基流动模型不支持图像识别，请选择支持图片输入的VLM模型"
            )
        detail = error_message or snippet
        raise RecognitionAPIError(
            f"硅基流动请求返回错误状态码 {response.status_code}: {detail}"
        )

    try:
        result = response.json()
    except ValueError as exc:
        raise RecognitionAPIError("硅基流动响应不是有效的JSON格式") from exc

    content = _extract_first_message_content(result)
    structured = _maybe_parse_json_block(content) if content else None

    parsed_result: Dict[str, Any] = dict(result)
    if structured is not None:
        parsed_result["parsed"] = structured
    if content is not None:
        parsed_result["content"] = content
    return parsed_result


def _encode_media_for_siliconflow(path: Path) -> Tuple[str, str]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        image_bytes = _render_pdf_first_page(path)
        mime_type = "image/png"
    else:
        try:
            image_bytes = path.read_bytes()
        except OSError as exc:
            raise RecognitionAPIError(f"读取文件失败: {path}") from exc
        mime_type, _ = mimetypes.guess_type(str(path))
        if not mime_type or not mime_type.startswith("image/"):
            mime_type = "image/png"
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return encoded, mime_type


def _render_pdf_first_page(path: Path) -> bytes:
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise RecognitionAPIError(
            "需要安装PyMuPDF库以将PDF转换为图片: pip install pymupdf"
        ) from exc

    try:
        document = fitz.open(path)
    except RuntimeError as exc:
        raise RecognitionAPIError(f"无法打开PDF文件: {path}") from exc

    if document.page_count == 0:
        document.close()
        raise RecognitionAPIError("PDF文件不包含任何页面")

    try:
        page = document.load_page(0)
        pix = page.get_pixmap(alpha=False)
        image_bytes = pix.tobytes("png")
    except RuntimeError as exc:
        raise RecognitionAPIError("无法渲染PDF页面为图片") from exc
    finally:
        document.close()
    return image_bytes


def _coerce_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _extract_first_message_content(payload: Mapping[str, Any]) -> Optional[str]:
    choices = payload.get("choices")
    if not isinstance(choices, Iterable) or isinstance(choices, (bytes, bytearray)):
        return None
    for choice in choices:
        if not isinstance(choice, Mapping):
            continue
        message = choice.get("message")
        if isinstance(message, Mapping):
            content = message.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, Iterable) and not isinstance(
                content, (bytes, bytearray)
            ):
                parts: List[str] = []
                for item in content:
                    if isinstance(item, Mapping):
                        text = item.get("text")
                        if isinstance(text, str) and text.strip():
                            parts.append(text)
                if parts:
                    return "\n".join(parts)
    return None


def _maybe_parse_json_block(text: Optional[str]) -> Optional[Mapping[str, Any]]:
    if text is None:
        return None
    candidate = _strip_code_fence(text.strip())
    if not candidate:
        return None
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, Mapping):
        return cast(Mapping[str, Any], parsed)
    return None


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) < 3:
        return stripped
    body = lines[1:]
    if body and body[-1].strip().startswith("```"):
        body = body[:-1]
    return "\n".join(body).strip()


def extract_date_from_payload(payload: Mapping[str, Any]) -> Optional[datetime]:
    """Attempt to locate a meaningful date value in the API response."""

    def _parse_iso_date(value: Any) -> Optional[datetime]:
        if isinstance(value, str):
            try:
                dt = datetime.strptime(value.strip(), "%Y-%m-%d")
                return _normalize_to_date(dt)
            except ValueError:
                return None
        return None

    if isinstance(payload, Mapping):
        parsed = payload.get("parsed")
        if isinstance(parsed, Mapping):
            for key in ("invoice_date", "payment_date"):
                dt = _parse_iso_date(parsed.get(key))
                if dt:
                    return dt
        for key in ("invoice_date", "payment_date"):
            dt = _parse_iso_date(payload.get(key))
            if dt:
                return dt

    if not isinstance(payload, Mapping):
        return None

    prioritized: List[Tuple[int, int, datetime]] = []
    for index, (keyword, detected) in enumerate(_iter_keyword_dates(payload)):
        priority = _KEYWORD_PRIORITY.get(keyword, len(_KEYWORD_PRIORITY))
        prioritized.append((priority, index, detected))
    if prioritized:
        prioritized.sort(key=lambda item: (item[0], item[1]))
        return prioritized[0][2]

    def _extract(obj: Any) -> Optional[datetime]:
        if obj is None:
            return None
        if isinstance(obj, str):
            return _parse_date_string(obj)
        if isinstance(obj, (int, float)):
            return _parse_timestamp(obj)
        if isinstance(obj, Mapping):
            for key in _KNOWN_DATE_KEYS:
                if key in obj:
                    found = _extract(obj[key])
                    if found:
                        return found
            for value in obj.values():
                found = _extract(value)
                if found:
                    return found
        elif isinstance(obj, Iterable) and not isinstance(obj, (bytes, bytearray)):
            for item in obj:
                found = _extract(item)
                if found:
                    return found
        return None

    for top_key in ("res", "data", "result"):
        if top_key in payload:
            extracted = _extract(payload[top_key])
            if extracted:
                return extracted

    return _extract(payload)


def _parse_timestamp(value: float) -> Optional[datetime]:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return None
    # Accept timestamps roughly between years 2000 and 2100
    if not 946684800 <= timestamp <= 4102444800:
        return None
    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    return _normalize_to_date(dt)


def _parse_date_string(value: str) -> Optional[datetime]:
    text = value.strip()
    if not text:
        return None

    match = _DATE_PATTERN.search(text)
    if match:
        return _build_keyword_datetime(
            match.group("year"), match.group("month"), match.group("day")
        )

    match = _EIGHT_DIGIT_PATTERN.match(text)
    if match:
        return _build_keyword_datetime(
            match.group("year"), match.group("month"), match.group("day")
        )

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            parsed = datetime.strptime(text, fmt)
            return _normalize_to_date(parsed)
        except ValueError:
            continue

    return None
