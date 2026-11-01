import re
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.core.legal import CURRENT_TERMS_VERSION


class TermsAcceptance(BaseModel):
    accepted_terms_version: Literal[CURRENT_TERMS_VERSION] = Field(
        ...,
        description='请先阅读并同意当前版本的免责声明和使用规范',
    )

def normalize_username(value: str) -> str:
    value = value.strip()
    if not value or len(value) > 32 or re.fullmatch(r'1[3-9]\d{9}', value) or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError('登录名须为 1 至 32 个字符')
    return value

def normalize_phone(value: str) -> str:
    value = value.strip()
    if not re.fullmatch(r'1[3-9]\d{9}', value):
        raise ValueError('手机号格式不正确')
    return value

def validate_password(value: str) -> str:
    if len(value) < 6 or len(value) > 64 or not value.strip():
        raise ValueError('密码须为 6 至 64 位，且不能全为空格')
    return value

class Credentials(BaseModel):
    username: str = Field(..., min_length=1, max_length=32)
    password: str = Field(..., min_length=6, max_length=64)
    _username = field_validator('username')(normalize_username)
    _password = field_validator('password')(validate_password)

class RegisterRequest(Credentials, TermsAcceptance):
    # 注册必须绑定手机号；短信验证码或手机号短信登录产生的短期凭证
    # 二选一完成手机号验证。
    phone: str
    sms_code: Optional[str] = Field(default=None, pattern=r'^\d{6}$')
    registration_token: Optional[str] = Field(default=None, min_length=16, max_length=512)
    _phone = field_validator('phone')(normalize_phone)


class SmsLoginRequest(TermsAcceptance):
    """手机号短信登录请求。

    登录和注册共用短信验证码，但场景仍由后端固定为 ``login``，避免
    客户端任意指定场景绕过认证流程。
    """

    phone: str
    sms_code: str = Field(..., pattern=r'^\d{6}$')
    _phone = field_validator('phone')(normalize_phone)

class LoginRequest(TermsAcceptance):
    username: Optional[str] = Field(default=None, min_length=1, max_length=32)
    phone: Optional[str] = None
    password: str = Field(..., min_length=6, max_length=64)
    _username = field_validator('username')(normalize_username)
    _phone = field_validator('phone')(normalize_phone)
    _password = field_validator('password')(validate_password)

    @property
    def has_one_identifier(self) -> bool:
        return bool(self.username) ^ bool(self.phone)

class ForgotPasswordRequest(BaseModel):
    # 密码重置必须通过手机号短信完成，禁止仅凭用户名重置。
    phone: str
    sms_code: str = Field(..., pattern=r'^\d{6}$')
    new_password: str = Field(..., min_length=6, max_length=64)
    _phone = field_validator('phone')(normalize_phone)
    _password = field_validator('new_password')(validate_password)


class SendSmsRequest(BaseModel):
    phone: str
    scene: Literal['register', 'login', 'modify_phone', 'reset_password', 'bind_phone', 'verify_phone']
    _phone = field_validator('phone')(normalize_phone)


class BindPhoneRequest(BaseModel):
    phone: str
    sms_code: str = Field(..., pattern=r'^\d{6}$')
    scene: Literal['modify_phone', 'bind_phone', 'verify_phone'] = 'bind_phone'
    _phone = field_validator('phone')(normalize_phone)

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    phone: Optional[str] = None
    active_family_id: Optional[int] = None
    notifications_enabled: bool = True
    system_notifications_enabled: bool = False


class PreferencesRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    notifications_enabled: Optional[bool] = None
    system_notifications_enabled: Optional[bool] = None


class SessionOut(BaseModel):
    id: int
    created_at: str
    expires_at: str
    current: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'
    user: UserOut
    is_new: bool = False


class SmsLoginResponse(BaseModel):
    """短信登录结果。

    已注册手机号会返回完整 TokenResponse 字段；新手机号返回
    ``requires_registration=true``、手机号和一次性注册凭证，前端据此
    自动切换到注册表单。
    """

    access_token: Optional[str] = None
    token_type: str = 'bearer'
    user: Optional[UserOut] = None
    is_new: bool = False
    requires_registration: bool = False
    phone: Optional[str] = None
    registration_token: Optional[str] = None
