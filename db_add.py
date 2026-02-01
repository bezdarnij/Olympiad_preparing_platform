from data import db_session
from data.tasks import Tasks
from data.task_tests import TaskTest

db_sess = db_session.create_session()
task = Tasks(
    title="",
    statement="",
    input_format="",
    output_format="",
    time_limit="",
    memory_limit="",
    difficulty=""
)
task_id = db_sess.query(Tasks).all()[-1].id
print(task_id)
test = TaskTest(
    task_id=task_id,
    input_data="",
    output="",
)
db_sess.add(test)
test = TaskTest(
    task_id=task_id,
    input_data="",
    output="",
)
db_sess.add(test)
test = TaskTest(
    task_id=task_id,
    input_data="",
    output="",
)
db_sess.add(test)
test = TaskTest(
    task_id=task_id,
    input_data="",
    output="",
)
db_sess.add(test)
test = TaskTest(
    task_id=task_id,
    input_data="",
    output="",
)
db_sess.add(test)
db_sess.commit()