from pydantic import BaseModel
from typing import Optional
from uuid import UUID

class CommentRequest(BaseModel):
    content: str

class CreateComment(BaseModel):
    target_type: str # "user" | "video" | "post",
    target_id: UUID # unique ID of the page, maybe the slug?
    content: str # the actual html string thing

class UserProfile(BaseModel):
    first_name: str
    last_name: str
    profile_picture: Optional[str] = None
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    address_line_3: Optional[str] = None
    postcode: Optional[str] = None
    credit_card_encrypted: Optional[str] = None


class CreateUserProfile(BaseModel):
    user_profile: UserProfile

class SignupRequest(BaseModel):
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

