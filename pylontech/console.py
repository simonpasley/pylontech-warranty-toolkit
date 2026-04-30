"""Console CLI mode for Pylontech batteries.

Pylontech batteries support a text-based console interface at 115200 baud.
Commands are sent as plain ASCII text and responses are tabular text.

Common commands:
    pwr     - Power status overview
    bat     - Detailed battery info (cell voltages, temps)
    soh     - State of health
    stat    - Status information
    info    - Device info (model, serial, firmware)
    unit    - Unit configuration
    log     - Event log
    alarm   - Active alarms
    time    - RTC time
    ctrl    - Control commands (FET, buzzer, heater)
    config  - Read/write BMS protection parameters
"""

import logging
import re
from typing import Optional

from .models import (
    AlarmStatus, BatteryPack, CellData, DeviceInfo,
    ProtectionParams,
)

logger = logging.getLogger(__name__)


def _parse_table(text: str) -> list[dict]:
    """Parse tabular console output into a list of dicts.

    Pylontech console outputs data in space-aligned columns with headers.
    """
    lines = text.strip().split('\n')
    if len(lines) < 2:
        return []

    # Find the header line (contains column names)
    header_line = None
    data_start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith(('Command', 'pylon', '@@', '>', '$')):
            # Check if this looks like a header (contains known column names)
            if any(col in stripped.upper() for col in ['VOLT', 'CURR', 'TEMP', 'SOC', 'SOH', 'POWER']):
                header_line = stripped
                data_start = i + 1
                break
            # Or if the next line looks like a separator or data
            if i + 1 < len(lines) and lines[i + 1].strip().startswith(('-', '=')):
                header_line = stripped
                data_start = i + 2
                break

    if not header_line:
        return []

    # Parse column positions from header
    headers = header_line.split()

    results = []
    for line in lines[data_start:]:
        stripped = line.strip()
        if not stripped or stripped.startswith(('Command', 'pylon', '@@', '>', '$', '-', '=')):
            continue
        values = stripped.split()
        if len(values) >= len(headers):
            row = {}
            for j, header in enumerate(headers):
                row[header.upper()] = values[j] if j < len(values) else ''
            results.append(row)

    return results


def _safe_float(value: str, default: float = 0.0) -> float:
    """Safely convert string to float."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _safe_int(value: str, default: int = 0) -> int:
    """Safely convert string to int."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


