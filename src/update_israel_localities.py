from __future__ import annotations

import argparse
import json
import math
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


DATASTORE_URL = "https://data.gov.il/api/3/action/datastore_search"
RESOURCE_ID = "d47a54ff-87f0-44b3-b33a-f284c0c38e5a"
PACKAGE_ID = "localities-in-israel"
SOURCE_URL = f"https://data.gov.il/he/datasets/lamas/{PACKAGE_ID}"
DEFAULT_OUT = Path("data/public/israel_localities.json")
DEFAULT_TIMEZONE = "Asia/Jerusalem"

FIELD_NAME = "שם יישוב"
FIELD_CODE = "סמל יישוב"
FIELD_TRANSCRIPTION = "תעתיק"
FIELD_DISTRICT = "שם מחוז"
FIELD_SUBDISTRICT = "שם נפה"
FIELD_MUNICIPALITY = "שם מעמד מונציפאלי"
FIELD_COORDINATES = "קואורדינטות"
FIELD_YEAR = "שנה"
FIELD_ENGLISH_NAME = "שם יישוב באנגלית"
FIELD_POPULATION = "סך הכל אוכלוסייה 2023 - ארעי"


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def unique_terms(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for term in terms:
        clean = clean_text(term)
        lowered = clean.lower()
        if clean and lowered not in seen:
            seen.add(lowered)
            result.append(clean)
    return result


def parse_optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).replace(",", "")))
    except ValueError:
        return None


def parse_itm_coordinates(value: Any) -> tuple[int, int] | None:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) < 10:
        return None
    x = int(digits[:-6])
    y = int(digits[-6:])
    if not (10000 <= x <= 300000 and 350000 <= y <= 800000):
        return None
    return x, y


def itm_to_wgs84(easting: int | float, northing: int | float) -> tuple[float, float]:
    # EPSG:2039 Israel TM Grid, inverse Transverse Mercator on GRS80.
    semi_major_axis = 6378137.0
    inverse_flattening = 298.257222101
    flattening = 1 / inverse_flattening
    eccentricity_squared = 2 * flattening - flattening * flattening
    second_eccentricity_squared = eccentricity_squared / (1 - eccentricity_squared)

    latitude_origin = math.radians(31 + 44 / 60 + 3.817 / 3600)
    longitude_origin = math.radians(35 + 12 / 60 + 16.261 / 3600)
    scale_factor = 1.0000067
    false_easting = 219529.584
    false_northing = 626907.39

    x = float(easting) - false_easting
    y = float(northing) - false_northing

    def meridional_arc(phi: float) -> float:
        return semi_major_axis * (
            (1 - eccentricity_squared / 4 - 3 * eccentricity_squared**2 / 64 - 5 * eccentricity_squared**3 / 256) * phi
            - (3 * eccentricity_squared / 8 + 3 * eccentricity_squared**2 / 32 + 45 * eccentricity_squared**3 / 1024)
            * math.sin(2 * phi)
            + (15 * eccentricity_squared**2 / 256 + 45 * eccentricity_squared**3 / 1024) * math.sin(4 * phi)
            - (35 * eccentricity_squared**3 / 3072) * math.sin(6 * phi)
        )

    origin_arc = meridional_arc(latitude_origin)
    meridional = origin_arc + y / scale_factor
    mu = meridional / (
        semi_major_axis
        * (1 - eccentricity_squared / 4 - 3 * eccentricity_squared**2 / 64 - 5 * eccentricity_squared**3 / 256)
    )
    e1 = (1 - math.sqrt(1 - eccentricity_squared)) / (1 + math.sqrt(1 - eccentricity_squared))
    footprint_latitude = (
        mu
        + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu)
        + (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu)
        + (151 * e1**3 / 96) * math.sin(6 * mu)
        + (1097 * e1**4 / 512) * math.sin(8 * mu)
    )

    sin_latitude = math.sin(footprint_latitude)
    cos_latitude = math.cos(footprint_latitude)
    tan_latitude = math.tan(footprint_latitude)
    radius_prime_vertical = semi_major_axis / math.sqrt(1 - eccentricity_squared * sin_latitude * sin_latitude)
    radius_meridian = semi_major_axis * (1 - eccentricity_squared) / (
        1 - eccentricity_squared * sin_latitude * sin_latitude
    ) ** 1.5
    tan_squared = tan_latitude * tan_latitude
    c = second_eccentricity_squared * cos_latitude * cos_latitude
    d = x / (radius_prime_vertical * scale_factor)

    latitude = footprint_latitude - (radius_prime_vertical * tan_latitude / radius_meridian) * (
        d * d / 2
        - (5 + 3 * tan_squared + 10 * c - 4 * c * c - 9 * second_eccentricity_squared) * d**4 / 24
        + (
            61
            + 90 * tan_squared
            + 298 * c
            + 45 * tan_squared * tan_squared
            - 252 * second_eccentricity_squared
            - 3 * c * c
        )
        * d**6
        / 720
    )
    longitude = longitude_origin + (
        d
        - (1 + 2 * tan_squared + c) * d**3 / 6
        + (5 - 2 * c + 28 * tan_squared - 3 * c * c + 8 * second_eccentricity_squared + 24 * tan_squared * tan_squared)
        * d**5
        / 120
    ) / cos_latitude

    return round(math.degrees(latitude), 6), round(math.degrees(longitude), 6)


