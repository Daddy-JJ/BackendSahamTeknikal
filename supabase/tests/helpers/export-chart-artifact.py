"""Export explicitly synthetic canonical chart input/artifact for SQL integration proof."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scanner" / "src"))

from idx_scanner.chart_fixture import synthetic_chart_export

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--owner-id", default="22222222-2222-4222-8222-222222222222")
parser.add_argument("--series-id", default="11111111-1111-4111-8111-111111111111")
args = parser.parse_args()
print(json.dumps(synthetic_chart_export(args.owner_id, args.series_id), allow_nan=False))
