"""D9 — Schema drift: tool output fails Pydantic / schema validation.

`ctx.tool_output_schema` may be a pydantic model class, a callable that raises,
or None (skip). Validation failure raises here is caught and converted to a
detection so the runner doesn't crash on a third-party schema.
"""

from __future__ import annotations

from nami_core.safety.types import Detection, DetectorContext


def detect(ctx: DetectorContext) -> Detection | None:
    schema = ctx.tool_output_schema
    if schema is None or ctx.tool_output is None:
        return None
    try:
        if hasattr(schema, "model_validate"):
            schema.model_validate(ctx.tool_output)
        elif callable(schema):
            schema(ctx.tool_output)
        else:
            return None
    except Exception as exc:  # noqa: BLE001 — schemas raise diverse types
        return Detection(
            pattern="D9",
            action="halt_branch",
            reason=f"tool output failed schema validation: {exc}",
            severity="medium",
            metadata={"error": str(exc)},
        )
    return None
