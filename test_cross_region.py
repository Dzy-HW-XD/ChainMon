#!/usr/bin/env python3
"""
ChainMon cross-region test script
Test blockchain sync and monitoring logic between two machines (tc + ali)
"""

import paramiko
import time
import json
import sys
import os

# Machine configs
MACHINES = {
    "tc": {
        "host": "43.156.165.206",
        "username": "root",
        "password": "Dzy980708+",
        "port": 22,
    },
    "ali": {
        "host": "8.152.4.161",
        "username": "root",
        "password": "Dzy980708?",
        "port": 22,
    }
}

def ssh_connect(machine_config, timeout=30):
    """SSH connect to remote machine"""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=machine_config["host"],
            username=machine_config["username"],
            password=machine_config["password"],
            port=machine_config["port"],
            timeout=timeout,
            allow_agent=False,
            look_for_keys=False
        )
        print(f"  [OK] SSH connected: {machine_config['host']}")
        return client
    except Exception as e:
        print(f"  [FAIL] SSH connect failed: {machine_config['host']} - {e}")
        return None

def ssh_exec(client, command, timeout=120):
    """Execute command on remote machine, return (stdout, stderr, exit_code)"""
    try:
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        out = stdout.read().decode('utf-8', errors='replace')
        err = stderr.read().decode('utf-8', errors='replace')
        exit_code = stdout.channel.recv_exit_status()
        return out, err, exit_code
    except Exception as e:
        return "", str(e), -1

def ssh_exec_long(client, command, timeout=300):
    """Execute long-running command, with longer timeout"""
    try:
        transport = client.get_transport()
        transport.set_keepalive(30)
        channel = transport.open_session()
        channel.settimeout(timeout)
        channel.exec_command(command)
        
        out = b""
        err = b""
        while True:
            if channel.recv_ready():
                chunk = channel.recv(4096)
                if not chunk:
                    break
                out += chunk
            if channel.recv_stderr_ready():
                chunk = channel.recv_stderr(4096)
                if not chunk:
                    break
                err += chunk
            if channel.exit_status_ready():
                while channel.recv_ready():
                    out += channel.recv(4096)
                while channel.recv_stderr_ready():
                    err += channel.recv_stderr(4096)
                break
            time.sleep(0.5)
        
        exit_code = channel.recv_exit_status()
        return out.decode('utf-8', errors='replace'), err.decode('utf-8', errors='replace'), exit_code
    except Exception as e:
        return "", str(e), -1

def check_environment(client, machine_name):
    """Check machine environment"""
    print(f"\n{'='*60}")
    print(f"  Checking environment: {machine_name}")
    print(f"{'='*60}")
    
    # 1. OS version
    out, err, code = ssh_exec(client, "cat /etc/os-release | grep -E '^(NAME|VERSION)='")
    if code == 0:
        print(f"  [OS] {out.strip()}")
    else:
        print(f"  [OS] Failed: {err}")
    
    # 2. Python3 version
    out, err, code = ssh_exec(client, "python3 --version 2>&1")
    if code == 0:
        print(f"  [Python] {out.strip()}")
    else:
        print(f"  [Python] Not installed: {err}")
    
    # 3. ipmitool
    out, err, code = ssh_exec(client, "which ipmitool 2>&1; ipmitool -V 2>&1 | head -1")
    if code == 0 and "not found" not in out:
        print(f"  [ipmitool] {out.strip()}")
    else:
        print(f"  [ipmitool] Not installed (will install)")
    
    # 4. pip3
    out, err, code = ssh_exec(client, "pip3 --version 2>&1")
    if code == 0:
        print(f"  [pip3] {out.strip()}")
    else:
        print(f"  [pip3] Not installed")
    
    # 5. git
    out, err, code = ssh_exec(client, "git --version 2>&1")
    if code == 0:
        print(f"  [git] {out.strip()}")
    else:
        print(f"  [git] Not installed")

