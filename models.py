from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class UserProfile(BaseModel):
    user_id: int
    first_name: str
    last_name: str
    email: str
    profile_picture: Optional[str] = None
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    address_line_3: Optional[str] = None
    postcode: Optional[str] = None
    credit_card_encrypted: Optional[str] = None
    created_at: datetime


class CreateUserProfile(BaseModel):
    user_profile: UserProfile

class SignupRequest(BaseModel):
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

