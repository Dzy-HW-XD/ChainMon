"""
数据采集模块
负责FRU硬件信息、性能指标等数据的采集
"""
import subprocess
import json
import logging
import time
import platform
import os
import glob
import shutil
import socket
import hashlib
from typing import Dict, Any, List, Optional
import psutil

logger = logging.getLogger(__name__)


class HardwareCollector:
    """
    硬件数据采集器
    采集FRU信息、CPU、内存、磁盘、GPU、温度、功耗等
    """

    def __init__(self, ipmi_username: str = "admin", ipmi_password: str = "admin123"):
        self.ipmi_username = ipmi_username
        self.ipmi_password = ipmi_password
        self.last_fru_data: Dict[str, Any] = {}  # 上次采集的FRU数据（用于去重）
        self.last_hardware_assets: Dict[str, str] = {}

    def _read_text_file(self, path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read().strip()
        except Exception:
            return ""

    def _run_command(self, cmd: List[str], timeout: int = 5) -> str:
        if not cmd or not shutil.which(cmd[0]):
            return ""
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return ""

    def _collect_linux_memory_modules(self) -> List[Dict[str, Any]]:
        output = self._run_command(["dmidecode", "-t", "memory"], timeout=8)
        modules: List[Dict[str, Any]] = []
        current: Dict[str, Any] = {}
        if output:
            key_map = {
                "Manufacturer": "manufacturer",
                "Size": "size",
                "Locator": "locator",
                "Bank Locator": "bank",
                "Type": "type",
                "Speed": "speed",
                "Part Number": "part_number",
                "Serial Number": "serial_number",
            }
            for raw in output.splitlines():
                line = raw.strip()
                if line == "Memory Device":
                    if current and current.get("size") and current.get("size") != "No Module Installed":
                        modules.append(current)
                    current = {}
                    continue
                if ":" not in line:
                    continue
                key, value = [part.strip() for part in line.split(":", 1)]
                if key in key_map and value and value != "Not Specified":
                    current[key_map[key]] = value
            if current and current.get("size") and current.get("size") != "No Module Installed":
                modules.append(current)
        return modules

    def _collect_disk_assets(self) -> List[Dict[str, Any]]:
        disks: List[Dict[str, Any]] = []
        if platform.system().lower() == "linux":
            for path in sorted(glob.glob("/sys/block/*")):
                name = os.path.basename(path)
                if name.startswith(("loop", "ram", "fd", "sr")):
                    continue
                size_sectors = self._read_text_file(os.path.join(path, "size"))
                try:
                    size_bytes = int(size_sectors) * 512 if size_sectors else None
                except ValueError:
                    size_bytes = None
                disks.append({
                    "name": name,
                    "model": self._read_text_file(os.path.join(path, "device/model")),
                    "vendor": self._read_text_file(os.path.join(path, "device/vendor")),
                    "serial": self._read_text_file(os.path.join(path, "device/serial")),
                    "rotational": self._read_text_file(os.path.join(path, "queue/rotational")),
                    "size_bytes": size_bytes,
                })
        else:
            for part in psutil.disk_partitions():
                if part.device:
                    disks.append({"name": part.device, "mountpoint": part.mountpoint, "fstype": part.fstype})
        return disks

    def collect_local_hardware_asset(self) -> Dict[str, Any]:
        """Collect basic server inventory that the local OS can expose."""
        vm = psutil.virtual_memory()
        cpu_model = platform.processor()
        if platform.system().lower() == "linux":
            cpuinfo = self._read_text_file("/proc/cpuinfo")
            for line in cpuinfo.splitlines():
                if line.lower().startswith("model name") and ":" in line:
                    cpu_model = line.split(":", 1)[1].strip()
                    break

        system_vendor = ""
        product_name = ""
        serial_number = ""
        if platform.system().lower() == "linux":
            system_vendor = self._read_text_file("/sys/class/dmi/id/sys_vendor")
            product_name = self._read_text_file("/sys/class/dmi/id/product_name")
            serial_number = self._read_text_file("/sys/class/dmi/id/product_serial")

        return {
            "success": True,
            "source": "agent-os",
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "system": {
                "vendor": system_vendor,
                "product_name": product_name,
                "serial_number": serial_number,
                "machine": platform.machine(),
                "os": platform.system(),
                "kernel": platform.release(),
            },
            "cpu": {
                "model": cpu_model,
                "physical_cores": psutil.cpu_count(logical=False),
                "logical_cores": psutil.cpu_count(logical=True),
            },
            "memory": {
                "total_bytes": vm.total,
                "modules": self._collect_linux_memory_modules(),
            },
            "disks": self._collect_disk_assets(),
            "collect_time": int(time.time()),
        }

    def is_hardware_asset_changed(self, device_id: str, asset: Dict[str, Any]) -> bool:
        normalized = json.dumps(asset, ensure_ascii=False, sort_keys=True, default=str)
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        if self.last_hardware_assets.get(device_id) != digest:
            self.last_hardware_assets[device_id] = digest
            return True
        return False

    def collect_fru_info(self, target_ip: str, target_user: str = None, 
                         target_password: str = None) -> Dict[str, Any]:
        """
        采集指定设备的FRU硬件信息
        使用 ipmitool fru 命令
        """
        username = target_user or self.ipmi_username
        password = target_password or self.ipmi_password
        
        try:
            # 执行 ipmitool fru 命令
            cmd = [
                "ipmitool",
                "-I", "lanplus",
                "-H", target_ip,
                "-U", username,
                "-P", password,
                "fru"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                logger.error(f"采集FRU信息失败 {target_ip}: {result.stderr}")
                return {"error": result.stderr, "success": False}
            
            # 解析FRU输出
            fru_data = self._parse_fru_output(result.stdout)
            fru_data["target_ip"] = target_ip
            fru_data["collect_time"] = int(time.time())
            fru_data["success"] = True
            
            logger.info(f"FRU信息采集成功 {target_ip}: {fru_data.get('product_name', 'N/A')}")
            return fru_data
            
        except subprocess.TimeoutExpired:
            logger.error(f"采集FRU信息超时 {target_ip}")
            return {"error": "timeout", "success": False}
        except Exception as e:
            logger.error(f"采集FRU信息异常 {target_ip}: {e}")
            return {"error": str(e), "success": False}

    def _parse_fru_output(self, output: str) -> Dict[str, Any]:
        """解析 ipmitool fru 命令输出"""
        fru_data = {
            "product_name": "",
            "product_part_number": "",
            "product_serial": "",
            "product_manufacturer": "",
            "board_mfr": "",
            "board_product": "",
            "board_serial": "",
            "board_part": "",
            "chassis_part": "",
            "chassis_serial": ""
        }
        
        current_section = None
        for line in output.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            # 检测段落标题
            if "FRU Device Description" in line:
                continue
            if line.startswith("Product Manufacturer"):
                current_section = "product"
                fru_data["product_manufacturer"] = line.split(':', 1)[-1].strip()
            elif line.startswith("Product Name"):
                fru_data["product_name"] = line.split(':', 1)[-1].strip()
            elif line.startswith("Product Part Number"):
                fru_data["product_part_number"] = line.split(':', 1)[-1].strip()
            elif line.startswith("Product Serial"):
                fru_data["product_serial"] = line.split(':', 1)[-1].strip()
            elif line.startswith("Board Mfg"):
                fru_data["board_mfr"] = line.split(':', 1)[-1].strip()
            elif line.startswith("Board Product"):
                fru_data["board_product"] = line.split(':', 1)[-1].strip()
            elif line.startswith("Board Serial"):
                fru_data["board_serial"] = line.split(':', 1)[-1].strip()
            elif line.startswith("Board Part Number"):
                fru_data["board_part"] = line.split(':', 1)[-1].strip()
            elif line.startswith("Chassis Part Number"):
                fru_data["chassis_part"] = line.split(':', 1)[-1].strip()
            elif line.startswith("Chassis Serial"):
                fru_data["chassis_serial"] = line.split(':', 1)[-1].strip()
        
        return fru_data

    def is_fru_changed(self, device_ip: str, new_fru: Dict[str, Any]) -> bool:
        """
        检查FRU信息是否发生变化
        如果变化则返回True（需要重新上链）
        """
        key = f"{device_ip}_fru"
        if key not in self.last_fru_data:
            self.last_fru_data[key] = new_fru
            return True
        
        old_fru = self.last_fru_data[key]
        # 比较关键字段
        for field in ["product_serial", "board_serial", "product_part_number"]:
            if old_fru.get(field) != new_fru.get(field):
                self.last_fru_data[key] = new_fru
                return True
        
        return False

    def collect_performance_metrics(self, target_ip: str, target_user: str = None,
                                    target_password: str = None) -> Dict[str, Any]:
        """
        采集设备性能指标
        使用 ipmitool sdr 命令获取传感器数据
        """
        username = target_user or self.ipmi_username
        password = target_password or self.ipmi_password
        
        try:
            cmd = [
                "ipmitool",
                "-I", "lanplus",
                "-H", target_ip,
                "-U", username,
                "-P", password,
                "sdr"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                return {"error": result.stderr, "success": False}
            
            # 解析传感器数据
            metrics = self._parse_sdr_output(result.stdout)
            metrics["target_ip"] = target_ip
            metrics["collect_time"] = int(time.time())
            metrics["success"] = True
            
            return metrics
            
        except Exception as e:
            logger.error(f"采集性能指标异常 {target_ip}: {e}")
            return {"error": str(e), "success": False}

    def _parse_sdr_output(self, output: str) -> Dict[str, Any]:
        """解析 ipmitool sdr 命令输出（传感器数据）"""
        metrics = {
            "cpu_usage": 0,
            "memory_usage": 0,
            "disk_io": {},
            "gpu_util": 0,
            "gpu_mem": 0,
            "temperature": {},
            "power": 0,
            "fan_speed": {},
            "sensors": []
        }
        
        for line in output.split('\n'):
            line = line.strip()
            if not line or '|' not in line:
                continue
            
            parts = line.split('|')
            if len(parts) < 2:
                continue
            
            sensor_name = parts[0].strip()
            sensor_value = parts[1].strip()
            
            # 提取数值
            value_num = ""
            for c in sensor_value:
                if c.isdigit() or c == '.':
                    value_num += c
                else:
                    break
            try:
                value_float = float(value_num) if value_num else 0
            except:
                value_float = 0
            
            # 分类传感器
            sensor_lower = sensor_name.lower()
            if "temp" in sensor_lower or "thermal" in sensor_lower:
                metrics["temperature"][sensor_name] = value_float
            elif "fan" in sensor_lower:
                metrics["fan_speed"][sensor_name] = value_float
            elif "power" in sensor_lower or "psu" in sensor_lower:
                metrics["power"] = max(metrics["power"], value_float)
            elif "cpu" in sensor_lower:
                metrics["cpu_usage"] = max(metrics["cpu_usage"], value_float)
            elif "mem" in sensor_lower:
                metrics["memory_usage"] = max(metrics["memory_usage"], value_float)
            elif "gpu" in sensor_lower:
                metrics["gpu_util"] = max(metrics["gpu_util"], value_float)
            
            metrics["sensors"].append({
                "name": sensor_name,
                "value": sensor_value,
                "numeric": value_float
            })
        
        return metrics

    def collect_local_metrics(self) -> Dict[str, Any]:
        """
        采集本地机器性能指标（不需要IPMI）
        用于本地客户端所在机器的监控
        """
        metrics = {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory": {
                "total": psutil.virtual_memory().total,
                "used": psutil.virtual_memory().used,
                "percent": psutil.virtual_memory().percent
            },
            "disk": {},
            "net": {},
            "temperature": {},
            "collect_time": int(time.time())
        }
        
        # 磁盘IO
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                metrics["disk"][part.mountpoint] = {
                    "total": usage.total,
                    "used": usage.used,
                    "percent": (usage.used / usage.total * 100) if usage.total > 0 else 0
                }
            except:
                pass
        
        # 网络IO
        net_io = psutil.net_io_counters()
        metrics["net"] = {
            "bytes_sent": net_io.bytes_sent,
            "bytes_recv": net_io.bytes_recv
        }
        
        # 温度（如果可用）
        try:
            temps = psutil.sensors_temperatures()
            for name, entries in temps.items():
                for entry in entries:
                    metrics["temperature"][f"{name}_{entry.label}"] = entry.current
        except:
            pass
        
        return metrics
