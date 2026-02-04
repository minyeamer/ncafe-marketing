from __future__ import annotations
import functools

from pywinauto import Desktop
from pywinauto.controls.uiawrapper import UIAWrapper
from pywinauto.keyboard import send_keys

from utils.common import AttrDict

from typing import TypeVar, TypedDict, TYPE_CHECKING
import os
import re
import subprocess
import time

if TYPE_CHECKING:
    from typing import Literal
    from pathlib import Path
    from pywinauto.controls.uia_controls import ButtonWrapper, EditWrapper, StaticWrapper
    from pywinauto.win32structures import RECT

IpAddress = TypeVar("IpAddress", bound=str)


class VpnRuntimeError(RuntimeError):
    ...

class ElementNotFoundError(VpnRuntimeError):
    ...

class LoginFailedError(VpnRuntimeError):
    ...

class VpnInUseError(VpnRuntimeError):
    ...

class VpnFailedError(VpnRuntimeError):
    ...


class Client(AttrDict):

    def __init__(
            self,
            exe_path: str | Path,
            process_name: str,
        ):
        if not os.path.exists(str(exe_path)):
            raise FileNotFoundError(f"[Errno 2] No such file or directory: '{exe_path}'")
        self.exe_path = exe_path
        self.process_name = process_name
        self.__desktop = Desktop(backend="uia")

    @property
    def desktop(self) -> Desktop:
        return self.__desktop

    ########################## Handle Process #########################

    def start_process(self, force_restart: bool = False) -> bool:
        is_process_running = self.is_process_running()
        if force_restart and is_process_running:
            self.terminate_process()
            is_process_running = False

        if not is_process_running:
            subprocess.Popen([self.exe_path, "connect"], shell=True)
        return True

    def terminate_process(self, exact: bool = True) -> bool:
        process_name = self.process_name if exact else f"*{self.process_name}*"
        return (subprocess.run(["taskkill", "/F", "/IM", process_name],
                    shell=True, capture_output=True).stdout.decode("cp949", errors="ignore")
                .startswith("성공:"))

    def is_process_running(self) -> bool:
        return bool(
            subprocess.run(["tasklist", '|', "findstr", self.process_name],
                shell=True, capture_output=True).stdout)

    ########################## Handle Window ##########################

    def wait_window_open(
            self,
            title_patttern: re.Pattern[str],
            timeout: float = 30.,
            interval: float = 0.25,
            error_msg: str | Literal[":default:"] = str(),
        ) -> UIAWrapper:
        start_time = time.perf_counter()
        while (time.perf_counter() - start_time) < timeout:
            if isinstance(window := self.catch_window(title_patttern), UIAWrapper):
                spec = self.desktop.window(handle=window.handle)
                spec.wait("visible", timeout=3)
                return spec.wrapper_object()
            time.sleep(interval)

        if error_msg == ":default:":
            error_msg = f"패턴 '{title_patttern.pattern}'에 매칭되는 윈도우를 찾을 수 없습니다."
        raise TimeoutError(error_msg)

    def catch_window(self, title_patttern: re.Pattern[str]) -> UIAWrapper | None:
        windows: list[UIAWrapper] = self.desktop.windows()
        for window in windows:
            try:
                title = str(window.window_text()).strip()
                if title_patttern.search(title):
                    return window
            except Exception:
                continue
        return None


###################################################################
####################### Client Config - VPN #######################
###################################################################

class VpnPattern(AttrDict):

    def __init__(
            self,
            common: str | re.Pattern[str],
            login: str | re.Pattern[str],
            service: str | re.Pattern[str],
            connected: str | re.Pattern[str],
        ):
        self.common = common if isinstance(common, re.Pattern) else re.compile(common)
        self.login = login if isinstance(login, re.Pattern) else re.compile(login)
        self.service = service if isinstance(service, re.Pattern) else re.compile(service)
        self.connected = connected if isinstance(connected, re.Pattern) else re.compile(connected)