def deploy_chainmon(client, machine_name, peer_host, peer_port=8080):
    """Deploy ChainMon to remote machine"""
    print(f"\n{'='*60}")
    print(f"  Deploying ChainMon: {machine_name}")
    print(f"{'='*60}")
    
    # 1. Clone or update code
    print(f"  [1/6] Cloning/updating code...")
    cmd = """
    if [ -d ~/ChainMon ]; then
        cd ~/ChainMon && git pull origin main 2>&1
    else
        cd ~ && git clone https://github.com/Dzy-HW-XD/ChainMon.git 2>&1
    fi
    """
    out, err, code = ssh_exec(client, cmd, timeout=120)
    if code != 0 and "Already up" not in out:
        print(f"  [WARN] Git pull issues: {out[:200]}")
    print(f"  [OK] Code ready")
    
    # 2. Install system dependencies
    print(f"  [2/6] Installing system dependencies...")
    cmd = "DEBIAN_FRONTEND=noninteractive apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ipmitool python3-pip python3-venv openssh-client sqlite3 2>&1 | tail -3"
    out, err, code = ssh_exec_long(client, cmd, timeout=300)
    if code != 0:
        print(f"  [WARN] System deps may have issues: {err[:200]}")
    else:
        print(f"  [OK] System dependencies installed")
    
    # 3. Create venv and install Python dependencies
    print(f"  [3/6] Installing Python dependencies (this may take a while)...")
    # Break this into steps to avoid timeout
    cmd = "cd ~/ChainMon && python3 -m venv venv 2>&1"
    out, err, code = ssh_exec(client, cmd, timeout=60)
    if code != 0:
        print(f"  [WARN] venv creation: {err[:100]}")
    
    cmd = "cd ~/ChainMon && source venv/bin/activate && pip install --quiet --upgrade pip 2>&1 | tail -2"
    out, err, code = ssh_exec_long(client, cmd, timeout=120)
    
    cmd = "cd ~/ChainMon && source venv/bin/activate && pip install --quiet -r requirements.txt 2>&1 | tail -5"
    out, err, code = ssh_exec_long(client, cmd, timeout=300)
    if code != 0:
        print(f"  [WARN] Python deps install: {out[:200]} {err[:200]}")
    else:
        print(f"  [OK] Python dependencies installed")
    
    # 4. Create config file
    print(f"  [4/6] Creating config file...")
    out, _, _ = ssh_exec(client, "hostname -I | awk '{print $1}'")
    local_ip = out.strip().split()[0] if out.strip() else "127.0.0.1"
    
    other_name = "ali" if machine_name == "tc" else "tc"
    config_content = f"""# ChainMon config - {machine_name}
node_id: "{machine_name}"
blockchain:
  enabled: true
  pbft_timeout: 5
  block_batch_size: 10
  block_interval: 30
  min_confirm_threshold: 0.8

network:
  listen_addr: "0.0.0.0"
  listen_port: 8080
  peers:
    - node_id: "{other_name}"
      addr: "{peer_host}"
      port: {peer_port}

client:
  collect_interval: 30
  scan_network: "{local_ip}/24"
  ipmi:
    interface: "lanplus"
    username: "admin"
    password: "admin123"

web:
  enabled: true
  listen_addr: "0.0.0.0"
  listen_port: 5000

logging:
  level: "INFO"
  file: "logs/chainmon.log"
"""
    # Write config
    cmd = f"""python3 -c "
import os
os.makedirs(os.path.expanduser('~/ChainMon/config'), exist_ok=True)
with open(os.path.expanduser('~/ChainMon/config/node_config.yaml'), 'w') as f:
    f.write('''{config_content}''')
print('Config written')
" """
    out, err, code = ssh_exec(client, cmd)
    if code != 0:
        print(f"  [FAIL] Config creation failed: {err}")
        return False
    print(f"  [OK] Config created (node_id={machine_name}, local_ip={local_ip})")
    
    # 5. Create directories
    ssh_exec(client, "mkdir -p ~/ChainMon/logs ~/ChainMon/data")
    
    # 6. Verify deployment
    print(f"  [5/6] Verifying deployment...")
    cmd = "cd ~/ChainMon && source venv/bin/activate && python3 -c 'from blockchain.block import Block; print(\"Import OK\")' 2>&1"
    out, err, code = ssh_exec(client, cmd, timeout=30)
    if code != 0:
        print(f"  [FAIL] Deployment verification failed: {err[:300]}")
        return False
    print(f"  [OK] Deployment verified")
    
    print(f"\n  [PASS] {machine_name} deployed successfully!")
    return True

