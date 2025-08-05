import os


def _get_required(name: str) -> str:
    value = os.getenv(name)
    if value is None:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _parse_int_list(value: str) -> list[int]:
    return [int(v.strip()) for v in value.split(',') if v.strip()]


API_TOKEN = _get_required("API_TOKEN")
GROUP1_ID = int(_get_required("GROUP1_ID"))
GROUP2_IDS = _parse_int_list(os.getenv("GROUP2_IDS", ""))
TOPIC_IDS_GROUP1 = _parse_int_list(os.getenv("TOPIC_IDS_GROUP1", ""))
