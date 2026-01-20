import datetime
import sqlalchemy
from sqlalchemy import orm

from .db_session import SqlAlchemyBase


class SubmissionResults(SqlAlchemyBase):
    __tablename__ = 'submission_results'

    id = sqlalchemy.Column(sqlalchemy.Integer,
                           primary_key=True, autoincrement=True)
    submission_id = sqlalchemy.Column(sqlalchemy.Integer,
                                sqlalchemy.ForeignKey("submissions.id"))
    score = sqlalchemy.Column(sqlalchemy.Integer, nullable=True)
    total_tests = sqlalchemy.Column(sqlalchemy.Integer, nullable=True)
    passed_tests = sqlalchemy.Column(sqlalchemy.Integer, nullable=True)
    failed_tests = sqlalchemy.Column(sqlalchemy.Integer, nullable=True)
    stderr = sqlalchemy.Column(sqlalchemy.String, nullable=True)
    stdout = sqlalchemy.Column(sqlalchemy.String, nullable=True)
    submissions = orm.relationship("Submissions", back_populates="result")