class WaitOptions(TypedDict, total=False):
    timeout: float
    interval: float
    wait_after: float


class VpnConfig(AttrDict):
    def __init__(
        self,
        exe_path: str | Path,
        process_name: str,
        title_patterns: VpnPattern | dict[str, str | re.Pattern[str]],
        service_name: str,
        userid: str = str(),
        passwd: str = str(),
        ip_addr: str = str(),
        subnet: str = str(),
        service_no: int = 1,
        force_restart: bool = False,
        force_connect: bool = False,
        wait_timeout: float = 30.,
        wait_interval: float = 0.25,
        wait_after: float | None = 0.5,
    ):
        self.exe_path = exe_path
        self.process_name = process_name
        self.title_patterns = title_patterns
        self.service_name = service_name
        self.userid = userid
        self.passwd = passwd
        self.ip_addr = ip_addr
        self.service_no = service_no
        self.subnet = subnet
        self.force_restart = force_restart
        self.force_connect = force_connect
        self.wait_options: WaitOptions = dict(timeout=wait_timeout, interval=wait_interval, wait_after=wait_after)

    @property
    def login(self) -> dict:
        return dict(userid=self.userid, passwd=self.passwd, **self.wait_options)

    @property
    def connect(self) -> dict:
        keys = ["service_name", "service_no", "subnet", "force_connect", "on_failure"]
        return dict({key: self[key] for key in keys}, **self.wait_options)

    @property
    def search_and_connect(self) -> dict:
        keys = ["ip_addr", "service_name", "service_no", "subnet", "force_connect", "on_failure"]
        return dict({key: self[key] for key in keys}, **self.wait_options)


###################################################################
###################### Client Executor - VPN ######################
###################################################################

