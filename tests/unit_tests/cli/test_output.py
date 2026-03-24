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

import json

from nautilus_trader.cli.output import format_error
from nautilus_trader.cli.output import format_output


class TestFormatJson:
    def test_dict(self) -> None:
        result = format_output({"key": "value"}, "json")
        parsed = json.loads(result)

        assert parsed == {"key": "value"}

    def test_list(self) -> None:
        result = format_output([{"a": 1}, {"a": 2}], "json")
        parsed = json.loads(result)

        assert len(parsed) == 2


class TestFormatCsv:
    def test_list_of_dicts(self) -> None:
        data = [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
        ]
        result = format_output(data, "csv")
        lines = result.strip().split("\n")

        assert lines[0] == "name,age"
        assert lines[1] == "Alice,30"
        assert lines[2] == "Bob,25"

    def test_single_dict(self) -> None:
        result = format_output({"name": "Alice"}, "csv")
        lines = result.strip().split("\n")

        assert lines[0] == "name"
        assert lines[1] == "Alice"

    def test_empty_list(self) -> None:
        result = format_output([], "csv")

        assert result == ""

    def test_custom_columns(self) -> None:
        data = [{"name": "Alice", "age": 30, "city": "NY"}]
        result = format_output(data, "csv", columns=["name", "city"])
        lines = result.strip().split("\n")

        assert lines[0] == "name,city"
        assert lines[1] == "Alice,NY"


class TestFormatTable:
    def test_dict_table(self) -> None:
        data = {"trader_id": "TRADER-001", "state": "RUNNING"}
        result = format_output(data, "table", title="Status")

        assert "Status" in result
        assert "trader_id" in result
        assert "TRADER-001" in result

    def test_list_table(self) -> None:
        data = [
            {"id": "S-001", "state": "RUNNING"},
            {"id": "S-002", "state": "STOPPED"},
        ]
        result = format_output(data, "table")

        assert "S-001" in result
        assert "RUNNING" in result
        assert "S-002" in result

    def test_empty_list(self) -> None:
        result = format_output([], "table", title="Items")

        assert "(empty)" in result

    def test_string_passthrough(self) -> None:
        result = format_output("plain text", "table")

        assert result == "plain text"


class TestFormatError:
    def test_format_error(self) -> None:
        result = format_error("NOT_FOUND", "Order not found")

        assert "NOT_FOUND" in result
        assert "Order not found" in result
