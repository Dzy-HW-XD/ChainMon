#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
区块链核心逻辑单元测试
验证区块创建、哈希计算、链式校验等核心功能
"""
import sys
import os
import json
import time

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from blockchain.block import Block, ChainData, ChainDataType, create_genesis_block
from blockchain.chain import Blockchain
from blockchain.consensus import SimpleConsensus


def test_block_creation():
    """测试区块创建"""
    print("\n=== 测试区块创建 ===")
    
    # 创建创世区块
    genesis = create_genesis_block("test-node")
    print(f"创世区块高度: {genesis.block_height}")
    print(f"创世区块哈希: {genesis.current_hash}")
    print(f"前一区块哈希: {genesis.prev_block_hash}")
    
    assert genesis.block_height == 0
    assert genesis.prev_block_hash == "0" * 64
    assert genesis.current_hash != ""
    assert genesis.validate_hash()
    print("✓ 区块创建测试通过")


def test_chain_data():
    """测试链上数据结构"""
    print("\n=== 测试链上数据结构 ===")
    
    # 创建FRU数据
    fru_data = ChainData(
        data_type=int(ChainDataType.FRU_HARDWARE),
        device_ip="10.0.1.100",
        content=json.dumps({"product_name": "PowerEdge R740", "serial": "ABC123"}),
        operate_user="system"
    )
    print(f"FRU数据类型: {fru_data.data_type}")
    print(f"设备IP: {fru_data.device_ip}")
    
    # 创建性能数据
    perf_data = ChainData(
        data_type=int(ChainDataType.PERFORMANCE),
        device_ip="10.0.1.100",
        content=json.dumps({"cpu_percent": 45.2, "memory_percent": 67.8}),
        operate_user="system"
    )
    
    # 创建IPMI操作日志
    ipmi_data = ChainData(
        data_type=int(ChainDataType.IPMI_OPERATION),
        device_ip="10.0.1.100",
        content=json.dumps({"command": "power on", "status": "success"}),
        operate_user="admin"
    )
    
    # 测试序列化/反序列化
    fru_dict = fru_data.to_dict()
    fru_restored = ChainData.from_dict(fru_dict)
    assert fru_restored.data_type == fru_data.data_type
    assert fru_restored.device_ip == fru_data.device_ip
    print("✓ 链上数据结构测试通过")


def test_blockchain():
    """测试区块链核心功能"""
    print("\n=== 测试区块链核心功能 ===")
    
    # 创建临时区块链
    import tempfile
    tmpdir = tempfile.mkdtemp()
    bc = Blockchain("test-node", tmpdir)
    
    # 检查创世区块
    assert len(bc.chain) == 1
    assert bc.chain[0].block_height == 0
    print(f"创世区块高度: {bc.chain[0].block_height}")
    
    # 添加数据到待上链池
    data1 = ChainData(
        data_type=int(ChainDataType.FRU_HARDWARE),
        device_ip="10.0.1.100",
        content=json.dumps({"product_name": "Server-1"}),
        operate_user="system"
    )
    bc.add_data(data1)
    
    data2 = ChainData(
        data_type=int(ChainDataType.PERFORMANCE),
        device_ip="10.0.1.100",
        content=json.dumps({"cpu_percent": 50.0}),
        operate_user="system"
    )
    bc.add_data(data2)
    
    print(f"待上链数据: {len(bc.pending_data)}")
    assert len(bc.pending_data) == 2
    
    # 创建新区块
    new_block = bc.create_block("test-node")
    print(f"新区块高度: {new_block.block_height}")
    print(f"新区块数据条数: {len(new_block.data_list)}")
    
    # 添加区块到链
    success, error = bc.add_block(new_block)
    assert success, f"添加区块失败: {error}"
    assert len(bc.chain) == 2
    
    # 验证链的完整性
    assert bc.is_chain_valid()
    print("✓ 区块链核心功能测试通过")
    
    # 清理
    import shutil
    shutil.rmtree(tmpdir)


def test_chain_validation():
    """测试链式校验（防篡改）"""
    print("\n=== 测试链式校验 ===")
    
    import tempfile
    tmpdir = tempfile.mkdtemp()
    bc = Blockchain("test-node", tmpdir)
    
    # 添加几个区块
    for i in range(3):
        data = ChainData(
            data_type=int(ChainDataType.PERFORMANCE),
            device_ip="10.0.1.100",
            content=json.dumps({"cpu_percent": 50.0 + i}),
            operate_user="system"
        )
        bc.add_data(data)
        block = bc.create_block("test-node")
        bc.add_block(block)
    
    print(f"链高度: {len(bc.chain) - 1}")
    assert bc.is_chain_valid()
    
    # 篡改一个区块的数据
    bc.chain[1].data_list[0].content = "tampered data"
    
    # 重新计算该区块哈希（模拟高级篡改）
    bc.chain[1].current_hash = bc.chain[1].calculate_hash()
    
    # 验证应该失败（因为后续区块的prev_hash不再匹配）
    is_valid = bc.is_chain_valid()
    print(f"篡改后链验证: {'通过(异常!)' if is_valid else '失败(正确!)'}")
    assert not is_valid, "篡改检测未生效！"
    
    print("✓ 链式校验测试通过（篡改检测正常）")
    
    import shutil
    shutil.rmtree(tmpdir)


def test_consensus():
    """测试共识机制"""
    print("\n=== 测试共识机制 ===")
    
    peers = [
        {"node_id": "node-1", "host": "10.0.1.10", "port": 8080, "region": "bj"},
        {"node_id": "node-2", "host": "10.0.2.10", "port": 8080, "region": "sh"},
        {"node_id": "node-3", "host": "10.0.3.10", "port": 8080, "region": "us"},
    ]
    
    consensus = SimpleConsensus("node-1", peers, consensus_threshold=80)
    
    # 测试轮询记账
    print(f"node-1是否轮到记账: {consensus.is_my_turn()}")
    assert consensus.is_my_turn()  # 初始索引为0，node-1在第一个
    
    # 切换到下一个
    next_node = consensus.next_leader()
    print(f"下一个记账节点: {next_node}")
    assert next_node == "node-2"
    
    # 测试区块提议和投票
    genesis = create_genesis_block("node-1")
    block_hash = consensus.propose_block(genesis)
    
    # 模拟投票
    consensus.vote_block(block_hash, "node-1", True)
    consensus.vote_block(block_hash, "node-2", True)
    consensus.vote_block(block_hash, "node-3", True)
    
    # 检查是否达到共识
    confirmed = consensus.get_confirmed_block(block_hash)
    print(f"区块是否确认: {confirmed is not None}")
    assert confirmed is not None
    
    print("✓ 共识机制测试通过")


def test_query():
    """测试数据查询"""
    print("\n=== 测试数据查询 ===")
    
    import tempfile
    tmpdir = tempfile.mkdtemp()
    bc = Blockchain("test-node", tmpdir)
    
    # 添加不同类型的数据
    for i in range(5):
        data = ChainData(
            data_type=int(ChainDataType.FRU_HARDWARE) if i % 2 == 0 else int(ChainDataType.PERFORMANCE),
            device_ip=f"10.0.1.{100 + i}",
            content=json.dumps({"index": i}),
            operate_user="system"
        )
        bc.add_data(data)
        block = bc.create_block("test-node")
        bc.add_block(block)
    
    # 查询FRU数据
    fru_results = bc.query_data(data_type=int(ChainDataType.FRU_HARDWARE))
    print(f"FRU数据查询结果: {len(fru_results)} 条")
    assert len(fru_results) > 0
    
    # 查询特定设备
    device_results = bc.query_data(device_ip="10.0.1.100")
    print(f"特定设备查询结果: {len(device_results)} 条")
    
    print("✓ 数据查询测试通过")
    
    import shutil
    shutil.rmtree(tmpdir)


def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 50)
    print(" 区块链核心逻辑单元测试")
    print("=" * 50)
    
    tests = [
        test_block_creation,
        test_chain_data,
        test_blockchain,
        test_chain_validation,
        test_consensus,
        test_query,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ 测试失败: {e}")
            failed += 1
    
    print("\n" + "=" * 50)
    print(f" 测试结果: {passed} 通过, {failed} 失败")
    print("=" * 50)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
