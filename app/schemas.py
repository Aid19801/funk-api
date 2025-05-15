from pydantic import BaseModel

class UserIn(BaseModel):
    email: str
    password: str

class UserOut(BaseModel):
    id: int
    email: str
    is_superuser: bool

    class Config:
        from_attributes = True
