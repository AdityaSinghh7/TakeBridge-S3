from __future__ import annotations

import inspect
from typing import Callable, List, Tuple

from .io_spec import InputParamSpec, ToolInputSpec, ToolOutputSpec, IoToolSpec


def _split_docstring(doc: str) -> Tuple[str, List[str]]:
    """Return (short_description, lines_after_args_header)."""
    lines = [line.rstrip() for line in (doc or "").strip().splitlines()]
    if not lines:
        return "", []

    # Collect description lines up to (but not including) the "Args:" header.
    desc_lines: List[str] = []
    i = 0
    while i < len(lines):
        text = lines[i].strip()
        if text == "Args:":
            break
        desc_lines.append(text)
        i += 1

    # Join description and strip an optional leading "Description:" label.
    short_description = " ".join(part for part in desc_lines if part).strip()
    if short_description.lower().startswith("description:"):
        short_description = short_description[len("description:") :].strip()

    # Skip the "Args:" line if present.
    if i < len(lines) and lines[i].strip() == "Args:":
        i += 1
    arg_lines = lines[i:]
    return short_description, arg_lines


def _parse_args_block(sig: inspect.Signature, arg_lines: List[str]) -> ToolInputSpec:
    """Parse an Args: block into a ToolInputSpec based on the function signature."""
    params: List[InputParamSpec] = []
    clean = [line for line in arg_lines if line.strip()]

    for line in clean:
        stripped = line.strip()
        if not stripped or ":" not in stripped:
            continue
        left, desc = stripped.split(":", 1)
        left = left.strip()
        desc = desc.strip()

        # Handle optional "(type)" suffix, e.g. "count (int): description".
        if "(" in left and left.endswith(")"):
            name_part, type_part = left.split("(", 1)
            name = name_part.strip()
            type_hint_from_doc = type_part[:-1].strip()  # drop closing ")"
        else:
            name = left
            type_hint_from_doc = None

        param = sig.parameters.get(name)
        if param is None:
            # Unknown parameter name; skip to avoid misleading specs.
            continue

        annotation = param.annotation
        if annotation is not inspect._empty:
            # Render annotation as a simple string for prompts.
            type_hint = getattr(annotation, "__name__", str(annotation))
        else:
            type_hint = type_hint_from_doc or "unknown"

        required = param.default is inspect._empty
        default_value = None if required else param.default

        params.append(
            InputParamSpec(
                name=name,
                type=type_hint,
                required=required,
                description=desc,
                default=default_value,
            )
        )

    return ToolInputSpec(params=params)


def build_iotoolspec_from_func(
    *,
    provider: str,
    func: Callable[..., object],
) -> IoToolSpec:
    """Construct an IoToolSpec from a wrapper function's signature and docstring."""
    doc = inspect.getdoc(func) or ""
    sig = inspect.signature(func)

    short_description, arg_lines = _split_docstring(doc)
    input_spec = _parse_args_block(sig, arg_lines)

    # Wrap the underlying method-style function so callers can invoke it as
    # a plain callable (**kwargs) without worrying about the `self` parameter.
    def _wrapped(**kwargs: object) -> object:
        dummy_self = object()
        return func(dummy_self, **kwargs)

    return IoToolSpec(
        provider=provider,
        tool_name=func.__name__,
        python_name=func.__name__,
        python_signature=str(sig),
        description=short_description or doc.strip(),
        input_spec=input_spec,
        output_spec=ToolOutputSpec(),
        func=_wrapped,
    )
