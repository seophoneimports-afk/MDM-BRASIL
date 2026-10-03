from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict, Any

# Client Schemas
class UserRegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    whatsapp: str = Field(..., min_length=8, max_length=25)
    password: str = Field(..., min_length=6, max_length=100)

class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str

class PasswordResetRequest(BaseModel):
    email: EmailStr
    new_password: str = Field(..., min_length=6)

class PasswordResetInitRequest(BaseModel):
    email: EmailStr

class PasswordResetConfirmRequest(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=4, max_length=10)
    new_password: str = Field(..., min_length=6, max_length=100)

class ThemeUpdateRequest(BaseModel):
    theme: str = Field(..., pattern="^(cinema_stealth|apex_quantum|matrix_cyber|neon_cyberblade|hypersaas_enterprise)$")

class BuyCreditsRequest(BaseModel):
    credits_amount: int = Field(..., ge=1, le=1000)

# Admin Schemas
class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str

class AdminAdjustCreditsRequest(BaseModel):
    user_id: int
    amount_credits: int = Field(..., ne=0)
    type: str = Field("ADJUSTMENT", pattern="^(ADJUSTMENT|BONUS|REFUND)$")
    justification: str = Field(..., min_length=5, max_length=255)

class AdminUpdateUserRequest(BaseModel):
    status: Optional[str] = Field(None, pattern="^(active|suspended|pending)$")
    name: Optional[str] = None
    whatsapp: Optional[str] = None

class AdminSettingRequest(BaseModel):
    key: str
    value: str

# EXE Schemas
class ExeLoginRequest(BaseModel):
    email: EmailStr
    password: str

class ExeConsumeRequest(BaseModel):
    device_serial: str = Field(..., min_length=2)
    device_model: Optional[str] = "Android Device"
    service_code: Optional[str] = "FRP_MDM_UNLOCK"
    service_name: Optional[str] = "Desbloqueio e Gestão MDM/FRP"
    client_name: Optional[str] = "Cliente Final"
    credits_to_consume: int = Field(1, ge=1)

class GoogleAuthRequest(BaseModel):
    credential: Optional[str] = None
    email: Optional[EmailStr] = None
    name: Optional[str] = None
    google_id: Optional[str] = None
    avatar_url: Optional[str] = None
    password: Optional[str] = None

class UpdateClientPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=6, max_length=100)

class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    whatsapp: Optional[str] = None
    avatar_url: Optional[str] = None
    new_password: Optional[str] = None

class PixPreviewRequest(BaseModel):
    pix_key: str
    key_type: Optional[str] = "AUTO"
    merchant_name: Optional[str] = "MDM FRP BRASIL"
    merchant_city: Optional[str] = "AMERICANA"
    amount: Optional[float] = 5.00

# Webhook Schema
class PixWebhookSimulationRequest(BaseModel):
    txid: str
    idempotency_key: Optional[str] = None
    status: str = "PAID"