def start_chainmon(client, machine_name):
    """Start ChainMon node"""
    print(f"\n{'='*60}")
    print(f"  Starting ChainMon: {machine_name}")
    print(f"{'='*60}")
    
    # Stop existing process
    cmd = "pkill -f 'python3 monitor_client.py' 2>/dev/null; sleep 2; echo 'Stopped'"
    ssh_exec(client, cmd)
    
    # Start new process (background)
    cmd = """cd ~/ChainMon && source venv/bin/activate && nohup python3 monitor_client.py > logs/stdout.log 2>&1 &
echo "PID=$!"
"""
    out, err, code = ssh_exec(client, cmd, timeout=10)
    
    # Wait for startup
    print(f"  Waiting for service to start (15s)...")
    time.sleep(15)
    
    # Check if process is running
    cmd = "ps aux | grep 'python3 monitor_client.py' | grep -v grep"
    out, err, code = ssh_exec(client, cmd)
    if code != 0 or not out.strip():
        print(f"  [FAIL] Process not running! Checking logs...")
        cmd = "tail -30 ~/ChainMon/logs/stdout.log 2>/dev/null"
        out, err, code = ssh_exec(client, cmd)
        print(f"  LOG: {out[:500]}")
        cmd = "tail -30 ~/ChainMon/logs/chainmon.log 2>/dev/null"
        out, err, code = ssh_exec(client, cmd)
        print(f"  LOG2: {out[:500]}")
        return False
    
    print(f"  [OK] Process running: {out.strip()[:100]}")
    return True

def test_blockchain_sync(client_tc, client_ali):
    """Test blockchain sync between two nodes"""
    print(f"\n{'='*60}")
    print(f"  Test: Blockchain Sync")
    print(f"{'='*60}")
    
    # 1. Check P2P health
    print(f"\n  [1/5] Checking P2P health endpoints...")
    for name, client in [("TC", client_tc), ("ALI", client_ali)]:
        cmd = "curl -s -m 5 http://localhost:8080/health 2>&1"
        out, _, code = ssh_exec(client, cmd, timeout=10)
        print(f"  {name} P2P health: {out[:150]}")
    
    # 2. Check chain status
    print(f"\n  [2/5] Checking chain status...")
    for name, client in [("TC", client_tc), ("ALI", client_ali)]:
        cmd = "curl -s -m 5 http://localhost:8080/p2p/chain/sync 2>&1"
        out, _, code = ssh_exec(client, cmd, timeout=10)
        print(f"  {name} chain: {out[:200]}")
    
    # 3. Check node heartbeat
    print(f"\n  [3/5] Checking heartbeat...")
    for name, client in [("TC", client_tc), ("ALI", client_ali)]:
        cmd = "curl -s -m 5 http://localhost:8080/p2p/heartbeat 2>&1"
        out, _, code = ssh_exec(client, cmd, timeout=10)
        print(f"  {name} heartbeat: {out[:150]}")
    
    # 4. Wait for block creation
    print(f"\n  [4/5] Waiting for block creation (35s)...")
    time.sleep(35)
    
    # 5. Check sync result
    print(f"\n  [5/5] Checking sync result...")
    results = {}
    for name, client in [("TC", client_tc), ("ALI", client_ali)]:
        cmd = "curl -s -m 5 http://localhost:8080/p2p/chain/sync 2>&1"
        out, _, code = ssh_exec(client, cmd, timeout=10)
        print(f"  {name} chain(after): {out[:200]}")
        try:
            data = json.loads(out)
            results[name] = data
        except:
            print(f"  Cannot parse JSON for {name}")
    
    # Compare chain heights
    tc_height = results.get("TC", {}).get("chain_height", "N/A")
    ali_height = results.get("ALI", {}).get("chain_height", "N/A")
    print(f"\n  Chain height comparison:")
    print(f"      TC:  {tc_height}")
    print(f"      ALI: {ali_height}")
    
    if isinstance(tc_height, int) and isinstance(ali_height, int):
        if tc_height == ali_height:
            print(f"  [PASS] Chain sync OK! Heights match: {tc_height}")
            return True
        elif abs(tc_height - ali_height) <= 1:
            print(f"  [WARN] Heights differ by 1, likely sync delay")
            return True
        else:
            print(f"  [WARN] Heights differ significantly")
            return False
    else:
        print(f"  [WARN] Cannot compare heights")
        return False

def test_web_dashboard(client_tc, client_ali):
    """Test Web management dashboard"""
    print(f"\n{'='*60}")
    print(f"  Test: Web Dashboard")
    print(f"{'='*60}")
    
    for name, client in [("TC", client_tc), ("ALI", client_ali)]:
        print(f"\n  Checking {name} Web dashboard (port 5000)...")
        cmd = "curl -s -m 5 http://localhost:5000/ -o /dev/null -w '%{http_code}' 2>&1"
        out, _, code = ssh_exec(client, cmd, timeout=10)
        print(f"  {name} HTTP status: {out}")
        
        cmd = "curl -s -m 5 http://localhost:5000/api/status 2>&1"
        out, _, code = ssh_exec(client, cmd, timeout=10)
        print(f"  {name} API /status: {out[:200]}")