def fetch_page(resource_id: str, limit: int, offset: int, timeout: int, retries: int) -> dict[str, Any]:
    query = urllib.parse.urlencode({"resource_id": resource_id, "limit": limit, "offset": offset})
    request = urllib.request.Request(
        f"{DATASTORE_URL}?{query}",
        headers={"User-Agent": "job-searcher-localities-updater/1.0"},
    )
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as error:  # pragma: no cover - exercised only on transient network failures.
            last_error = error
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch data.gov.il resource {resource_id}: {last_error}") from last_error


def fetch_records(resource_id: str = RESOURCE_ID, limit: int = 500, timeout: int = 30, retries: int = 2) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    offset = 0
    total: int | None = None
    while total is None or offset < total:
        payload = fetch_page(resource_id, limit, offset, timeout, retries)
        if not payload.get("success"):
            raise RuntimeError(f"data.gov.il returned an unsuccessful response for {resource_id}")
        result = payload.get("result") or {}
        page_records = result.get("records") or []
        records.extend(page_records)
        total = int(result.get("total") or len(records))
        offset += limit
    return records


def locality_terms(label: str, english: str, transcription: str) -> list[str]:
    variants = [label, english, transcription]
    for value in (label, english, transcription):
        clean = clean_text(value)
        if "-" in clean:
            variants.append(re.sub(r"\s*-\s*", " - ", clean))
            variants.append(re.sub(r"\s*-\s*", "-", clean))
    return unique_terms(variants)


def build_locality_record(record: dict[str, Any]) -> dict[str, Any] | None:
    label = clean_text(record.get(FIELD_NAME))
    code = parse_optional_int(record.get(FIELD_CODE))
    coordinates = parse_itm_coordinates(record.get(FIELD_COORDINATES))
    if not label or code is None or coordinates is None:
        return None

    lat, lng = itm_to_wgs84(*coordinates)
    if not (29.4 <= lat <= 33.4 and 34.2 <= lng <= 36.0):
        return None

    english = clean_text(record.get(FIELD_ENGLISH_NAME))
    transcription = clean_text(record.get(FIELD_TRANSCRIPTION))
    population = parse_optional_int(record.get(FIELD_POPULATION))
    return {
        "key": f"cbs_{code}",
        "code": code,
        "label": label,
        "terms": locality_terms(label, english, transcription),
        "lat": lat,
        "lng": lng,
        "kind": "locality",
        "source": "cbs_localities_2023",
        "district": clean_text(record.get(FIELD_DISTRICT)),
        "subdistrict": clean_text(record.get(FIELD_SUBDISTRICT)),
        "municipality": clean_text(record.get(FIELD_MUNICIPALITY)),
        "english": english,
        "transcription": transcription,
        "population": population,
    }


def build_dataset(records: list[dict[str, Any]], timezone: str = DEFAULT_TIMEZONE) -> dict[str, Any]:
    localities = [item for record in records if (item := build_locality_record(record))]
    localities.sort(key=lambda item: (str(item["label"]), int(item["code"])))
    years = sorted({parse_optional_int(record.get(FIELD_YEAR)) for record in records if parse_optional_int(record.get(FIELD_YEAR))})
    return {
        "source": {
            "name": "הלמ״ס - יישובים בישראל, קובץ היישובים 2023",
            "package_id": PACKAGE_ID,
            "resource_id": RESOURCE_ID,
            "url": SOURCE_URL,
            "coordinate_system": "Israel TM Grid / EPSG:2039 converted to WGS84",
            "years": years,
            "downloaded_at": datetime.now(ZoneInfo(timezone)).isoformat(timespec="seconds"),
            "records": len(records),
            "usable_localities": len(localities),
        },
        "localities": localities,
    }


def write_dataset(dataset: dict[str, Any], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Download CBS Israel localities and convert them to dashboard map points.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--resource-id", default=RESOURCE_ID)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    args = parser.parse_args()

    records = fetch_records(args.resource_id, args.limit, args.timeout, args.retries)
    dataset = build_dataset(records, args.timezone)
    write_dataset(dataset, args.out)
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(args.out),
                "records": dataset["source"]["records"],
                "usable_localities": dataset["source"]["usable_localities"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
