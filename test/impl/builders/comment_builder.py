from typing import List, Union, Tuple, Optional, Dict, Any
from datetime import datetime
from .helpers import transform_datetime, create_uuid
from src.github.models import Comment, User
from .user_builder import UserBuilder


class CommentBuilder(object):
    def __init__(self, body: str = ""):
        self.raw_comment = {
            "id": create_uuid(),
            "body": body,
            "author": {"login": "somebody", "name": ""},
        }

    def body(self, body: str):
        self.raw_comment["body"] = body
        return self

    def author(self, user: Union[User, UserBuilder]):
        self.raw_comment["author"] = user.to_raw()
        return self

    def published_at(self, published_at: Union[str, datetime]):
        self.raw_comment["publishedAt"] = transform_datetime(published_at)
        return self

    def build(self) -> Comment:
        return Comment(self.raw_comment)

    def to_raw(self) -> Dict[str, Any]:
        return self.build().to_raw()