class VpnClient(Client):

    def __init__(
            self,
            exe_path: str | Path,
            process_name: str,
            title_patterns: VpnPattern | dict[str, str | re.Pattern[str]],
        ):
        super().__init__(exe_path, process_name)
        if isinstance(title_patterns, VpnPattern):
            self.title_patterns = title_patterns
        else:
            self.title_patterns = VpnPattern(**title_patterns)

    ########################## Handle Window ##########################

    def focus_window(func):
        @functools.wraps(func)
        def wrapper(self: VpnClient, *args, wait_after: float | None = 0.5, **kwargs):
            window: UIAWrapper = func(self, *args, **kwargs)
            if wait_after:
                time.sleep(wait_after)
            window.set_focus()
            return window
        return wrapper

    @focus_window
    def wait_vpn_open(self, timeout: float = 30., interval: float = 0.25, **kwargs) -> UIAWrapper:
        error_msg = "VPN 프로그램을 실행해주세요."
        return self.wait_window_open(self.title_patterns.common, timeout, interval, error_msg)

    @focus_window
    def wait_login_form(self, timeout: float = 30., interval: float = 0.25, **kwargs) -> UIAWrapper:
        error_msg = "VPN 로그인 창이 확인되지 않습니다."
        return self.wait_window_open(self.title_patterns.login, timeout, interval, error_msg)

    @focus_window
    def wait_service_ui(self, timeout: float = 30., interval: float = 0.25, **kwargs) -> UIAWrapper:
        error_msg = "VPN 서비스 목록이 확인되지 않습니다."
        return self.wait_window_open(self.title_patterns.service, timeout, interval, error_msg)

    ############################## Login ##############################

    def try_login(self, userid: str = str(), passwd: str = str(), **wait_options: float) -> bool:
        window = self.wait_vpn_open(**wait_options)
        window_title = str(window.window_text()).strip()

        if not self.title_patterns.login.search(window_title):
            return bool(self.title_patterns.service.search(window_title))
        elif len(edits := window.descendants(control_type="Edit")) < 2:
            raise ElementNotFoundError("로그인 양식이 존재하지 않습니다.")

        if userid: # else use saved value
            input_id: EditWrapper = edits[0]
            input_id.click_input()
            time.sleep(0.05)
            send_keys("^a{BACKSPACE}", pause=0.02)
            send_keys(userid, pause=0.02)

        if passwd: # else use saved value
            input_pw: EditWrapper = edits[1]
            input_pw.click_input()
            time.sleep(0.05)
            send_keys("^a{BACKSPACE}", pause=0.02)
            send_keys(passwd, pause=0.02)

        try:
            login_btn: ButtonWrapper = window.descendants(control_type="Button", title="로그인")[0]
            login_btn.click_input()
        except Exception:
            raise ElementNotFoundError("로그인 버튼이 존재하지 않습니다.")

        try:
            self.wait_service_ui(**wait_options)
            return True
        except TimeoutError:
            if (dialogs := window.descendants(control_type="Window")):
                confirm_btn: ButtonWrapper = window.descendants(control_type="Button", title="확인")[0]
                confirm_btn.click_input()
            raise LoginFailedError("입력하신 아이디 혹은 패스워드가 틀렸습니다. 계정 정보를 확인하여 다시 로그인해 주십시오.")

    def logout(self, **wait_options: float):
        window = self.wait_service_ui(**wait_options)
        try:
            logout_btn: ButtonWrapper = window.descendants(control_type="Button", title="로그아웃")[0]
            logout_btn.click_input()
        except Exception:
            raise ElementNotFoundError("로그아웃 버튼이 존재하지 않습니다.")

    ######################## Search IP Address ########################

    def search_ip_addr(self, text: IpAddress, **wait_options: float):
        window = self.wait_service_ui(**wait_options)
        try:
            search_btn: ButtonWrapper = window.descendants(control_type="Button", title="검색")[0]
        except Exception:
            raise ElementNotFoundError("검색 버튼이 존재하지 않습니다.")

        search_input, (btn_x, btn_y) = None, self._center(search_btn)
        for edit in window.descendants(control_type="Edit"):
            edit_x, edit_y = self._center(edit)
            if (abs(btn_x - edit_x) < 100.) and (abs(btn_y - edit_y) < 12.):
                search_input: EditWrapper = edit
        if search_input is None:
            raise ElementNotFoundError("검색 입력창이 존재하지 않습니다.")

        search_input.click_input()
        time.sleep(0.1)
        send_keys("^a{BACKSPACE}", pause=0.02)
        send_keys(text, pause=0.03)

        time.sleep(0.15)
        search_btn.click_input()

    def _center(self, el: UIAWrapper) -> tuple[float, float]:
        rect: RECT = el.rectangle()
        return (rect.left + rect.right) / 2, (rect.top + rect.bottom) / 2

    ########################## Connect to VPN #########################

    def connect(
            self,
            service_name: str,
            service_no: int = 1,
            subnet: str = str(),
            force_connect: bool = False,
            **wait_options: float
        ) -> IpAddress:
        window = self.wait_service_ui(**wait_options)
        rows: list[list[StaticWrapper]] = list()
        ip_addr: IpAddress = str()

        try:
            cells: list[StaticWrapper] = window.descendants(control_type="Text")
            for i, cell in enumerate(cells):
                if (str(cell.window_text()).strip() == service_name) and ((i+6) < len(cells)):
                    if (not subnet) or str(cells[i+2].window_text()).strip().startswith(subnet):
                        rows.append([cells[i+col] for col in range(7)])

            service, id, name, server, status, connect_btn, end_date = rows[service_no-1]
            ip_addr = str(name.window_text()).strip()

            if (str(status.window_text()).strip() == "대기") or force_connect:
                connect_btn.click_input()
            else:
                raise VpnInUseError(f"{service_no}번째 서비스가 사용 중입니다.")
        except VpnInUseError as error:
            raise error
        except Exception:
            raise ElementNotFoundError(f"{service_no}번째 서비스가 존재하지 않습니다.")

        self.wait_for_connection(ip_addr, **wait_options)
        return ip_addr

    def disconnect(self, **wait_options: float):
        window = self.wait_for_connection(**wait_options)
        try:
            action_btn: ButtonWrapper = window.descendants(control_type="Button", title="연결끊기")[0]
            action_btn.click_input()
        except Exception:
            raise ElementNotFoundError("연결끊기 버튼이 존재하지 않습니다.")

        try:
            confirm_btn: ButtonWrapper = window.descendants(control_type="Button", title="예(Y)")[0]
            confirm_btn.click_input()
        except Exception:
            raise ElementNotFoundError("VPN 접속 해제 확인창이 존재하지 않습니다.")

    def wait_for_connection(
            self,
            ip_addr: str = str(),
            timeout: float = 30.,
            interval: float = 0.25,
            wait_after: float | None = 0.5,
            **kwargs
        ) -> UIAWrapper:
        start_time = time.perf_counter()
        error_msg = "VPN이 연결되지 않았습니다."

        window = self.wait_window_open(self.title_patterns.connected, timeout, interval, error_msg)
        if wait_after:
            time.sleep(wait_after)
        window.set_focus()

        while (time.perf_counter() - start_time) < timeout:
            if (not ip_addr) or window.descendants(title=ip_addr):
                return window
            time.sleep(interval)
        raise VpnFailedError(error_msg)

    ########################## Custom Methods #########################

    def restart_service(
            self,
            userid: str = str(),
            passwd: str = str(),
            **wait_options: float
        ) -> bool:
        self.start_process(force_restart=True)
        return self.try_login(userid, passwd, **wait_options)

    def search_and_connect(
            self,
            service_name: str,
            ip_addr: str = str(),
            subnet: str = str(),
            service_no: int = 1,
            force_connect: bool = False,
            **wait_options: float
        ) -> IpAddress:
        if ip_addr:
            self.search_ip_addr(ip_addr, **wait_options)
        try:
            return self.connect(service_name, service_no, subnet, force_connect, **wait_options)
        except VpnFailedError:
            self.disconnect(**wait_options)
            return None


