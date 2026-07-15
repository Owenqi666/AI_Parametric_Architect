"""Verify schema loading from an isolated wheel installation."""

from ai_parametric_architect.contracts import load_model_schema
from ai_parametric_architect.intent import load_intent_schema

EXPECTED_SCHEMA_IDS = {
    "model": "https://schemas.ai-parametric-architect.dev/model/1.0.0.json",
    "intent": "https://schemas.ai-parametric-architect.dev/design-intent/1.0.0.json",
}


def main() -> int:
    schemas = {
        "model": load_model_schema("1.0.0"),
        "intent": load_intent_schema("1.0.0"),
    }
    for name, schema in schemas.items():
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            raise SystemExit(f"Installed package did not load the expected {name} schema")
        if schema.get("$id") != EXPECTED_SCHEMA_IDS[name]:
            raise SystemExit(f"Installed package loaded the wrong {name} schema version")
    print("Verified model and intent schema loading from isolated wheel installation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
