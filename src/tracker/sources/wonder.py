"""
CDC WONDER client.

WONDER's API is an XML POST to a per-dataset controller URL. There is no
JSON, no auth, no key, and no rate limit published. It is free forever,
which is the entire reason this project can run at zero cost.

Two things will bite you:

1. Suppression. Any cell with fewer than 10 deaths comes back as
   "Suppressed" rather than a number. For hanging deaths broken down by
   race AND state AND year you will hit this constantly. Do not treat a
   suppressed cell as zero. The schema has a dedicated flag for it.

2. The API rejects some breakdowns that the web UI allows, and the
   parameter codes differ between dataset files. D77 is the 1999-2020
   multiple-cause file. Provisional years live under different ids.
   Verify codes against the WONDER site before trusting a pull.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import httpx

WONDER_BASE = "https://wonder.cdc.gov/controller/datarequest"

# ICD-10 codes for hanging/strangulation/suffocation, split by intent.
# The pairing is the point: the ratio between them is the signal.
ICD_SELF_HARM = "X70"       # intentional self-harm
ICD_UNDETERMINED = "Y20"    # hanging, undetermined intent
ICD_ASSAULT = "X91"         # assault by hanging/strangulation/suffocation


@dataclass
class WonderQuery:
    dataset: str = "D77"
    years: tuple[int, ...] = ()
    group_by: tuple[str, ...] = ("D77.V1-level1", "D77.V9", "D77.V8")
    icd_codes: tuple[str, ...] = (ICD_SELF_HARM, ICD_UNDETERMINED, ICD_ASSAULT)


def _param(name: str, *values: str) -> ET.Element:
    el = ET.Element("parameter")
    ET.SubElement(el, "name").text = name
    for v in values:
        ET.SubElement(el, "value").text = v
    return el


def build_request(q: WonderQuery) -> str:
    """
    Build the XML body. WONDER wants every B_* (group-by) slot filled,
    padded with '*None*' for unused ones. Omitting them 500s.
    """
    root = ET.Element("request-parameters")
    root.append(_param("accept_datause_restrictions", "true"))

    slots = list(q.group_by) + ["*None*"] * (5 - len(q.group_by))
    for i, slot in enumerate(slots[:5], start=1):
        root.append(_param(f"B_{i}", slot))

    # Measures: deaths, population, crude rate
    root.append(_param("M_1", "D77.M1"))
    root.append(_param("M_2", "D77.M2"))
    root.append(_param("M_3", "D77.M3"))

    if q.years:
        root.append(_param("F_D77.V1", *[str(y) for y in q.years]))
    else:
        root.append(_param("F_D77.V1", "*All*"))

    # V2 is the underlying-cause ICD-10 axis on D77.
    root.append(_param("F_D77.V2", *q.icd_codes))

    root.append(_param("O_precision", "1"))
    root.append(_param("O_show_totals", "false"))
    root.append(_param("O_show_suppressed", "true"))

    return ET.tostring(root, encoding="unicode")


def fetch(q: WonderQuery, timeout: float = 90.0) -> str:
    url = f"{WONDER_BASE}/{q.dataset}"
    resp = httpx.post(
        url,
        data={"request_xml": build_request(q), "accept_datause_restrictions": "true"},
        timeout=timeout,
        headers={"User-Agent": "hanging-deaths-tracker (research; contact in repo)"},
    )
    resp.raise_for_status()
    return resp.text


def parse(xml_text: str) -> list[dict]:
    """
    WONDER returns <data-table><r><c .../></r></data-table>. Cells carry
    either a label (group-by value) or a value (measure). Suppressed and
    unreliable cells come back with those literal strings.
    """
    root = ET.fromstring(xml_text)
    rows: list[dict] = []
    now = dt.datetime.now(dt.timezone.utc).isoformat()

    for r in root.iter("r"):
        labels, values = [], []
        for c in r.iter("c"):
            if (lab := c.get("l")) is not None:
                labels.append(lab)
            elif (val := c.get("v")) is not None:
                values.append(val)

        def num(idx: int):
            if idx >= len(values):
                return None
            raw = values[idx].replace(",", "").strip()
            if raw in ("Suppressed", "Unreliable", "Not Applicable", ""):
                return None
            try:
                return float(raw)
            except ValueError:
                return None

        joined = " ".join(values)
        rows.append({
            "labels": labels,
            "deaths": num(0),
            "population": num(1),
            "crude_rate": num(2),
            "suppressed": int("Suppressed" in joined),
            "unreliable": int("Unreliable" in joined),
            "fetched_at": now,
        })
    return rows


def load(conn: sqlite3.Connection, dataset: str, rows: list[dict]) -> int:
    """
    Map parsed rows into mortality_agg. Label ordering follows the
    group_by tuple you passed, so keep them in sync.
    """
    n = 0
    for row in rows:
        labels = row["labels"] + [None] * (3 - len(row["labels"]))
        year, race, icd = labels[0], labels[1], labels[2]
        conn.execute(
            """
            INSERT INTO mortality_agg
                (dataset, year, state, race, icd10_code, deaths,
                 population, crude_rate, suppressed, unreliable, fetched_at)
            VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT DO UPDATE SET
                deaths = excluded.deaths,
                population = excluded.population,
                crude_rate = excluded.crude_rate,
                suppressed = excluded.suppressed,
                fetched_at = excluded.fetched_at
            """,
            (dataset, int(year) if year and year.isdigit() else None, race, icd,
             row["deaths"], row["population"], row["crude_rate"],
             row["suppressed"], row["unreliable"], row["fetched_at"]),
        )
        n += 1
    conn.commit()
    return n