def test_data_collection(client, machine_name):
    """Test data collection functionality"""
    print(f"\n  Testing data collection on {machine_name}...")
    cmd = """cd ~/ChainMon && source venv/bin/activate && python3 -c "
from client.collector import HardwareCollector
c = HardwareCollector()
# Test local metrics collection (no ipmitool dependency)
import json
metrics = c.collect_local_metrics()
print('Local metrics: ' + json.dumps(metrics, indent=2)[:300])
" 2>&1"""
    out, err, code = ssh_exec(client, cmd, timeout=30)
    if code == 0:
        print(f"  [OK] Data collection works: {out[:300]}")
    else:
        print(f"  [FAIL] Data collection failed: {err[:200]}")

def check_logs(client, machine_name):
    """Check node logs"""
    print(f"\n{'='*60}")
    print(f"  Logs: {machine_name}")
    print(f"{'='*60}")
    
    # Check stdout log
    cmd = "tail -40 ~/ChainMon/logs/stdout.log 2>/dev/null"
    out, _, _ = ssh_exec(client, cmd)
    if out.strip():
        lines = out.strip().split('\n')
        print(f"  stdout.log (last 40 lines):")
        for line in lines:
            print(f"  {line}")
    else:
        print(f"  stdout.log is empty")
    
    # Check chainmon log
    cmd = "tail -40 ~/ChainMon/logs/chainmon.log 2>/dev/null"
    out, _, _ = ssh_exec(client, cmd)
    if out.strip():
        lines = out.strip().split('\n')
        print(f"  chainmon.log (last 40 lines):")
        for line in lines:
            print(f"  {line}")

def main():
    """Main test flow"""
    print("=" * 60)
    print("  ChainMon Cross-Region Test")
    print("  Machines: tc (43.156.165.206) + ali (8.152.4.161)")
    print("=" * 60)
    
    # Step 1: SSH connect
    print("\n[Step 1/8] SSH connecting to both machines...")
    client_tc = ssh_connect(MACHINES["tc"])
    client_ali = ssh_connect(MACHINES["ali"])
    
    if not client_tc or not client_ali:
        print("\n[FAIL] SSH connection failed, test aborted")
        return 1
    
    # Step 2: Check environment
    print("\n[Step 2/8] Checking environment on both machines...")
    check_environment(client_tc, "tc")
    check_environment(client_ali, "ali")
    
    # Step 3: Deploy ChainMon
    print("\n[Step 3/8] Deploying ChainMon to both machines...")
    if not deploy_chainmon(client_tc, "tc", MACHINES["ali"]["host"]):
        print("\n[FAIL] TC deployment failed, test aborted")
        check_logs(client_tc, "tc")
        return 1
    
    if not deploy_chainmon(client_ali, "ali", MACHINES["tc"]["host"]):
        print("\n[FAIL] ALI deployment failed, test aborted")
        check_logs(client_ali, "ali")
        return 1
    
    # Step 4: Test data collection before starting
    print("\n[Step 4/8] Testing data collection...")
    test_data_collection(client_tc, "tc")
    test_data_collection(client_ali, "ali")
    
    # Step 5: Start ChainMon
    print("\n[Step 5/8] Starting ChainMon nodes...")
    if not start_chainmon(client_tc, "tc"):
        print("\n[FAIL] TC start failed")
        check_logs(client_tc, "tc")
        return 1
    
    if not start_chainmon(client_ali, "ali"):
        print("\n[FAIL] ALI start failed")
        check_logs(client_ali, "ali")
        return 1
    
    # Step 6: Test blockchain sync
    print("\n[Step 6/8] Testing blockchain sync...")
    sync_ok = test_blockchain_sync(client_tc, client_ali)
    
    # Step 7: Test Web dashboard
    print("\n[Step 7/8] Testing Web dashboard...")
    test_web_dashboard(client_tc, client_ali)
    
    # Step 8: Check logs
    print("\n[Step 8/8] Checking logs...")
    check_logs(client_tc, "tc")
    check_logs(client_ali, "ali")
    
    # Summary
    print("\n" + "=" * 60)
    print("  TEST SUMMARY")
    print("=" * 60)
    print(f"  Blockchain sync: {'PASS' if sync_ok else 'NEEDS ATTENTION'}")
    print(f"  Web dashboard TC: http://43.156.165.206:5000")
    print(f"  Web dashboard ALI: http://8.152.4.161:5000")
    print("=" * 60)
    
    # Close connections
    client_tc.close()
    client_ali.close()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
