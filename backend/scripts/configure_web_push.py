"""为本机生成 Web Push 密钥；已有密钥不覆盖，不输出私钥。"""
import base64
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from dotenv import dotenv_values

path = Path(__file__).resolve().parents[1] / '.env'
existing = dotenv_values(path)
if existing.get('WEB_PUSH_VAPID_PUBLIC_KEY') and existing.get('WEB_PUSH_VAPID_PRIVATE_KEY'):
    print('Web Push 已有密钥，保留现有配置。')
else:
    key = ec.generate_private_key(ec.SECP256R1())
    encode = lambda value: base64.urlsafe_b64encode(value).decode().rstrip('=')
    values = {
        'WEB_PUSH_VAPID_PUBLIC_KEY': encode(key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)),
        'WEB_PUSH_VAPID_PRIVATE_KEY': encode(key.private_numbers().private_value.to_bytes(32, 'big')),
        'WEB_PUSH_VAPID_SUBJECT': existing.get('WEB_PUSH_VAPID_SUBJECT') or 'mailto:admin@localhost',
    }
    lines = path.read_text().splitlines() if path.exists() else []
    lines = [line for line in lines if line.split('=', 1)[0].strip() not in values]
    path.write_text('\n'.join(lines) + '\n' + '\n'.join(f'{name}={value}' for name, value in values.items()) + '\n')
    path.chmod(0o600)
    print('已生成本机 Web Push 密钥并保存到 backend/.env；生产部署请配置实际联系地址与 HTTPS。')
