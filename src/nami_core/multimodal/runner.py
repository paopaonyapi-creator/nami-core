import os
import yaml
import logging
from typing import Any, Dict

# In T1, we route all inference through the gateway per RUNTIME §6
import nami_core.inference_gateway as gateway

logger = logging.getLogger("nami_core.multimodal.runner")

class MultimodalRunner:
    """DAG executor for multimodal pipelines defined in registry."""

    def __init__(self, registry_path: str = None):
        if not registry_path:
            registry_path = os.environ.get(
                "NAMI_MULTIMODAL_REGISTRY",
                os.path.join(os.path.dirname(__file__), "../../../config/multimodal_registry.yaml")
            )
        self.registry_path = os.path.abspath(registry_path)
        self.pipelines = self._load_registry()

    def _load_registry(self) -> Dict[str, Any]:
        if not os.path.exists(self.registry_path):
            logger.warning(f"Registry not found at {self.registry_path}")
            return {}
        with open(self.registry_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data.get("pipelines", {})

    async def run(self, pipeline_name: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a pipeline by its name."""
        if pipeline_name not in self.pipelines:
            raise ValueError(f"Pipeline '{pipeline_name}' not found in registry.")

        pipeline = self.pipelines[pipeline_name]
        logger.info(f"Running pipeline {pipeline_name}: {pipeline.get('description', '')}")

        state = dict(inputs)
        
        for step in pipeline.get("steps", []):
            step_name = step.get("name", "unnamed_step")
            action = step.get("action")
            
            # Extract inputs
            step_inputs = {k: state.get(k) for k in step.get("input_keys", [])}
            
            logger.debug(f"Step '{step_name}': Action={action}")

            try:
                # Dispatch action
                if action == "inference_gateway.chat":
                    system_prompt = step.get("system_prompt", "")
                    prompt = step_inputs.get("prompt", "")
                    req = gateway.InferenceRequest(
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt}
                        ]
                    )
                    # For demonstration/Phase 34 scaffolding, we just route it
                    resp = await gateway.dispatch(req)
                    result = resp.message.get("content", "")
                elif action == "inference_gateway.image":
                    # T1 constraint: Image via cloud API
                    logger.info(f"Dispatching image generation with prompt: {step_inputs.get('enriched_prompt')}")
                    # Stub output since inference_gateway doesn't actually support .image yet natively in the same way
                    result = "https://placeholder.url/image.png"
                elif action == "inference_gateway.audio":
                    logger.info(f"Dispatching audio generation with text: {step_inputs.get('text')}")
                    result = "https://placeholder.url/audio.mp3"
                else:
                    raise NotImplementedError(f"Action '{action}' is not supported yet.")

                # Assign outputs
                out_keys = step.get("output_keys", [])
                if len(out_keys) == 1:
                    state[out_keys[0]] = result
                else:
                    # In a real DAG, might need to map multiple returns
                    pass
            except Exception as e:
                logger.error(f"Pipeline '{pipeline_name}' failed at step '{step_name}': {e}")
                raise
        
        return state
