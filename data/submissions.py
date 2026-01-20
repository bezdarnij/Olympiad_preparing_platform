import datetime
import sqlalchemy
from sqlalchemy import orm

from .db_session import SqlAlchemyBase


class Submissions(SqlAlchemyBase):
    __tablename__ = 'submissions'

    id = sqlalchemy.Column(sqlalchemy.Integer,
                           primary_key=True, autoincrement=True)
    user_id = sqlalchemy.Column(sqlalchemy.Integer,
                                sqlalchemy.ForeignKey("users.id"))
    task_id = sqlalchemy.Column(sqlalchemy.Integer,
                                sqlalchemy.ForeignKey("tasks.id"))
    file_path = sqlalchemy.Column(sqlalchemy.String, nullable=True)
    status = sqlalchemy.Column(sqlalchemy.String, nullable=True)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime,
                                     default=datetime.datetime.now)
    tasks = orm.relationship('Tasks', back_populates="submissions")
    user = orm.relationship("User", back_populates="submissions")
    result = orm.relationship("SubmissionResults", back_populates="submissions")