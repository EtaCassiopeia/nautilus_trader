# -------------------------------------------------------------------------------------------------
#  Copyright (C) 2015-2026 Nautech Systems Pty Ltd. All rights reserved.
#  https://nautechsystems.io
#
#  Licensed under the GNU Lesser General Public License Version 3.0 (the "License");
#  You may not use this file except in compliance with the License.
#  You may obtain a copy of the License at https://www.gnu.org/licenses/lgpl-3.0.en.html
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
# -------------------------------------------------------------------------------------------------

from __future__ import annotations

import csv
import io
import json
from typing import Any


def format_output(
    data: Any,
    output_format: str = "table",
    columns: list[str] | None = None,
    title: str | None = None,
) -> str:
    """
    Format data for terminal output.

    Parameters
    ----------
    data : Any
        The data to format. Can be a dict, list of dicts, or string.
    output_format : str
        Output format: "table", "json", or "csv".
    columns : list[str], optional
        Column names for table/CSV output. Auto-detected if None.
    title : str, optional
        Title for table output.

    Returns
    -------
    str

    """
    if output_format == "json":
        return _format_json(data)
    elif output_format == "csv":
        return _format_csv(data, columns)
    else:
        return _format_table(data, columns, title)


def _format_json(data: Any) -> str:
    """Format data as indented JSON."""
    return json.dumps(data, indent=2, default=str)


def _format_csv(data: Any, columns: list[str] | None = None) -> str:
    """Format data as CSV."""
    if isinstance(data, dict):
        data = [data]

    if not isinstance(data, list) or not data:
        return ""

    if columns is None:
        columns = list(data[0].keys())

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in data:
        writer.writerow(row)

    return output.getvalue().replace("\r\n", "\n").strip()


def _format_table(
    data: Any,
    columns: list[str] | None = None,
    title: str | None = None,
) -> str:
    """Format data as a text table."""
    if isinstance(data, str):
        return data

    if isinstance(data, dict):
        return _format_dict_table(data, title)

    if isinstance(data, list):
        if not data:
            return title + "\n(empty)" if title else "(empty)"
        if isinstance(data[0], dict):
            return _format_list_table(data, columns, title)

    return str(data)


def _format_dict_table(data: dict, title: str | None = None) -> str:
    """Format a dict as a key-value table."""
    lines = []
    if title:
        lines.append(title)
        lines.append("=" * len(title))

    if not data:
        lines.append("(empty)")
        return "\n".join(lines)

    max_key_len = max(len(str(k)) for k in data.keys())
    for key, value in data.items():
        lines.append(f"  {str(key):<{max_key_len}}  {value}")

    return "\n".join(lines)


def _format_list_table(
    data: list[dict],
    columns: list[str] | None = None,
    title: str | None = None,
) -> str:
    """Format a list of dicts as a text table."""
    if columns is None:
        columns = list(data[0].keys())

    # Calculate column widths
    col_widths: dict[str, int] = {}
    for col in columns:
        header_len = len(col)
        max_val = max((len(str(row.get(col, ""))) for row in data), default=0)
        col_widths[col] = max(header_len, max_val)

    # Build header
    lines = []
    if title:
        lines.append(title)

    header = "  ".join(col.ljust(col_widths[col]) for col in columns)
    separator = "  ".join("-" * col_widths[col] for col in columns)
    lines.append(header)
    lines.append(separator)

    # Build rows
    for row in data:
        line = "  ".join(
            str(row.get(col, "")).ljust(col_widths[col])
            for col in columns
        )
        lines.append(line)

    return "\n".join(lines)


def format_error(code: str, message: str) -> str:
    """Format an error for terminal output."""
    return f"Error [{code}]: {message}"
