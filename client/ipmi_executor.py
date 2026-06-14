"""
IPMI指令执行模块
负责接收、校验、执行IPMI指令，并记录操作日志
"""
import subprocess
import logging
import time
from typing import Dict, Any, List, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class IPMICommand:
    """IPMI指令结构体"""
    command_id: str
    target_ip: str
    ipmi_command: str       # 完整ipmitool命令（不含连接参数）
    operator: str            # 操作用户
    timestamp: int = 0
    status: str = "pending"  # pending/running/success/failed
    result: str = ""
    error: str = ""

    def __post_init__(self):
        if self.timestamp == 0:
            self.timestamp = int(time.time())


class IPMIExecutor:
    """
    IPMI指令执行器
    负责IPMI指令的校验、执行、结果记录
    """

    def __init__(self, ipmi_username: str = "admin", ipmi_password: str = "admin123",
                 whitelist: List[str] = None):
        self.ipmi_username = ipmi_username
        self.ipmi_password = ipmi_password
        self.whitelist = whitelist or ["power", "chassis", "sensor", "fru", "sel", "lan", "user"]
        self.command_history: List[IPMICommand] = []

    def is_command_allowed(self, command: str) -> Tuple[bool, str]:
        """
        检查指令是否在白名单中
        返回: (是否允许, 原因)
        """
        cmd_lower = command.lower().strip()
        
        # 检查是否包含危险命令
        dangerous_keywords = ["shell", "exec", "sh", "bash", "/bin/", "rm ", "dd "]
        for kw in dangerous_keywords:
            if kw in cmd_lower:
                return False, f"指令包含危险关键词: {kw}"
        
        # 检查是否在白名单中
        allowed = False
        for allowed_cmd in self.whitelist:
            if cmd_lower.startswith(allowed_cmd):
                allowed = True
                break
        
        if not allowed:
            return False, f"指令不在白名单中: {command[:50]}"
        
        return True, "允许执行"

    def execute_command(self, target_ip: str, ipmi_command: str, 
                       operator: str = "system") -> IPMICommand:
        """
        执行IPMI指令
        返回: IPMICommand对象（包含执行结果）
        """
        # 创建指令记录
        cmd_record = IPMICommand(
            command_id=f"cmd_{int(time.time())}_{target_ip.replace('.', '_')}",
            target_ip=target_ip,
            ipmi_command=ipmi_command,
            operator=operator
        )
        
        # 校验指令
        is_allowed, reason = self.is_command_allowed(ipmi_command)
        if not is_allowed:
            cmd_record.status = "rejected"
            cmd_record.error = reason
            logger.warning(f"IPMI指令被拒绝 {target_ip}: {reason}")
            self.command_history.append(cmd_record)
            return cmd_record
        
        # 执行指令
        cmd_record.status = "running"
        logger.info(f"执行IPMI指令 {target_ip}: {ipmi_command[:100]}")
        
        try:
            # 构建完整命令
            full_cmd = [
                "ipmitool",
                "-I", "lanplus",
                "-H", target_ip,
                "-U", self.ipmi_username,
                "-P", self.ipmi_password,
            ]
            
            # 解析ipmi_command，添加到命令末尾
            cmd_parts = ipmi_command.strip().split()
            full_cmd.extend(cmd_parts)
            
            # 执行
            result = subprocess.run(full_cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                cmd_record.status = "success"
                cmd_record.result = result.stdout[:2000]  # 限制长度
                logger.info(f"IPMI指令执行成功 {target_ip}")
            else:
                cmd_record.status = "failed"
                cmd_record.error = result.stderr[:1000]
                logger.error(f"IPMI指令执行失败 {target_ip}: {cmd_record.error}")
                
        except subprocess.TimeoutExpired:
            cmd_record.status = "failed"
            cmd_record.error = "指令执行超时"
            logger.error(f"IPMI指令执行超时 {target_ip}")
        except Exception as e:
            cmd_record.status = "failed"
            cmd_record.error = str(e)
            logger.error(f"IPMI指令执行异常 {target_ip}: {e}")
        
        self.command_history.append(cmd_record)
        return cmd_record

    def execute_raw(self, target_ip: str, raw_command: List[str], 
                    operator: str = "system") -> IPMICommand:
        """
        执行原始IPMI命令（命令已分解为列表）
        """
        ipmi_command_str = " ".join(raw_command)
        return self.execute_command(target_ip, ipmi_command_str, operator)

    def power_on(self, target_ip: str, operator: str = "system") -> IPMICommand:
        """开机"""
        return self.execute_command(target_ip, "power on", operator)

    def power_off(self, target_ip: str, operator: str = "system") -> IPMICommand:
        """关机（软关机）"""
        return self.execute_command(target_ip, "power soft", operator)

    def power_off_force(self, target_ip: str, operator: str = "system") -> IPMICommand:
        """强制关机"""
        return self.execute_command(target_ip, "power off", operator)

    def power_cycle(self, target_ip: str, operator: str = "system") -> IPMICommand:
        """重启（循环断电）"""
        return self.execute_command(target_ip, "power cycle", operator)

    def power_reset(self, target_ip: str, operator: str = "system") -> IPMICommand:
        """复位"""
        return self.execute_command(target_ip, "power reset", operator)

    def get_power_status(self, target_ip: str, operator: str = "system") -> IPMICommand:
        """获取电源状态"""
        return self.execute_command(target_ip, "power status", operator)

    def get_fru(self, target_ip: str, operator: str = "system") -> IPMICommand:
        """获取FRU信息"""
        return self.execute_command(target_ip, "fru", operator)

    def get_sensors(self, target_ip: str, operator: str = "system") -> IPMICommand:
        """获取传感器数据"""
        return self.execute_command(target_ip, "sdr", operator)

    def get_sel(self, target_ip: str, operator: str = "system") -> IPMICommand:
        """获取系统事件日志"""
        return self.execute_command(target_ip, "sel list", operator)

    def set_fan_speed(self, target_ip: str, speed_percent: int, 
                      operator: str = "system") -> IPMICommand:
        """
        设置风扇转速（百分比）
        注意：不同服务器风扇控制方式不同，此为示例
        """
        # 示例：使用 raw 命令设置风扇速度（需根据服务器型号调整）
        hex_speed = format(speed_percent * 255 // 100, '02x')
        return self.execute_command(target_ip, f"raw 0x30 0x30 0x02 0xff 0x{hex_speed}", operator)

    def get_command_history(self, target_ip: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        """获取指令执行历史"""
        history = self.command_history
        if target_ip:
            history = [c for c in history if c.target_ip == target_ip]
        
        # 返回最近的记录
        recent = history[-limit:] if limit > 0 else history
        return [self._cmd_to_dict(c) for c in reversed(recent)]

    def _cmd_to_dict(self, cmd: IPMICommand) -> Dict[str, Any]:
        """将IPMICommand转换为字典"""
        return {
            "command_id": cmd.command_id,
            "target_ip": cmd.target_ip,
            "ipmi_command": cmd.ipmi_command,
            "operator": cmd.operator,
            "timestamp": cmd.timestamp,
            "status": cmd.status,
            "result": cmd.result[:500] if cmd.result else "",
            "error": cmd.error[:500] if cmd.error else ""
        }