###################################################################
######################## Test Client - VPN ########################
###################################################################

def test_vpn(
        exe_path: str | Path,
        process_name: str,
        title_patterns: VpnPattern | dict[str, str | re.Pattern[str]],
        service_name: str,
        userid: str = str(),
        passwd: str = str(),
        ip_addr: str = str(),
        subnet: str = str(),
        service_no: int = 1,
        force_restart: bool = False,
        force_connect: bool = False,
        disconnect: bool = True,
        logout: bool = True,
        terminate_process: bool = True,
        wait_timeout: float = 30.,
        wait_interval: float = 0.25,
        break_point: Literal["login","service","connected","disconnected","logout"] | None = None,
    ) -> UIAWrapper | None:
    client = VpnClient(exe_path, process_name, title_patterns)
    client.start_process(force_restart)

    BREAK_POINT = break_point
    wait_options: WaitOptions = dict(timeout=wait_timeout, interval=wait_interval)
    if BREAK_POINT == "login":
        return client.wait_login_form(**wait_options)

    if client.try_login(userid, passwd, **wait_options):
        if BREAK_POINT == "service":
            return client.wait_service_ui(**wait_options)

        if ip_addr:
            client.search_ip_addr(ip_addr, **wait_options)
            time.sleep(1)
        client.connect(service_name, service_no, subnet, force_connect, **wait_options)

        if BREAK_POINT == "connected":
            return client.wait_for_connection(**wait_options)

        if disconnect or terminate_process:
            client.disconnect(**wait_options)

        if BREAK_POINT == "disconnected":
            return client.wait_service_ui(**wait_options)

        if logout or terminate_process:
            client.logout(**wait_options)

        if BREAK_POINT == "logout":
            return client.wait_login_form(**wait_options)

    if terminate_process:
        client.terminate_process()
