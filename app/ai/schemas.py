ANALYZE_WORKFLOW_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "steps": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "order": {"type": "INTEGER"},
                    "title": {"type": "STRING"},
                    "description": {"type": "STRING"},
                    "required_inputs": {
                        "type": "ARRAY",
                        "items": {"type": "STRING"},
                    },
                    "evidence": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "source": {"type": "STRING"},
                                "location": {"type": "STRING"},
                            },
                            "required": ["source", "location"],
                        },
                    },
                },
                "required": ["order", "title", "description", "required_inputs", "evidence"],
            },
        },
        "unconfirmed": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },
    },
    "required": ["steps", "unconfirmed"],
}

QA_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "answer": {"type": "STRING"},
        "evidence": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "source": {"type": "STRING"},
                    "location": {"type": "STRING"},
                },
                "required": ["source", "location"],
            },
        },
        "needs_confirmation": {"type": "BOOLEAN"},
        "confirmation_reason": {"type": "STRING"},
    },
    "required": ["answer", "evidence", "needs_confirmation"],
}

PRACTICE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "situation": {"type": "STRING"},
        "questions": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "prompt": {"type": "STRING"},
                    "choices": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "correct_index": {"type": "INTEGER"},
                    "explanation": {"type": "STRING"},
                    "evidence": {"type": "STRING"},
                },
                "required": ["prompt", "choices", "correct_index", "explanation", "evidence"],
            },
        },
    },
    "required": ["situation", "questions"],
}
