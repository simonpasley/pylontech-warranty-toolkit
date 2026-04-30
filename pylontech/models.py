"""Data models for Pylontech battery information."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CellData:
    """Individual cell voltage and temperature data."""
    cell_number: int = 0
    voltage: float = 0.0       # Volts
    temperature: float = 0.0   # Celsius

    def to_dict(self):
        return {
            'cell_number': self.cell_number,
            'voltage': round(self.voltage, 3),
            'temperature': round(self.temperature, 1),
        }


@dataclass
class AlarmStatus:
    """Battery alarm and error status."""
    # Cell voltage alarms (per cell): 0=normal, 1=below low, 2=above high, 0xF0=other
    cell_voltage_alarms: list = field(default_factory=list)
    # Temperature alarms (per sensor)
    temp_alarms: list = field(default_factory=list)
    # Pack level alarms
    charge_current_alarm: int = 0      # 0=normal, 1=below low, 2=above high
    discharge_current_alarm: int = 0
    pack_voltage_alarm: int = 0
    # System error bitmask
    error_code: int = 0

    # Error code bit definitions
    ERROR_BITS = {
        0: 'Input Overvoltage',
        1: 'Input Reverse Voltage',
        2: 'Voltage Sensor Fault',
        3: 'Temperature Sensor Fault',
        4: 'Communication Error',
        5: 'Address Error',
        6: 'BMIC Error',
        7: 'Charge MOS Failure',
        8: 'Discharge MOS Failure',
        9: 'I2C Error',
    }

    @property
    def active_errors(self) -> list:
        errors = []
        for bit, name in self.ERROR_BITS.items():
            if self.error_code & (1 << bit):
                errors.append(name)
        return errors

    @property
    def has_alarms(self) -> bool:
        if any(a != 0 for a in self.cell_voltage_alarms):
            return True
        if any(a != 0 for a in self.temp_alarms):
            return True
        if self.charge_current_alarm or self.discharge_current_alarm:
            return True
        if self.pack_voltage_alarm:
            return True
        if self.error_code:
            return True
        return False

    def to_dict(self):
        return {
            'cell_voltage_alarms': self.cell_voltage_alarms,
            'temp_alarms': self.temp_alarms,
            'charge_current_alarm': self.charge_current_alarm,
            'discharge_current_alarm': self.discharge_current_alarm,
            'pack_voltage_alarm': self.pack_voltage_alarm,
            'error_code': self.error_code,
            'active_errors': self.active_errors,
            'has_alarms': self.has_alarms,
        }


@dataclass
class ProtectionParams:
    """BMS protection parameter thresholds."""
    pack_overvoltage: float = 0.0          # V - pack over voltage protection
    pack_undervoltage: float = 0.0         # V - pack under voltage protection
    cell_overvoltage: float = 0.0          # V - cell over voltage protection
    cell_undervoltage: float = 0.0         # V - cell under voltage protection
    charge_overcurrent: float = 0.0        # A - charge over current protection
    discharge_overcurrent: float = 0.0     # A - discharge over current protection
    charge_overtemp: float = 0.0           # C - charge over temperature
    charge_undertemp: float = 0.0          # C - charge under temperature
    discharge_overtemp: float = 0.0        # C - discharge over temperature
    discharge_undertemp: float = 0.0       # C - discharge under temperature

    def to_dict(self):
        return {
            'pack_overvoltage': round(self.pack_overvoltage, 2),
            'pack_undervoltage': round(self.pack_undervoltage, 2),
            'cell_overvoltage': round(self.cell_overvoltage, 3),
            'cell_undervoltage': round(self.cell_undervoltage, 3),
            'charge_overcurrent': round(self.charge_overcurrent, 1),
            'discharge_overcurrent': round(self.discharge_overcurrent, 1),
            'charge_overtemp': round(self.charge_overtemp, 1),
            'charge_undertemp': round(self.charge_undertemp, 1),
            'discharge_overtemp': round(self.discharge_overtemp, 1),
            'discharge_undertemp': round(self.discharge_undertemp, 1),
        }


@dataclass
class DeviceInfo:
    """Device identification and firmware information."""
    address: int = 0
    manufacturer: str = ''
    device_name: str = ''
    board_version: str = ''
    main_soft_version: str = ''
    soft_version: str = ''
    boot_version: str = ''
    comm_version: str = ''
    release_date: str = ''
    barcode: str = ''
    specification: str = ''
    cell_number: int = 0
    max_discharge_current: float = 0.0
    max_charge_current: float = 0.0
    serial_number: str = ''

    def to_dict(self):
        return {
            'address': self.address,
            'manufacturer': self.manufacturer,
            'device_name': self.device_name,
            'board_version': self.board_version,
            'main_soft_version': self.main_soft_version,
            'soft_version': self.soft_version,
            'boot_version': self.boot_version,
            'comm_version': self.comm_version,
            'release_date': self.release_date,
            'barcode': self.barcode,
            'specification': self.specification,
            'cell_number': self.cell_number,
            'max_discharge_current': self.max_discharge_current,
            'max_charge_current': self.max_charge_current,
            'serial_number': self.serial_number,
        }


@dataclass
class BatteryPack:
    """Complete battery pack status."""
    address: int = 0
    voltage: float = 0.0          # V - total pack voltage
    current: float = 0.0          # A - pack current (positive=charge, negative=discharge)
    temperature: float = 0.0      # C - average temperature
    soc: float = 0.0              # % - state of charge
    soh: float = 0.0              # % - state of health
    cycle_count: int = 0
    remaining_capacity: float = 0.0   # Ah
    total_capacity: float = 0.0       # Ah
    cells: list = field(default_factory=list)   # list of CellData
    state: str = 'Unknown'        # Idle, Charging, Discharging
    charge_fet: bool = True       # charge MOSFET state
    discharge_fet: bool = True    # discharge MOSFET state
    alarm: Optional[AlarmStatus] = None
    device_info: Optional[DeviceInfo] = None
    params: Optional[ProtectionParams] = None
    # Management info
    charge_voltage_limit: float = 0.0   # V
    discharge_voltage_limit: float = 0.0  # V
    charge_current_limit: float = 0.0   # A
    discharge_current_limit: float = 0.0  # A
    online: bool = False

    @property
    def min_cell_voltage(self) -> float:
        if not self.cells:
            return 0.0
        return min(c.voltage for c in self.cells)

    @property
    def max_cell_voltage(self) -> float:
        if not self.cells:
            return 0.0
        return max(c.voltage for c in self.cells)

    @property
    def cell_voltage_diff(self) -> float:
        if not self.cells:
            return 0.0
        return self.max_cell_voltage - self.min_cell_voltage

    def to_dict(self):
        result = {
            'address': self.address,
            'voltage': round(self.voltage, 2),
            'current': round(self.current, 2),
            'temperature': round(self.temperature, 1),
            'soc': round(self.soc, 1),
            'soh': round(self.soh, 1),
            'cycle_count': self.cycle_count,
            'remaining_capacity': round(self.remaining_capacity, 2),
            'total_capacity': round(self.total_capacity, 2),
            'cells': [c.to_dict() for c in self.cells],
            'state': self.state,
            'charge_fet': self.charge_fet,
            'discharge_fet': self.discharge_fet,
            'min_cell_voltage': round(self.min_cell_voltage, 3),
            'max_cell_voltage': round(self.max_cell_voltage, 3),
            'cell_voltage_diff': round(self.cell_voltage_diff, 3),
            'charge_voltage_limit': round(self.charge_voltage_limit, 2),
            'discharge_voltage_limit': round(self.discharge_voltage_limit, 2),
            'charge_current_limit': round(self.charge_current_limit, 1),
            'discharge_current_limit': round(self.discharge_current_limit, 1),
            'online': self.online,
        }
        if self.alarm:
            result['alarm'] = self.alarm.to_dict()
        if self.device_info:
            result['device_info'] = self.device_info.to_dict()
        if self.params:
            result['params'] = self.params.to_dict()
        return result
