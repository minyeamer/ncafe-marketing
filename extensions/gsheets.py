from __future__ import annotations

from gspread import service_account_from_dict

from typing import Callable, Sequence, TypedDict, TYPE_CHECKING
import datetime as dt
import json
import re

if TYPE_CHECKING:
    from typing import Any, Hashable, Literal, TypeVar
    _KT = TypeVar("_KT", Hashable)
    _VT = TypeVar("_VT", Any)
    JsonString = TypeVar("JsonString", str)
    Path = TypeVar("Path", str)

    from gspread import Client as ServiceClient
    from gspread.spreadsheet import Spreadsheet
    from gspread.worksheet import Worksheet, JSONResponse
    from gspread.exceptions import WorksheetNotFound


ACCOUNT_PATH = ".secrets/service_account.json"


class ServiceAccount(dict):
    def __init__(self, info: JsonString | Path | dict[str,str]):
        super().__init__(self.read_account(info))

    def read_account(self, info: JsonString | Path | dict[str,str]) -> dict:
        if isinstance(info, dict):
            return info
        elif isinstance(info, str):
            if info.startswith('{') and info.endswith('}'):
                return json.loads(info)
            else:
                with open(info, 'r', encoding="utf-8") as file:
                    return json.loads(file.read())
        else:
            raise ValueError("Unrecognized service account.")


def worksheet2py(
        records: list[dict[_KT,_VT]],
        keys: _KT | list[_KT] | None = None,
    ) -> list[dict[_KT,_VT]] | list[_VT]:
    """Convert worksheet values to python objects."""

    def to_python_object(value: Any) -> Any:
        if isinstance(value, str):
            if value == "TRUE":
                return True
            elif value == "FALSE":
                return False
            elif re.match(r"^\d+(\.\d*)?%$", value):
                return float(value[:-1]) / 100
            elif re.match(r"^\d{4}-\d{2}-\d{2}", value):
                if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
                    return dt.datetime.strptime(value, "%Y-%m-%d").date()
                elif re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", value):
                    return dt.datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
                elif re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}", value):
                    return dt.datetime.strptime(value, "%Y-%m-%d %H:%M")
                elif re.match(r"^\d{4}-\d{2}-\d{2} \d{2}", value):
                    return dt.datetime.strptime(value, "%Y-%m-%d %H")
        return value

    return list_apply(records, func=to_python_object, keys=keys)


def py2worksheet(
        records: list[dict],
        expected_headers: list[str] | None = None,
        include_header: bool = False,
    ) -> list[tuple]:
    """Convert python objects to Worksheet values without keys."""
    import datetime as dt

    def to_excel_format(value: Any) -> Any:
        if isinstance(value, dt.date):
            offset = 693594
            days = value.toordinal() - offset
            if isinstance(value, dt.datetime):
                seconds = (value.hour*60*60 + value.minute*60 + value.second)/(24*60*60)
                return days + seconds
            else:
                return days
        else:
            return value

    return to_csv(records, to_excel_format, expected_headers, include_header)


def to_csv(
        __r: list[dict[_KT,_VT]],
        apply: Callable | None = None,
        expected_headers: list[str] | None = None,
        include_header: bool = False,
        default: _VT | None = None,
    ) -> list[tuple]:
    func = apply if isinstance(apply, Callable) else (lambda x: x)
    header = expected_headers if isinstance(expected_headers, Sequence) else list(__r[0].keys())
    csv = [tuple(func(__m.get(key, default)) for key in header) for __m in __r]
    return ([header] if include_header else list()) + csv


###################################################################
######################### Worksheet Client ########################
###################################################################

class WorksheetConnection(TypedDict):
    account: str | Path
    key: str
    sheet: str
    head: int


