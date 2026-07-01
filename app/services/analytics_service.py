import json
import pandas as pd
from pathlib import Path


METADATA_DIR = Path("storage/metadata")


def load_datasets():

    records = []

    for file in METADATA_DIR.glob("*.json"):

        with open(file, "r") as f:
            records.append(json.load(f))

    if not records:
        return pd.DataFrame()

    return pd.DataFrame(records)