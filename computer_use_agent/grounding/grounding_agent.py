import base64
import re
import time
from collections import defaultdict
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import httpx
import pytesseract
from PIL import Image
from pytesseract import Output

from computer_use_agent.coder.code_agent import CodeAgent
from computer_use_agent.core.mllm import LMMAgent
from computer_use_agent.memory.procedural_memory import PROCEDURAL_MEMORY
from computer_use_agent.utils.common_utils import call_llm_safe, compress_image
from shared.latency_logger import LATENCY_LOGGER
from shared.streaming import emit_event
from shared.text_utils import safe_ascii
from shared.hierarchical_logger import (
    get_hierarchical_logger,
    get_step_id,
)
import logging

logger = logging.getLogger("desktopenv.agent")

_TEXT_SPAN_PROMPT_PATH = Path(__file__).with_name("text_span_prompt.txt")

_FLOAT_PATTERN = r"-?\d+(?:\.\d+)?"
_CLICK_POINT_RE = re.compile(
    rf"click\s*\(\s*(?:x\s*=\s*)?(?P<x>{_FLOAT_PATTERN})\s*,\s*(?:y\s*=\s*)?(?P<y>{_FLOAT_PATTERN})\s*\)",
    re.IGNORECASE,
)
_BRACKET_POINT_RE = re.compile(
    rf"[\[\(]\s*(?P<x>{_FLOAT_PATTERN})\s*,\s*(?P<y>{_FLOAT_PATTERN})\s*[\]\)]",
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(_FLOAT_PATTERN)


def _parse_xy_from_text(text: str) -> Optional[Tuple[float, float]]:
    if not text:
        return None
    for pattern in (_CLICK_POINT_RE, _BRACKET_POINT_RE):
        match = pattern.search(text)
        if match:
            try:
                return float(match.group("x")), float(match.group("y"))
            except Exception:
                return None
    numbers = _NUMBER_RE.findall(text)
    if len(numbers) >= 2:
        try:
            return float(numbers[0]), float(numbers[1])
        except Exception:
            return None
    return None


def _decode_screenshot_data(screenshot_data: object) -> bytes:
    if isinstance(screenshot_data, str):
        data = screenshot_data.strip()
        if data.startswith("data:"):
            data = data.split("base64,", 1)[-1]
        return base64.b64decode(data)
    if isinstance(screenshot_data, bytes):
        return screenshot_data
    raise ValueError(f"Unsupported screenshot type: {type(screenshot_data)}")


def _get_image_size(image_bytes: bytes) -> Tuple[int, int]:
    with Image.open(BytesIO(image_bytes)) as img:
        return img.size


def _is_probable_norm_1000(x: float, y: float, img_w: int, img_h: int) -> bool:
    if not (0.0 <= x <= 1000.0 and 0.0 <= y <= 1000.0):
        return False
    if not float(x).is_integer() or not float(y).is_integer():
        return True
    return img_w <= 1100 and img_h <= 1100


def _normalize_point_to_dims(
    x: float,
    y: float,
    *,
    img_w: int,
    img_h: int,
    target_w: int,
    target_h: int,
    allow_norm_1000: Optional[bool],
) -> List[int]:
    target_w = max(int(target_w), 1)
    target_h = max(int(target_h), 1)
    if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0:
        scaled_x = x * target_w
        scaled_y = y * target_h
    else:
        use_norm_1000 = False
        if allow_norm_1000 is True:
            use_norm_1000 = 0.0 <= x <= 1000.0 and 0.0 <= y <= 1000.0
        elif allow_norm_1000 is None:
            use_norm_1000 = _is_probable_norm_1000(x, y, img_w, img_h)
            if not use_norm_1000 and 0.0 <= x <= 1000.0 and 0.0 <= y <= 1000.0:
                if img_w > 1000 and img_h > 1000:
                    logger.debug(
                        "Ambiguous grounding coords scale (0..1000 with large image); assuming pixel-space."
                    )
        if use_norm_1000:
            scaled_x = (x / 1000.0) * target_w
            scaled_y = (y / 1000.0) * target_h
        else:
            img_w = max(int(img_w), 1)
            img_h = max(int(img_h), 1)
            scaled_x = (x / img_w) * target_w
            scaled_y = (y / img_h) * target_h
    scaled_x = max(0.0, min(float(target_w - 1), round(scaled_x)))
    scaled_y = max(0.0, min(float(target_h - 1), round(scaled_y)))
    return [int(scaled_x), int(scaled_y)]


def _load_text_span_prompt() -> str:
    if not _TEXT_SPAN_PROMPT_PATH.exists():
        raise FileNotFoundError(
            f"Text span prompt file not found at {_TEXT_SPAN_PROMPT_PATH}"
        )
    return _TEXT_SPAN_PROMPT_PATH.read_text(encoding="utf-8").strip()


class ACI:
    def __init__(self):
        self.knowledge: List[str] = []


# Agent action decorator
def agent_action(func):
    func.is_agent_action = True
    return func


UBUNTU_APP_SETUP = f"""import subprocess;
import difflib;
import pyautogui;
import time;
pyautogui.press('escape');
time.sleep(0.5);
output = subprocess.check_output(['wmctrl', '-lx']);
output = output.decode('utf-8').splitlines();
window_titles = [line.split(None, 4)[2] for line in output];
closest_matches = difflib.get_close_matches('APP_NAME', window_titles, n=1, cutoff=0.1);
if closest_matches:
    closest_match = closest_matches[0];
    for line in output:
        if closest_match in line:
            window_id = line.split()[0]
            break;
subprocess.run(['wmctrl', '-ia', window_id])
subprocess.run(['wmctrl', '-ir', window_id, '-b', 'add,maximized_vert,maximized_horz'])
"""


SET_CELL_VALUES_CMD = """import uno
import subprocess
import unicodedata, json

def identify_document_type(component):
    if component.supportsService("com.sun.star.sheet.SpreadsheetDocument"):
        return "Calc"

    if component.supportsService("com.sun.star.text.TextDocument"):
        return "Writer"

    if component.supportsService("com.sun.star.sheet.PresentationDocument"):
        return "Impress"

    return None

def _norm_name(s: str | None) -> str | None:
    if s is None:
        return None
    if "\\\\u" in s or "\\\\U" in s or "\\\\x" in s:
        try:
            # json.loads handles all the escape forms safely
            s = json.loads(f"{{s}}")
        except Exception:
            # fallback: best-effort
            try:
                s = s.encode("utf-8").decode("unicode_escape")
            except Exception:
                pass
    # Normalize (NFC works well across platforms)
    return unicodedata.normalize("NFC", s)

def cell_ref_to_indices(cell_ref):
    column_letters = ''.join(filter(str.isalpha, cell_ref))
    row_number = ''.join(filter(str.isdigit, cell_ref))

    col = sum((ord(char.upper()) - ord('A') + 1) * (26**idx) for idx, char in enumerate(reversed(column_letters))) - 1
    row = int(row_number) - 1
    return col, row

def set_cell_values(new_cell_values: dict[str, str], app_name: str = "Untitled 1", sheet_name: str = "Sheet1"):
    app_name  = _norm_name(app_name)
    sheet_name = _norm_name(sheet_name)

    new_cell_values_idx = {{}}
    for k, v in new_cell_values.items():
        try:
            col, row = cell_ref_to_indices(k)
        except:
            col = row = None

        if col is not None and row is not None:
            new_cell_values_idx[(col, row)] = v

    # Clean up previous TCP connections.
    subprocess.run(
        'echo \"osworld-public-evaluation\" | sudo -S ss --kill --tcp state TIME-WAIT sport = :2002',
        shell=True,
        check=True,
        text=True,
        capture_output=True
    )

    # Dynamically allow soffice to listen on port 2002.
    subprocess.run(
        [
            "soffice",
            "--accept=socket,host=localhost,port=2002;urp;StarOffice.Service"
        ]
    )

    local_context = uno.getComponentContext()
    resolver = local_context.ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver", local_context
    )
    context = resolver.resolve(
        f"uno:socket,host=localhost,port=2002;urp;StarOffice.ComponentContext"
    )
    desktop = context.ServiceManager.createInstanceWithContext(
        "com.sun.star.frame.Desktop", context
    )

    # Collect all LibreOffice-related opened windows.
    documents = []
    for i, component in enumerate(desktop.Components):
        title = component.Title
        doc_type = identify_document_type(component)
        documents.append((i, component, title, doc_type))

    # Find the LibreOffice Calc app and the sheet of interest.
    spreadsheet = [doc for doc in documents if doc[3] == "Calc"]
    selected_spreadsheet = [doc for doc in spreadsheet if doc[2] == app_name]
    if spreadsheet:
        try:
            if selected_spreadsheet:
                spreadsheet = selected_spreadsheet[0][1]
            else:
                spreadsheet = spreadsheet[0][1]

            sheet = spreadsheet.Sheets.getByName(sheet_name)
        except:
            raise ValueError(f"Could not find sheet {{sheet_name}} in {{app_name}}.")

        for (col, row), value in new_cell_values_idx.items():
            cell = sheet.getCellByPosition(col, row)

            # Set the cell value.
            if isinstance(value, (int, float)):
                cell.Value = value
            elif isinstance(value, str):
                if value.startswith("="):
                    cell.Formula = value
                else:
                    cell.String = value
            elif isinstance(value, bool):
                cell.Value = 1 if value else 0
            elif value is None:
                cell.clearContents(0)
            else:
                raise ValueError(f"Unsupported cell value type: {{type(value)}}")

    else:
        raise ValueError(f"Could not find LibreOffice Calc app corresponding to {{app_name}}.")

set_cell_values(new_cell_values={cell_values}, app_name="{app_name}", sheet_name="{sheet_name}")        
"""


# ACI primitives are parameterized by description, and coordinate generation uses a pretrained grounding model
class OSWorldACI(ACI):
    def __init__(
        self,
        env,
        platform: str,
        engine_params_for_generation: Dict,
        engine_params_for_grounding: Dict,
        width: int = 1920,
        height: int = 1080,
        code_agent_budget: int = 20,
        code_agent_engine_params: Dict = None,
        grounding_base_url: Optional[str] = None,
        grounding_system_prompt: Optional[str] = None,
        grounding_timeout: float = 10.0,
        grounding_max_retries: int = 3,
        grounding_api_key: Optional[str] = None,
        grounding_inference_fn: Optional[
            Callable[[bytes, str], Tuple[float, float]]
        ] = None,
    ):
        super().__init__()

        self.env = env
        self.platform = (
            platform  # Dictates how the switch_applications agent action works.
        )

        # Configure scaling
        self.width = width
        self.height = height

        # Maintain state for save_to_knowledge
        self.knowledge = []

        # Screenshot used during ACI execution
        self.obs = None

        # Configure the visual grounding model responsible for coordinate generation
        engine_params_for_grounding = dict(engine_params_for_grounding)
        engine_params_for_grounding.setdefault("engine_type", "openai")
        engine_params_for_grounding.setdefault("model", "o4-mini")
        engine_params_for_grounding.setdefault("grounding_width", self.width)
        engine_params_for_grounding.setdefault("grounding_height", self.height)
        self.grounding_model = LMMAgent(engine_params_for_grounding)
        self.engine_params_for_grounding = engine_params_for_grounding

        # Configure text grounding agent
        engine_params_for_generation = dict(engine_params_for_generation)
        engine_params_for_generation.setdefault("engine_type", "openai")
        engine_params_for_generation.setdefault("model", "o4-mini")
        self.text_span_agent = LMMAgent(
            engine_params=engine_params_for_generation,
            system_prompt=_load_text_span_prompt(),
        )

        # Configure code agent
        code_agent_engine_params = (
            code_agent_engine_params or engine_params_for_generation
        )
        code_agent_engine_params = dict(code_agent_engine_params)
        code_agent_engine_params.setdefault("engine_type", "openai")
        code_agent_engine_params.setdefault("model", "o4-mini")
        self.code_agent = CodeAgent(code_agent_engine_params, code_agent_budget)

        # Store full task context (for composing code subtasks)
        self.current_task_context = None
        self.last_code_agent_result = None
        # Store handback inference result for continuation after human intervention
        self.handback_inference = None
        self.grounding_base_url = grounding_base_url
        self.grounding_system_prompt = grounding_system_prompt
        self.grounding_timeout = grounding_timeout
        self.grounding_max_retries = grounding_max_retries
        self.grounding_api_key = grounding_api_key
        self.grounding_inference_fn = grounding_inference_fn
        self._logged_grounding_absence = False
        if self.grounding_base_url:
            logger.info("Grounding service configured: %s", self.grounding_base_url)
        else:
            logger.warning(
                "No grounding_base_url configured; falling back to LLM-based coordinates."
            )

    # Given the state and worker's referring expression, use the grounding model to generate (x,y)
    def generate_coords(self, ref_expr: str, obs: Dict) -> List[int]:
        screenshot_data = obs.get("screenshot")
        if screenshot_data is None:
            raise ValueError("Observation missing 'screenshot' for grounding call")

        # Get hierarchical logger if available
        h_logger = get_hierarchical_logger()
        step_id = get_step_id() or "cu-main"
        grounding_logger = None
        if h_logger:
            cu_logger = h_logger.get_agent_logger("computer_use", step_id)
            grounding_logger = cu_logger.get_sub_logger("grounding")
            grounding_logger.log_event("generate_coords.started", {
                "ref_expr": ref_expr,
            })

        emit_event(
            "grounding.generate_coords.started",
            {
                "ref_expr": ref_expr,
            },
        )

        try:
            image_bytes = _decode_screenshot_data(screenshot_data)
        except Exception as exc:
            raise ValueError(
                "Failed to decode screenshot for grounding inference"
            ) from exc

        source = "fallback"
        coords: Optional[List[int]] = None
        grounding_width = max(
            int(self.engine_params_for_grounding.get("grounding_width") or self.width),
            1,
        )
        grounding_height = max(
            int(self.engine_params_for_grounding.get("grounding_height") or self.height),
            1,
        )

        if self.grounding_inference_fn is not None:
            x_norm, y_norm = self.grounding_inference_fn(image_bytes, ref_expr)
            x = min(max(0, round(x_norm * grounding_width)), grounding_width - 1)
            y = min(max(0, round(y_norm * grounding_height)), grounding_height - 1)
            coords = [x, y]
            source = "custom_inference"
        else:
            if self.grounding_base_url:
                coords = self._grounding_service_coords(image_bytes, ref_expr)
                if coords:
                    source = "service"
                else:
                    logger.warning(
                        "Grounding service call failed; falling back to model inference for coordinates."
                    )
                    emit_event(
                        "grounding.generate_coords.service_fallback",
                        {"ref_expr": ref_expr},
                    )
            if coords is None:
                # Reset the grounding model state
                self.grounding_model.reset()

                # Configure the context, UI-TARS demo does not use system prompt
                prompt = (
                    "You are a GUI grounding model.\n"
                    "Given the screenshot, find the best single click point for the target.\n"
                    "Return only: click(x, y)\n"
                    "x and y must be integers in [0,1000] representing thousandths of the image.\n"
                    f"Target: {ref_expr}"
                )
                self.grounding_model.add_message(
                    text_content=prompt, image_content=image_bytes, put_text_last=True
                )

                # Generate and parse coordinates
                response = call_llm_safe(
                    self.grounding_model,
                    cost_source="grounding.fallback_coords",
                )
                print("RAW GROUNDING MODEL RESPONSE:", response)
                point = _parse_xy_from_text(response)
                if not point:
                    raise RuntimeError(f"Failed to parse grounding coordinates from: {response}")
                try:
                    img_w, img_h = _get_image_size(image_bytes)
                except Exception as exc:
                    logger.warning("Failed to read screenshot size for fallback grounding: %s", exc)
                    img_w, img_h = grounding_width, grounding_height
                coords = _normalize_point_to_dims(
                    point[0],
                    point[1],
                    img_w=img_w,
                    img_h=img_h,
                    target_w=grounding_width,
                    target_h=grounding_height,
                    allow_norm_1000=True,
                )
                source = "llm"

        if coords is None:
            raise RuntimeError("Failed to generate grounding coordinates")

        # Log completion to hierarchical logger
        if grounding_logger:
            grounding_logger.log_event("generate_coords.completed", {
                "ref_expr": ref_expr,
                "coords": coords,
                "source": source,
            })

        emit_event(
            "grounding.generate_coords.completed",
            {
                "ref_expr": ref_expr,
                "coords": coords,
                "source": source,
            },
        )
        return coords

    def _grounding_service_coords(
        self, image_bytes: bytes, prompt: str
    ) -> Optional[List[int]]:
        if not self.grounding_base_url:
            if not self._logged_grounding_absence:
                logger.warning(
                    "grounding_base_url not set; skipping external grounding service."
                )
                self._logged_grounding_absence = True
            return None

        try:
            with Image.open(BytesIO(image_bytes)) as img:
                width, height = img.size
        except Exception as exc:
            logger.error("Failed to read screenshot for grounding service: %s", exc)
            logger.warning("Falling back to LLM grounding due to image read failure.")
            return None

        return self._invoke_grounding_service(image_bytes, prompt, width, height)

    def _invoke_grounding_service(
        self, image_bytes: bytes, prompt: str, width: int, height: int
    ) -> Optional[List[int]]:
        with LATENCY_LOGGER.measure("grounding", "compress_image"):
            compressed_image = compress_image(image_bytes=image_bytes)
        image_base64 = base64.b64encode(compressed_image).decode("utf-8")

        messages: List[Dict[str, Any]] = []
        if self.grounding_system_prompt:
            messages.append(
                {
                    "role": "system",
                    "content": [{"type": "text", "text": self.grounding_system_prompt}],
                }
            )
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "image": f"data:image/webp;base64,{image_base64}",
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        )

        payload = {
            "messages": messages,
            "max_new_tokens": 300,
            "temperature": 0.0,
            "top_p": 0.9,
        }

        url = f"{self.grounding_base_url.rstrip('/')}/call_llm"

        headers = {}
        if self.grounding_api_key:
            headers["Authorization"] = f"Bearer {self.grounding_api_key}"

        for attempt in range(self.grounding_max_retries):
            try:
                emit_event(
                    "grounding.generate_coords.service_attempt",
                    {
                        "attempt": attempt + 1,
                        "prompt": prompt,
                    },
                )
                with LATENCY_LOGGER.measure(
                    "grounding", "runpod_call", extra={"attempt": attempt + 1}
                ):
                    with httpx.Client(timeout=self.grounding_timeout) as client:
                        response = client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                result_items = [data] if isinstance(data, dict) else data
                if not result_items:
                    raise ValueError("Empty grounding response")
                text = (
                    result_items[0].get("response")
                    or result_items[0].get("text")
                    or ""
                )
                coords = _parse_xy_from_text(text)
                if not coords:
                    raise ValueError(f"No coordinates found in response: {text}")
                grounding_width = self.engine_params_for_grounding.get("grounding_width") or self.width
                grounding_height = self.engine_params_for_grounding.get("grounding_height") or self.height
                coords_payload = _normalize_point_to_dims(
                    coords[0],
                    coords[1],
                    img_w=width,
                    img_h=height,
                    target_w=grounding_width,
                    target_h=grounding_height,
                    allow_norm_1000=None,
                )
                emit_event(
                    "grounding.generate_coords.service_success",
                    {
                        "attempt": attempt + 1,
                        "coords": coords_payload,
                    },
                )
                return coords_payload
            except Exception as exc:
                logger.warning(
                    "Grounding service attempt %d failed: %s", attempt + 1, exc
                )
                emit_event(
                    "grounding.generate_coords.service_retry",
                    {
                        "attempt": attempt + 1,
                        "error": str(exc),
                    },
                )
                time.sleep(1.0)
        logger.error(
            "All grounding service attempts failed after %d retries; using fallback coordinates.",
            self.grounding_max_retries,
        )
        emit_event(
            "grounding.generate_coords.service_failed",
            {
                "attempts": self.grounding_max_retries,
                "prompt": prompt,
            },
        )
        return None

    # Calls pytesseract to generate word level bounding boxes for text grounding
    def get_ocr_elements(self, screenshot_data: Union[str, bytes]) -> Tuple[str, List]:
        image_bytes = _decode_screenshot_data(screenshot_data)
        image = Image.open(BytesIO(image_bytes))
        image_data = pytesseract.image_to_data(image, output_type=Output.DICT)

        # Clean text by removing leading and trailing spaces and non-alphabetical characters, but keeping punctuation
        for i, word in enumerate(image_data["text"]):
            image_data["text"][i] = re.sub(
                r"^[^a-zA-Z\s.,!?;:\-\+]+|[^a-zA-Z\s.,!?;:\-\+]+$", "", word
            )

        ocr_elements = []
        ocr_table = "Text Table:\nWord id\tText\n"
        # Obtain the <id, text, group number, word number> for each valid element
        grouping_map = defaultdict(list)
        ocr_id = 0
        for i in range(len(image_data["text"])):
            block_num = image_data["block_num"][i]
            if image_data["text"][i]:
                grouping_map[block_num].append(image_data["text"][i])
                ocr_table += f"{ocr_id}\t{image_data['text'][i]}\n"
                ocr_elements.append(
                    {
                        "id": ocr_id,
                        "text": image_data["text"][i],
                        "group_num": block_num,
                        "word_num": len(grouping_map[block_num]),
                        "left": image_data["left"][i],
                        "top": image_data["top"][i],
                        "width": image_data["width"][i],
                        "height": image_data["height"][i],
                    }
                )
                ocr_id += 1

        return ocr_table, ocr_elements

    # Given the state and worker's text phrase, generate the coords of the first/last word in the phrase
    def generate_text_coords(
        self, phrase: str, obs: Dict, alignment: str = ""
    ) -> List[int]:

        emit_event(
            "grounding.generate_text_coords.started",
            {
                "phrase": phrase,
                "alignment": alignment or "center",
            },
        )

        ocr_table, ocr_elements = self.get_ocr_elements(obs["screenshot"])

        alignment_prompt = ""
        if alignment == "start":
            alignment_prompt = "**Important**: Output the word id of the FIRST word in the provided phrase.\n"
        elif alignment == "end":
            alignment_prompt = "**Important**: Output the word id of the LAST word in the provided phrase.\n"

        # Load LLM prompt
        self.text_span_agent.reset()
        self.text_span_agent.add_message(
            alignment_prompt + "Phrase: " + phrase + "\n" + ocr_table, role="user"
        )
        self.text_span_agent.add_message(
            "Screenshot:\n", image_content=obs["screenshot"], role="user"
        )

        # Obtain the target element
        response = call_llm_safe(
            self.text_span_agent,
            cost_source="grounding.text_span",
        )
        print("TEXT SPAN AGENT RESPONSE:", response)
        numericals = re.findall(r"\d+", response)
        if len(numericals) > 0:
            text_id = int(numericals[-1])
        else:
            text_id = 0
        elem = ocr_elements[text_id]

        # Compute the element coordinates
        if alignment == "start":
            coords = [elem["left"], elem["top"] + (elem["height"] // 2)]
        elif alignment == "end":
            coords = [elem["left"] + elem["width"], elem["top"] + (elem["height"] // 2)]
        else:
            coords = [
                elem["left"] + (elem["width"] // 2),
                elem["top"] + (elem["height"] // 2),
            ]
        emit_event(
            "grounding.generate_text_coords.completed",
            {
                "phrase": phrase,
                "alignment": alignment or "center",
                "coords": coords,
            },
        )
        return coords

    def assign_screenshot(self, obs: Dict):
        self.obs = obs

    def set_task_context(self, task_context: str):
        """Set the high-level task context used to compose code subtasks.

        This context is *not* executed by the code agent. Any call to
        `call_code_agent` must pass an explicit, code-executable subtask string.
        """
        self.current_task_context = task_context

    # Resize from grounding model dim into OSWorld dim (default 1920 * 1080)
    def resize_coordinates(self, coordinates: List[int]) -> List[int]:
        grounding_width = self.engine_params_for_grounding.get("grounding_width") or self.width
        grounding_height = self.engine_params_for_grounding.get("grounding_height") or self.height

        return [
            round(coordinates[0] * self.width / grounding_width),
            round(coordinates[1] * self.height / grounding_height),
        ]

    @agent_action
    def click(
        self,
        element_description: str,
        num_clicks: int = 1,
        button_type: str = "left",
        hold_keys: List = [],
    ):
        """Click on the element
        Args:
            element_description:str, an extremely detailed descriptions of which element to click on. This description should be at least a full sentence. The description should be so detailed that it can be used to uniquely identify the element.
            num_clicks:int, number of times to click the element
            button_type:str, which mouse button to press can be "left", "middle", or "right"
            hold_keys:List, list of keys to hold while clicking
        """
        coords1 = self.generate_coords(element_description, self.obs)
        x, y = self.resize_coordinates(coords1)
        command = "import pyautogui; "

        # Move cursor to target before clicking for stability
        command += f"pyautogui.moveTo({x}, {y}, duration=0.15); "

        # Hold modifier keys (if any), then click, then release
        for k in hold_keys:
            command += f"pyautogui.keyDown({repr(k)}); "
        command += f"pyautogui.click({x}, {y}, clicks={num_clicks}, button={repr(button_type)}); "
        for k in hold_keys:
            command += f"pyautogui.keyUp({repr(k)}); "
        # Return pyautoguicode to click on the element
        return command

    @agent_action
    def switch_applications(self, app_code):
        """Switch to a different application that is already open
        Args:
            app_code:str the code name of the application to switch to from the provided list of open applications
        """
        if self.platform == "darwin":
            return f"import pyautogui; import time; pyautogui.hotkey('command', 'space', interval=0.5); pyautogui.typewrite({repr(app_code)}); pyautogui.press('enter'); time.sleep(1.0)"
        elif self.platform == "linux":
            return UBUNTU_APP_SETUP.replace("APP_NAME", app_code)
        elif self.platform == "windows":
            return f"import pyautogui; import time; pyautogui.hotkey('win', 'd', interval=0.5); pyautogui.typewrite({repr(app_code)}); pyautogui.press('enter'); time.sleep(1.0)"
        else:
            assert (
                False
            ), f"Unsupported platform: {self.platform}. Supported platforms are: darwin, linux, windows."

    @agent_action
    def open(self, app_or_filename: str):
        """Open any application or file with name app_or_filename. Use this action to open applications or files on the desktop, do not open manually.
        Args:
            app_or_filename:str, the name of the application or filename to open
        """
        # Normalize the target so that:
        # - If a full file path is provided, reduce to just the filename
        # - If a directory path is provided (ends with slash and has multiple separators), keep as-is
        # - If an application name is provided (no path separators), keep as-is
        normalized_target, category = self._normalize_open_target(app_or_filename)
        if category == "file" and normalized_target != app_or_filename:
            logger.info(
                "Normalized open target from full file path to filename: %r -> %r",
                app_or_filename,
                normalized_target,
            )
        app_or_filename = normalized_target
        if self.platform == "linux":
            return f"import pyautogui; import time; pyautogui.hotkey('win'); time.sleep(0.5); pyautogui.write({repr(app_or_filename)}); time.sleep(0.5); pyautogui.hotkey('enter'); time.sleep(1.0)"
        elif self.platform == "darwin":
            return f"import pyautogui; import time; pyautogui.hotkey('command', 'space', interval=0.5); pyautogui.typewrite({repr(app_or_filename)}); pyautogui.press('enter'); time.sleep(1.0)"
        elif self.platform == "windows":
            return (
                "import pyautogui; import time; "
                "pyautogui.hotkey('win'); time.sleep(0.5); "
                f"pyautogui.write({repr(app_or_filename)}); time.sleep(1.0); "
                "pyautogui.press('enter'); time.sleep(0.5)"
            )
        else:
            assert (
                False
            ), f"Unsupported platform: {self.platform}. Supported platforms are: darwin, linux, windows."

    def _normalize_open_target(self, raw: str) -> Tuple[str, str]:
        """Normalize an open() target across app names, file paths, and directories.

        Returns a tuple of (normalized_value, category) where category is one of:
        - "file": a filename only (path stripped if full path was given)
        - "directory": a directory path (kept as-is)
        - "app": an application name (no path separators, kept as-is)

        Heuristic (aligned with spec):
        - If the string ends with a path separator ('/' or '\\') AND contains more than one
          path separator overall, treat as directory -> keep full path.
        - Else, if it contains any path separator, treat as file path -> reduce to basename.
        - Else, treat as application name -> keep as-is.
        """
        if raw is None:
            return "", "app"
        s = str(raw).strip()
        if not s:
            return s, "app"

        sep_count = s.count("/") + s.count("\\")
        is_dir = (s.endswith("/") or s.endswith("\\")) and sep_count > 1
        if is_dir:
            return s, "directory"

        if sep_count >= 1:
            # Reduce to filename for file paths; handle both separators
            filename = s.replace("\\", "/").split("/")[-1]
            return filename, "file"

        return s, "app"

    @agent_action
    def type(
        self,
        element_description: Optional[str] = None,
        text: str = "",
        overwrite: bool = False,
        enter: bool = False,
    ):
        """Type text/unicode into a specific element
        Args:
            element_description:str, an extremely detailed description of which element to enter text in. This description should be at least a full sentence. The description should be so detailed that it can be used to uniquely identify the element.
            text:str, the text to type
            overwrite:bool, Assign it to True if the text should overwrite the existing text, otherwise assign it to False. Using this argument clears all text in an element.
            enter:bool, Assign it to True if the enter key should be pressed after typing the text, otherwise assign it to False.
        """
        command = "import pyautogui; "
        command += (
            "\ntry:\n"
            "    import pyperclip\n"
            "except ImportError:\n"
            "    import subprocess\n"
            "    subprocess.run('echo \"osworld-public-evaluation\" | sudo -S apt-get install -y xclip xsel', shell=True, check=True)\n"
            "    subprocess.check_call([subprocess.sys.executable, '-m', 'pip', 'install', 'pyperclip'])\n"
            "    import pyperclip\n\n"
        )

        if element_description is not None:
            coords1 = self.generate_coords(element_description, self.obs)
            x, y = self.resize_coordinates(coords1)
            command += f"pyautogui.click({x}, {y}); "

        if overwrite:
            command += (
                f"pyautogui.hotkey({repr('command' if self.platform == 'darwin' else 'ctrl')}, 'a'); "
                "pyautogui.press('backspace'); "
            )

        # Check if text contains Unicode characters that pyautogui.write() can't handle
        has_unicode = any(ord(char) > 127 for char in text)

        if has_unicode:
            # Use clipboard method for Unicode characters
            command += f"pyperclip.copy({repr(text)}); "
            command += f"pyautogui.hotkey({repr('command' if self.platform == 'darwin' else 'ctrl')}, 'v'); "
        else:
            # Use regular pyautogui.write() for ASCII text
            command += f"pyautogui.write({repr(text)}); "

        if enter:
            command += "pyautogui.press('enter'); "
        return command

    @agent_action
    def save_to_knowledge(self, text: List[str]):
        """Save facts, elements, texts, etc. to a long-term knowledge bank for reuse during this task. Can be used for copy-pasting text, saving elements, etc.
        Args:
            text:List[str] the text to save to the knowledge
        """
        self.knowledge.extend(text)
        return """WAIT"""

    @agent_action
    def drag_and_drop(
        self, starting_description: str, ending_description: str, hold_keys: List = []
    ):
        """Drag from the starting description to the ending description
        Args:
            starting_description:str, an extremely detailed description of where to start the drag action. This description should be at least a full sentence. The description should be so detailed that it can be used to uniquely identify the element.
            ending_description:str, an extremely detailed description of where to end the drag action. This description should be at least a full sentence. The description should be so detailed that it can be used to uniquely identify the element.
            hold_keys:List list of keys to hold while dragging
        """
        coords1 = self.generate_coords(starting_description, self.obs)
        coords2 = self.generate_coords(ending_description, self.obs)
        x1, y1 = self.resize_coordinates(coords1)
        x2, y2 = self.resize_coordinates(coords2)

        command = "import pyautogui; "

        command += f"pyautogui.moveTo({x1}, {y1}); "
        # TODO: specified duration?
        for k in hold_keys:
            command += f"pyautogui.keyDown({repr(k)}); "
        command += f"pyautogui.dragTo({x2}, {y2}, duration=1., button='left'); pyautogui.mouseUp(); "
        for k in hold_keys:
            command += f"pyautogui.keyUp({repr(k)}); "

        # Return pyautoguicode to drag and drop the elements

        return command

    @agent_action
    def highlight_text_span(
        self, starting_phrase: str, ending_phrase: str, button: str = "left"
    ):
        """Highlight a text span between a provided starting phrase and ending phrase. Use this to highlight words, lines, and paragraphs.
        Args:
            starting_phrase:str, the phrase that denotes the start of the text span you want to highlight. If you only want to highlight one word, just pass in that single word.
            ending_phrase:str, the phrase that denotes the end of the text span you want to highlight. If you only want to highlight one word, just pass in that single word.
            button:str, the button to use to highlight the text span. Defaults to "left". Can be "left", "right", or "middle".
        """
        coords1 = self.generate_text_coords(
            starting_phrase, self.obs, alignment="start"
        )
        coords2 = self.generate_text_coords(ending_phrase, self.obs, alignment="end")
        x1, y1 = coords1
        x2, y2 = coords2

        command = "import pyautogui; "
        command += f"pyautogui.moveTo({x1}, {y1}); "
        command += f"pyautogui.dragTo({x2}, {y2}, duration=1., button='{button}'); pyautogui.mouseUp(); "

        # Return pyautoguicode to drag and drop the elements
        return command

    @agent_action
    def set_cell_values(
        self, cell_values: Dict[str, Any], app_name: str, sheet_name: str
    ):
        """Use this to set individual cell values in a spreadsheet. For example, setting A2 to "hello" would be done by passing {"A2": "hello"} as cell_values. The sheet must be opened before this command can be used.
        Args:
            cell_values: Dict[str, Any], A dictionary of cell values to set in the spreadsheet. The keys are the cell coordinates in the format "A1", "B2", etc.
                Supported value types include: float, int, string, bool, formulas.
            app_name: str, The name of the spreadsheet application. For example, "Some_sheet.xlsx".
            sheet_name: str, The name of the sheet in the spreadsheet. For example, "Sheet1".
        """
        return SET_CELL_VALUES_CMD.format(
            cell_values=cell_values, app_name=app_name, sheet_name=sheet_name
        )

    @agent_action
    def call_code_agent(self, subtask: str):
        """Call the code agent to run Python/Bash scripts for a specific subtask.

        Args:
            subtask: str, required. A concrete, code-executable instruction for the
                code agent to complete using Python/Bash scripts (no GUI actions).
                Include target file paths/app names, the operation to perform, and
                what outputs to print/verify.

        Notes:
            - You MUST pass a non-empty `subtask` string.
            - Do NOT delegate the entire user task; pass the next actionable
              code subtask that advances the overall goal.
            - The code agent's capability is running Python/Bash scripts via the
              controller. It does not perform GUI clicks/typing directly.
        """
        if not isinstance(subtask, str) or not subtask.strip():
            raise ValueError("call_code_agent_task_required")

        # If being evaluated for formatting only, avoid real execution
        if getattr(self, "_validation_only", False):
            logger.info("GROUNDING AGENT: Skipping code agent execution during validation")
            # Return a harmless no-op snippet to satisfy validation
            return "import time; time.sleep(0.123)"

        # Get hierarchical logger if available
        h_logger = get_hierarchical_logger()
        step_id = get_step_id() or "cu-main"
        grounding_logger = None
        if h_logger:
            cu_logger = h_logger.get_agent_logger("computer_use", step_id)
            grounding_logger = cu_logger.get_sub_logger("grounding")

        logger.info("=" * 50)
        logger.info("GROUNDING AGENT: Calling Code Agent")
        logger.info("=" * 50)

        task_to_execute = subtask.strip()
        logger.info("Executing CODE SUBTASK: %s", safe_ascii(task_to_execute))

        # Log code agent call to hierarchical logger
        if grounding_logger:
            grounding_logger.log_event("code_agent.call_started", {
                "task": task_to_execute,
                "task_context": self.current_task_context,
            })

        print("obs keys: ", self.obs.keys())
        screenshot = self.obs.get("screenshot", "") if self.obs else ""
        logger.info("Screenshot available: %s", "Yes" if screenshot else "No")

        logger.info("Executing code agent...")
        emit_event(
            "grounding.code_agent.started",
            {
                "task": task_to_execute,
                "task_context": self.current_task_context,
            },
        )
        task_context = self.current_task_context
        if task_context:
            logger.info("Higher-level task context provided to code agent.")
        else:
            logger.info("No higher-level task context provided to code agent.")
        result = self.code_agent.execute(
            task_to_execute,
            screenshot,
            self.env.controller,
            task_context=task_context,
        )

        # Store the result for the worker to access
        self.last_code_agent_result = result

        logger.info("Code agent execution completed")
        logger.info("Result - Completion reason: %s", result.get("completion_reason"))
        logger.info("Steps executed: %s", result.get("steps_executed"))
        logger.info("Summary: %s", safe_ascii(result.get("summary")))

        logger.info("=" * 50)
        logger.info("GROUNDING AGENT: Code Agent Call Finished")
        logger.info("=" * 50)

        # Log code agent completion to hierarchical logger
        if grounding_logger:
            grounding_logger.log_event(
                "code_agent.call_completed",
                {
                    "task": task_to_execute,
                    "completion_reason": result.get("completion_reason"),
                    "steps_executed": result.get("steps_executed"),
                    "summary": result.get("summary"),
                },
            )

        emit_event(
            "grounding.code_agent.completed",
            {
                "task": task_to_execute,
                "task_context": self.current_task_context,
                "completion_reason": result.get("completion_reason"),
                "steps_executed": result.get("steps_executed"),
                "summary": result.get("summary"),
            },
        )
        return "import time; time.sleep(2.222)"

    @agent_action
    def scroll(self, element_description: str, clicks: int, shift: bool = False):
        """Scroll the element in the specified direction
        Args:
            element_description:str, an extremely detailed description of which element to enter scroll in. This description should be at least a full sentence. The description should be so detailed that it can be used to uniquely identify the element.
            clicks:int, the number of clicks to scroll can be positive (up) or negative (down). Hint: Start with 150 clicks (or -150 for down). If the scroll moves too little based on what you see, progressively increase the magnitude; if it overshoots, progressively reduce the magnitude.
            shift:bool, whether to use shift+scroll for horizontal scrolling
        """
        coords1 = self.generate_coords(element_description, self.obs)
        x, y = self.resize_coordinates(coords1)

        if shift:
            return f"import pyautogui; import time; pyautogui.moveTo({x}, {y}); time.sleep(0.5); pyautogui.hscroll({clicks})"
        else:
            return f"import pyautogui; import time; pyautogui.moveTo({x}, {y}); time.sleep(0.5); pyautogui.vscroll({clicks})"

    @agent_action
    def hotkey(self, keys: List):
        """Press a hotkey combination
        Args:
            keys:List the keys to press in combination in a list format (e.g. ['ctrl', 'c'])
        """
        # add quotes around the keys
        keys = [f"'{key}'" for key in keys]
        return f"import pyautogui; pyautogui.hotkey({', '.join(keys)})"

    @agent_action
    def hold_and_press(self, hold_keys: List, press_keys: List):
        """Hold a list of keys and press a list of keys
        Args:
            hold_keys:List, list of keys to hold
            press_keys:List, list of keys to press in a sequence
        """

        press_keys_str = "[" + ", ".join([f"'{key}'" for key in press_keys]) + "]"
        command = "import pyautogui; "
        for k in hold_keys:
            command += f"pyautogui.keyDown({repr(k)}); "
        command += f"pyautogui.press({press_keys_str}); "
        for k in hold_keys:
            command += f"pyautogui.keyUp({repr(k)}); "

        return command

    @agent_action
    def wait(self, time: float):
        """Wait for a specified amount of time
        Args:
            time:float the amount of time to wait in seconds
        """
        return f"""import time; time.sleep({time})"""

    @agent_action
    def done(
        self,
    ):
        """End the current task with a success. Use this when you believe the entire task has been fully completed."""
        return """DONE"""

    @agent_action
    def fail(self):
        """End the current task with a failure. Use this when you believe the entire task is impossible to complete."""
        return """FAIL"""

    @agent_action
    def handback_to_human(self, request: str):
        """Request human intervention for tasks requiring credentials, confirmation, or information the agent cannot obtain.

        Use this when you need the human to:
        - Sign into a service with credentials you don't have access to
        - Confirm a payment, deletion, or other irreversible action
        - Provide information that isn't visible on screen
        - Complete a CAPTCHA or other human verification
        - Make a decision that requires human judgment

        Args:
            request: str, A clear, specific description of what you need the human to do.
                     Be explicit about what action is needed and what the expected outcome should be.
                     Examples: "Please sign into Gmail with your credentials",
                              "Please confirm the payment amount of $50 is correct and click Confirm",
                              "Please complete the CAPTCHA verification on this page"
        """
        # Return a special sentinel value that the runner can intercept
        return f"HANDBACK_TO_HUMAN:{request}"


_OSWORLD_ACTION_NAMES: Optional[Tuple[str, ...]] = None


def list_osworld_agent_actions() -> List[str]:
    """
    Return the names of OSWorldACI methods marked as agent actions.

    Exposes the available CUA primitives (click, type, scroll, done, etc.)
    without requiring other modules to inspect the class themselves.
    """
    global _OSWORLD_ACTION_NAMES
    if _OSWORLD_ACTION_NAMES is None:
        actions: List[str] = []
        for attr_name in dir(OSWorldACI):
            attr = getattr(OSWorldACI, attr_name, None)
            if callable(attr) and getattr(attr, "is_agent_action", False):
                actions.append(attr_name)
        _OSWORLD_ACTION_NAMES = tuple(sorted(actions))
    return list(_OSWORLD_ACTION_NAMES)