class WorksheetClient:
    def __init__(
            self,
            account: ServiceAccount,
            key: str | None = None,
            sheet: str | None = None,
            head: int = 1,
        ):
        self.set_client(account)
        if key is not None:
            self.set_spreadsheet(key)
        if sheet is not None:
            self.set_worksheet(sheet)
        self.head = head

    def get_client(self) -> ServiceClient:
        return self.__client

    def set_client(self, account: ServiceAccount):
        self.__client = service_account_from_dict(ServiceAccount(account))

    ########################### Spreadsheet ###########################

    @property
    def key(self) -> str:
        return self.get_key()

    @property
    def spreadsheet(self) -> Spreadsheet:
        return self.get_spreadsheet()

    def get_key(self) -> str:
        return self.__key

    def get_spreadsheet(self) -> Spreadsheet:
        return self.__spreadsheet

    def set_spreadsheet(self, key: str):
        self.__key = key
        self.__spreadsheet = self.get_client().open_by_key(key)

    ############################ Worksheet ############################

    @property
    def sheetname(self) -> str:
        return self.get_sheetname()

    @property
    def worksheet(self) -> Worksheet:
        return self.get_worksheet()

    def get_sheetname(self) -> str:
        return self.__sheetname

    def get_worksheet(self) -> Worksheet:
        return self.__worksheet

    def set_worksheet(self, sheet: str):
        self.__sheetname = sheet
        self.__worksheet = self.spreadsheet.worksheet(sheet)

    def worksheet_exists(self, sheet: str) -> bool:
        try:
            self.spreadsheet.worksheet(sheet)
            return True
        except WorksheetNotFound:
            return False

    def clear(self, include_header=False) -> JSONResponse:
        if include_header:
            return self.worksheet.clear()
        else:
            last_row = self.count_rows()
            self.worksheet.insert_row([], 2)
            return self.worksheet.delete_rows(3, last_row+2)

    ########################### Get Records ###########################

    def get_all_records(
            self,
            expected_headers: Any | None = None,
            filter_headers: _KT | list[_KT] | None = None,
            value_render_option: Any | None = None,
            default_blank: str | None = None,
            numericise_ignore: Sequence[int] | bool = list(),
            allow_underscores_in_numeric_literals: bool = False,
            empty2zero: bool = False,
            convert_dtypes: bool = True,
        ) -> list[dict]:
        records = self.worksheet.get_all_records(
            self.head, expected_headers, value_render_option, default_blank,
            self._numericise_ignore(numericise_ignore), allow_underscores_in_numeric_literals, empty2zero)
        if convert_dtypes:
            return worksheet2py(records, filter_headers)
        else:
            return list_get(records, filter_headers) if filter_headers is not None else records

    def count_rows(self, include_header: bool = False) -> int:
        return len(self.worksheet.get_values("A:A")) - bool(not include_header)

    def get_header_row(self) -> list[str]:
        return self.worksheet.get_values("1:1")[0]

    def _auto_detect_header(self, columns: list[str]) -> list[int]:
        header = self.get_header_row()
        not_exists = [col for col in columns if col not in header]
        if not_exists:
            raise ValueError(f"Could not found columns in the header row: {', '.join(not_exists)}.")
        return [header.index(col) for col in columns]

    def _numericise_ignore(self, columns: list[str | int] | bool) -> list[int] | list[Literal["all"]]:
        if not columns:
            return list()
        elif isinstance(columns, bool):
            return ["all"]
        elif all(map(lambda x: isinstance(x, str), columns)):
            return self._auto_detect_header(columns)
        else:
            return columns

    ############################ Overwrite ############################

    def overwrite_worksheet(
            self,
            records: list[dict],
            expected_headers: list[str] | None = None,
            include_header: bool = False,
            match_header: bool = False,
        ) -> JSONResponse:
        if not records:
            return
        table = py2worksheet(records, expected_headers, include_header=True)
        if match_header:
            table = self._match_table_header(table)
        if not include_header:
            table = table[self.head:]
        self.clear(include_header)
        return self.worksheet.update(table, range_name=("A1" if include_header else "A2"))

    def _match_table_header(self, table: list[tuple]) -> list[tuple]:
        sheet_header = self.get_header_row()
        table_header = table[0]
        if set(table_header) - set(sheet_header):
            mismatch = ", ".join(sorted(set(table_header) - set(sheet_header)))
            raise ValueError(f"Worksheet header mismatch: {mismatch}.")
        elif sheet_header != table_header:
            reorder = [(sheet_header.index(col) if col in sheet_header else None) for col in table_header]
            return [tuple((row[i] if isinstance(i, int) else None) for i in reorder) for row in table]
        else:
            return table


###################################################################
########################## List Functions #########################
###################################################################

def apply_values(
        __m: dict[_KT,_VT],
        func: Callable,
        keys: _KT | Sequence[_KT] | None = None,
        default: _VT | None = None
    ) -> dict[_KT,_VT]:
    if keys is None:
        return {key: func(value) for key, value in __m.items()}
    elif (not isinstance(keys, str)) and isinstance(keys, Sequence):
        return {key: func(__m.get(key, default)) for key in keys}
    else:
        return func(__m.get(keys, default))


def list_apply(
        __r: list[dict[_KT,_VT]],
        func: Callable,
        keys: _KT | Sequence[_KT] | None = None,
        default: _VT | None = None,
    ) -> list[dict[_KT,_VT]] | list[_VT]:
    return [apply_values(__m, func, keys, default) for __m in __r]


def get_values(__m: dict[_KT,_VT], keys: _KT | Sequence[_KT], default: _VT | None = None) -> dict[_KT,_VT]:
    if (not isinstance(keys, str)) and isinstance(keys, Sequence):
        return {key: __m.get(key, default) for key in keys}
    else:
        return __m.get(keys, default)


def list_get(__r: list[dict[_KT,_VT]], keys: _KT | Sequence[_KT], default: _VT | None = None) -> list[dict[_KT,_VT]] | list[_VT]:
    return [get_values(__m, keys, default) for __m in __r]
