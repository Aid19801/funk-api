from pydantic import BaseModel
from typing import Optional
from uuid import UUID

class CommentRequest(BaseModel):
    content: str

class CreateComment(BaseModel):
    target_type: str  # e.g. "podcast" or "youtube"
    target_id: str    # now allows slugs like "/podcast/b9044..."
    content: str
    author_name: Optional[str] = None
    author_profile_picture: Optional[str] = None

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
    
class ContentType(BaseModel):
    id: str
    platform: str
    title: str
    text: str
    image: str
    external_link: str
    internal_link: str
    published_at: str
    channel_title: Optional[str] = None # youtube only
    channel_id: Optional[str] = None # youtube only
    audio_url: Optional[str] = None # pinecast/podcast only