class PylonConsole:
    """High-level console command interface for Pylontech batteries."""

    def __init__(self, connection):
        """
        Args:
            connection: ConnectionManager instance
        """
        self.conn = connection

    def _send(self, command: str, timeout: float = 3.0) -> str:
        """Send a console command and return the raw response text."""
        response = self.conn.send_command(command, timeout=timeout)
        logger.debug(f'Console [{command}]: {response[:200]}...' if len(response) > 200 else f'Console [{command}]: {response}')
        return response

    def get_power_status(self) -> list[BatteryPack]:
        """Get power status overview (pwr command).

        Returns list of BatteryPack objects, one per pack detected.
        """
        response = self._send('pwr')
        rows = _parse_table(response)
        packs = []

        for row in rows:
            pack = BatteryPack()
            pack.online = True

            # Parse pack number/address
            pack_num = row.get('POWER', row.get('PACK', row.get('#', '')))
            pack.address = _safe_int(pack_num, len(packs) + 1)

            # Voltage (may be in mV from console)
            volt_str = row.get('VOLT', row.get('VOLTAGE', '0'))
            volt = _safe_float(volt_str)
            pack.voltage = volt / 1000.0 if volt > 100 else volt  # Auto-detect mV vs V

            # Current
            curr_str = row.get('CURR', row.get('CURRENT', '0'))
            curr = _safe_float(curr_str)
            pack.current = curr / 1000.0 if abs(curr) > 100 else curr

            # Temperature
            temp_str = row.get('TEMPR', row.get('TEMP', row.get('TEMPERATURE', '0')))
            temp = _safe_float(temp_str)
            pack.temperature = temp / 1000.0 if temp > 200 else temp

            # SOC
            soc_str = row.get('CAPA(%)', row.get('SOC', row.get('CAPA', '0')))
            soc_str = soc_str.replace('%', '')
            pack.soc = _safe_float(soc_str)

            # Cycle count
            cycle_str = row.get('CYCLE', '0')
            pack.cycle_count = _safe_int(cycle_str)

            # State from basic state field
            state = row.get('BASICSTATE', row.get('STATE', ''))
            if 'Charg' in state or 'CHG' in state.upper():
                pack.state = 'Charging'
            elif 'Discharg' in state or 'DSG' in state.upper():
                pack.state = 'Discharging'
            elif 'Idle' in state:
                pack.state = 'Idle'
            else:
                if pack.current > 0.1:
                    pack.state = 'Charging'
                elif pack.current < -0.1:
                    pack.state = 'Discharging'
                else:
                    pack.state = 'Idle'

            packs.append(pack)

        return packs

    def get_battery_detail(self, pack_num: int = 1) -> Optional[BatteryPack]:
        """Get detailed battery info including cell voltages (bat command).

        Args:
            pack_num: Battery pack number (1-based)
        """
        response = self._send(f'bat {pack_num}' if pack_num > 0 else 'bat')
        if not response:
            return None

        pack = BatteryPack(address=pack_num, online=True)

        # Parse cell voltages from the response
        # Console typically shows: Cell01  Cell02  Cell03 ... headers
        # Then voltage values in mV
        lines = response.strip().split('\n')

        for line in lines:
            stripped = line.strip()

            # Look for cell voltage data lines
            # Format varies but typically has cell voltages in mV
            cell_match = re.findall(r'(\d{3,4})\s', stripped)
            if cell_match and len(cell_match) >= 8:  # At least 8 values suggests cell data
                for i, mv_str in enumerate(cell_match):
                    mv = _safe_int(mv_str)
                    if 2000 <= mv <= 4500:  # Valid LiFePO4 cell voltage range (mV)
                        cell = CellData(cell_number=i + 1, voltage=mv / 1000.0)
                        pack.cells.append(cell)

            # Look for voltage line
            if 'volt' in stripped.lower() and ':' in stripped:
                parts = stripped.split(':')
                if len(parts) >= 2:
                    val = _safe_float(parts[1].strip().split()[0])
                    if val > 0:
                        pack.voltage = val / 1000.0 if val > 100 else val

            # Look for current line
            if 'curr' in stripped.lower() and ':' in stripped:
                parts = stripped.split(':')
                if len(parts) >= 2:
                    val = _safe_float(parts[1].strip().split()[0])
                    if val != 0:
                        pack.current = val / 1000.0 if abs(val) > 100 else val

            # Look for temperature
            if 'temp' in stripped.lower() and ':' in stripped:
                parts = stripped.split(':')
                if len(parts) >= 2:
                    val = _safe_float(parts[1].strip().split()[0])
                    if val > 0:
                        pack.temperature = val / 1000.0 if val > 200 else val

        # Also try tabular parsing
        rows = _parse_table(response)
        if rows and not pack.cells:
            for row in rows:
                for key, value in row.items():
                    if key.startswith('CELL') or key.startswith('V'):
                        mv = _safe_int(value)
                        if 2000 <= mv <= 4500:
                            cell_num = len(pack.cells) + 1
                            cell = CellData(cell_number=cell_num, voltage=mv / 1000.0)
                            pack.cells.append(cell)

        return pack

    def get_soh(self) -> list[dict]:
        """Get state of health information (soh command)."""
        response = self._send('soh')
        rows = _parse_table(response)

        results = []
        for row in rows:
            pack_num = row.get('POWER', row.get('#', row.get('PACK', '')))
            soh_str = row.get('SOH', row.get('SOH(%)', ''))
            soh_str = soh_str.replace('%', '')
            results.append({
                'pack': _safe_int(pack_num),
                'soh': _safe_float(soh_str),
            })
        return results

    def get_stat(self) -> str:
        """Get status information (stat command). Returns raw text."""
        return self._send('stat')

    def get_info(self) -> Optional[DeviceInfo]:
        """Get device info: model, serial, firmware (info command)."""
        response = self._send('info')
        if not response:
            return None

        device = DeviceInfo()
        lines = response.strip().split('\n')

        for line in lines:
            stripped = line.strip()
            if ':' not in stripped:
                continue

            key, _, value = stripped.partition(':')
            key = key.strip().lower()
            value = value.strip()

            if 'device name' in key or 'model' in key:
                device.device_name = value
            elif 'manufacturer' in key or 'brand' in key:
                device.manufacturer = value
            elif 'board' in key and 'version' in key:
                device.board_version = value
            elif 'main' in key and ('soft' in key or 'version' in key):
                device.main_soft_version = value
            elif 'soft' in key and 'version' in key:
                device.soft_version = value
            elif 'boot' in key and 'version' in key:
                device.boot_version = value
            elif 'comm' in key and 'version' in key:
                device.comm_version = value
            elif 'release' in key or 'date' in key:
                device.release_date = value
            elif 'barcode' in key:
                device.barcode = value
            elif 'serial' in key:
                device.serial_number = value
            elif 'specification' in key or 'spec' in key:
                device.specification = value
            elif 'cell' in key and ('number' in key or 'count' in key):
                device.cell_number = _safe_int(value)
            elif 'address' in key:
                device.address = _safe_int(value)

        return device

    def get_alarms(self) -> str:
        """Get active alarms (alarm command). Returns raw text."""
        return self._send('alarm')

    def get_time(self) -> str:
        """Get battery RTC time (time command)."""
        return self._send('time')

    def get_log(self, count: int = 10) -> str:
        """Get event log entries (log command)."""
        return self._send(f'log {count}', timeout=5.0)

    def dump_event_log(self, max_pages: int = 400, page_timeout: float = 3.5,
                        max_seconds: float = 300.0,
                        progress_cb=None) -> str:
        """Page through the full `log` command output and return concatenated text.

        Pylontech's `log` returns events in pages with a "press any key /
        Enter to continue" prompt at the bottom. Different firmwares phrase
        this differently (`Press [Enter] to be continued`, `Press any key
        to continue`, `--More--`, etc.) so we match a forgiving regex.

        Note: `log` is local to the pack the cable is physically connected to.
        To dump a slave pack's log, connect directly to that pack's console
        port — the master's comm bus does not relay this command.

        progress_cb(current, total) is called after each page; total is None
        because the total page count is not known in advance.
        """
        import time as _time
        # Forgiving prompt detector — handles "Press [Enter]", "Press any
        # key", "press SPACE", "--More--", etc. without taking the literal
        # bracket characters as required.
        prompt_re = re.compile(r'(press[^\n]*?(?:continue|continued|key|enter)|--more--)',
                               re.IGNORECASE)

        start = _time.monotonic()
        stop_reason = 'end-of-log (no more-prompt)'
        pages_text = [self._send('log', timeout=page_timeout)]
        pages = 1
        if progress_cb:
            progress_cb(pages, None)

        while pages < max_pages and prompt_re.search(pages_text[-1]):
            if (_time.monotonic() - start) > max_seconds:
                stop_reason = f'wall-clock timeout ({max_seconds:.0f} s)'
                break
            if not self.conn.send(b'\r'):
                stop_reason = 'serial write failed'
                break
            chunk = self.conn.receive(size=16384, timeout=page_timeout)
            tail = self.conn.receive(size=16384, timeout=0.3)
            chunk += tail
            text = chunk.decode('utf-8', errors='replace')
            if not text.strip():
                stop_reason = 'empty page (likely end of log)'
                break
            pages_text.append(text)
            pages += 1
            if progress_cb:
                progress_cb(pages, None)

        if pages >= max_pages:
            stop_reason = f'page-count cap ({max_pages})'
            logger.warning(f'dump_event_log hit max_pages limit ({max_pages}) — output may be truncated')

        elapsed = _time.monotonic() - start
        footer = (
            f"\n# === dump_event_log finished ===\n"
            f"# pages: {pages}\n"
            f"# elapsed: {elapsed:.1f} s\n"
            f"# stop reason: {stop_reason}\n"
        )
        return ''.join(pages_text) + footer

    def dump_data_event_history(self, max_items: int = 500, timeout: float = 4.0,
                                 progress_cb=None) -> str:
        """Walk the entire `data event` history by index.

        `data event` with no argument returns the latest event and shows its
        index. We then call `data event <i>` for each i down to 0 to capture
        the full history. Returns concatenated text with separators.
        """
        out = []
        latest = self._send('data event', timeout=timeout)
        out.append(latest)

        # Find the highest index from the latest entry
        import re
        m = re.search(r'Item Index\s*:\s*(\d+)', latest)
        if not m:
            return ''.join(out)
        max_idx = int(m.group(1))
        max_idx = min(max_idx, max_items)

        total = max_idx + 1
        if progress_cb:
            progress_cb(1, total)

        captured = 1
        for i in range(max_idx - 1, -1, -1):
            text = self._send(f'data event {i}', timeout=timeout)
            out.append(f"\n# === Item {i} ===\n")
            out.append(text)
            captured += 1
            if progress_cb:
                progress_cb(captured, total)

        return ''.join(out)

    def get_unit(self) -> str:
        """Get unit configuration (unit command)."""
        return self._send('unit')

    def control_charge_fet(self, on: bool) -> str:
        """Control charge MOSFET. Returns response text."""
        state = 'on' if on else 'off'
        return self._send(f'ctrl cfet {state}')

    def control_discharge_fet(self, on: bool) -> str:
        """Control discharge MOSFET. Returns response text."""
        state = 'on' if on else 'off'
        return self._send(f'ctrl dfet {state}')

    def control_buzzer(self, on: bool) -> str:
        """Control buzzer. Returns response text."""
        state = 'on' if on else 'off'
        return self._send(f'ctrl buzz {state}')

    def control_heater(self, on: bool) -> str:
        """Control heater. Returns response text."""
        state = 'on' if on else 'off'
        return self._send(f'ctrl heat {state}')

    def read_config(self, param: str) -> str:
        """Read a BMS configuration parameter.

        Args:
            param: Parameter name (e.g. 'pov' for pack overvoltage)
        """
        return self._send(f'config {param}')

    def write_config(self, param: str, value: str) -> str:
        """Write a BMS configuration parameter.

        Args:
            param: Parameter name
            value: New value
        """
        return self._send(f'config {param} {value}')

    def get_protection_params(self) -> ProtectionParams:
        """Read all BMS protection parameters via config commands."""
        params = ProtectionParams()

        # Map of config param names to ProtectionParams attributes
        # Command names from official BatteryView US3000C_ParameterConfig.xml:
        #   pov/puv = pack over/under voltage (Accuracy=1000, mV)
        #   bov/buv = cell (battery) over/under voltage (Accuracy=1000, mV)
        #   coc/doc = charge/discharge over current (Accuracy=1000, mA)
        #   bot/but = cell over/under temperature (Accuracy=1000, m°C)
        #   bht/blt = cell high/low temp warning (Accuracy=1000, m°C)
        config_map = {
            'pov': ('pack_overvoltage', 1000.0),      # mV to V
            'puv': ('pack_undervoltage', 1000.0),
            'bov': ('cell_overvoltage', 1000.0),
            'buv': ('cell_undervoltage', 1000.0),
            'coc': ('charge_overcurrent', 1000.0),     # mA to A
            'doc': ('discharge_overcurrent', 1000.0),
            'bot': ('charge_overtemp', 1000.0),         # m°C to °C
            'but': ('charge_undertemp', 1000.0),
            'bht': ('discharge_overtemp', 1000.0),      # HT warning threshold
            'blt': ('discharge_undertemp', 1000.0),     # LT warning threshold
        }

        for config_name, (attr_name, divisor) in config_map.items():
            response = self._send(f'config {config_name}')
            # Parse the value from response
            match = re.search(r'(\d+\.?\d*)', response)
            if match:
                value = _safe_float(match.group(1))
                setattr(params, attr_name, value / divisor if divisor != 1.0 else value)

        return params
