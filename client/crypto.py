"""
FRU数据加密传输模块
使用AES-256-CBC加密敏感FRU硬件信息，确保传输安全
"""
import hashlib
import base64
import os
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class FRUCrypto:
    """
    FRU数据加密器
    使用AES-256-CBC对称加密，密钥由管理员密码派生
    """

    def __init__(self, password: str = "admin123"):
        """
        初始化加密器
        :param password: 加密密码（从web配置中获取）
        """
        self.password = password
        self.key = hashlib.sha256(password.encode('utf-8')).digest()  # 32 bytes = AES-256

    def encrypt(self, data: Any) -> Dict[str, str]:
        """
        加密数据
        :param data: 待加密的数据（字典/列表/字符串）
        :return: {encrypted: True, iv, data, alg}
        """
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            from cryptography.hazmat.primitives import padding as sym_padding

            # 序列化为JSON
            plaintext = json.dumps(data, ensure_ascii=False).encode('utf-8')

            # 生成随机IV
            iv = os.urandom(16)

            # PKCS7填充
            padder = sym_padding.PKCS7(128).padder()
            padded = padder.update(plaintext) + padder.finalize()

            # AES-256-CBC加密
            cipher = Cipher(algorithms.AES(self.key), modes.CBC(iv))
            encryptor = cipher.encryptor()
            ciphertext = encryptor.update(padded) + encryptor.finalize()

            # 计算HMAC-SHA256用于完整性校验
            hmac_key = hashlib.sha256(self.key + b"hmac").digest()
            import hmac as hmac_mod
            mac = hmac_mod.new(hmac_key, iv + ciphertext, hashlib.sha256).hexdigest()

            return {
                "encrypted": True,
                "iv": base64.b64encode(iv).decode('ascii'),
                "data": base64.b64encode(ciphertext).decode('ascii'),
                "mac": mac,
                "alg": "AES-256-CBC"
            }

        except ImportError:
            logger.warning("cryptography库未安装，使用XOR降级加密")
            return self._xor_encrypt(data)

    def decrypt(self, encrypted_data: Dict[str, str]) -> Any:
        """
        解密数据
        :param encrypted_data: {encrypted, iv, data, mac, alg}
        :return: 解密后的原始数据
        """
        if not encrypted_data.get("encrypted"):
            return encrypted_data

        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            from cryptography.hazmat.primitives import padding as sym_padding

            # 验证HMAC
            iv = base64.b64decode(encrypted_data["iv"])
            ciphertext = base64.b64decode(encrypted_data["data"])

            hmac_key = hashlib.sha256(self.key + b"hmac").digest()
            import hmac as hmac_mod
            expected_mac = hmac_mod.new(hmac_key, iv + ciphertext, hashlib.sha256).hexdigest()
            if not hmac_mod.compare_digest(expected_mac, encrypted_data.get("mac", "")):
                raise ValueError("HMAC校验失败，数据可能被篡改")

            # AES-256-CBC解密
            cipher = Cipher(algorithms.AES(self.key), modes.CBC(iv))
            decryptor = cipher.decryptor()
            padded = decryptor.update(ciphertext) + decryptor.finalize()

            # 去除PKCS7填充
            unpadder = sym_padding.PKCS7(128).unpadder()
            plaintext = unpadder.update(padded) + unpadder.finalize()

            return json.loads(plaintext.decode('utf-8'))

        except ImportError:
            return self._xor_decrypt(encrypted_data)

    def _xor_encrypt(self, data: Any) -> Dict[str, str]:
        """
        XOR降级加密（当cryptography库不可用时使用）
        安全性低于AES，仅作为降级方案
        """
        plaintext = json.dumps(data, ensure_ascii=False).encode('utf-8')
        key_stream = self.key  # 32 bytes
        extended_key = (key_stream * (len(plaintext) // len(key_stream) + 1))[:len(plaintext)]
        encrypted = bytes(a ^ b for a, b in zip(plaintext, extended_key))
        nonce = os.urandom(8)

        # 简单HMAC
        hmac_key = hashlib.sha256(self.key + b"hmac_xor").digest()
        import hmac as hmac_mod
        mac = hmac_mod.new(hmac_key, nonce + encrypted, hashlib.sha256).hexdigest()

        return {
            "encrypted": True,
            "iv": base64.b64encode(nonce).decode('ascii'),
            "data": base64.b64encode(encrypted).decode('ascii'),
            "mac": mac,
            "alg": "XOR-SHA256"
        }

    def _xor_decrypt(self, encrypted_data: Dict[str, str]) -> Any:
        """XOR降级解密"""
        encrypted = base64.b64decode(encrypted_data["data"])
        key_stream = self.key
        extended_key = (key_stream * (len(encrypted) // len(key_stream) + 1))[:len(encrypted)]
        plaintext = bytes(a ^ b for a, b in zip(encrypted, extended_key))
        return json.loads(plaintext.decode('utf-8'))

    @staticmethod
    def derive_key_base64(password: str) -> str:
        """
        从密码派生Base64编码的密钥（供前端CryptoJS使用）
        CryptoJS的AES需要Base64编码的密钥
        """
        key = hashlib.sha256(password.encode('utf-8')).digest()
        return base64.b64encode(key).decode('ascii')
