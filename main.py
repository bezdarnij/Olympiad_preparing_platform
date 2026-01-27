from flask import Flask, render_template, redirect, request, abort, session
from data import db_session
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from data.users import User
from data.tasks import Tasks
from data.submissions import Submissions
from data.submission_results import SubmissionResults
from data.task_tests import TaskTest
from forms.user import RegisterForm, LoginForm
from flask_socketio import SocketIO, join_room, leave_room, emit
import uuid
import os
import subprocess

app = Flask(__name__)
app.config['SECRET_KEY'] = '65432456uijhgfdsxcvbn'

login_manager = LoginManager()
login_manager.init_app(app)

socketio = SocketIO(app, cors_allowed_origins="*")
matches = {}


@login_manager.user_loader
def load_user(user_id):
    db_sess = db_session.create_session()
    return db_sess.get(User, user_id)


db_session.global_init("db/task.db")


@app.route("/")
def index():
    return render_template("index.html")


@app.route('/register', methods=['GET', 'POST'])
def reqister():
    form = RegisterForm()
    if form.validate_on_submit():
        if form.password.data != form.password_again.data:
            return render_template('register.html', title='Регистрация',
                                   form=form,
                                   message="Пароли не совпадают")
        db_sess = db_session.create_session()
        if db_sess.query(User).filter(User.email == form.email.data).first():
            return render_template('register.html', title='Регистрация',
                                   form=form,
                                   message="Такой пользователь уже есть")
        user = User(
            name=form.name.data,
            email=form.email.data,
            about=form.about.data
        )
        user.set_password(form.password.data)
        db_sess.add(user)
        db_sess.commit()
        return redirect('/login')
    return render_template('register.html', title='Регистрация', form=form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        db_sess = db_session.create_session()
        user = db_sess.query(User).filter(User.email == form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember_me.data)
            return redirect("/")
        return render_template('login.html',
                               message="Неправильный логин или пароль",
                               form=form)
    return render_template('login.html', title='Авторизация', form=form)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect("/")


@app.route('/tasks')
@login_required
def tasks_list():
    db_sess = db_session.create_session()
    tasks = db_sess.query(Tasks).all()
    return render_template('tasks.html', tasks=tasks)


@app.route('/pvp/create')
@login_required
def create_pvp():
    room = str(uuid.uuid4())
    session['room'] = room
    matches[room] = {
        'players': [current_user.id],
        'completed': {str(current_user.id): 0}
    }
    return redirect(f'/pvp/room/{room}')


@app.route('/pvp/join/<room>')
@login_required
def join_pvp(room):
    if room not in matches:
        abort(404)
    if len(matches[room]['players']) >= 2:
        return "комната заполнена", 400
    if current_user.id in matches[room]['players']:
        return redirect(f'/pvp/room/{room}')
    matches[room]['players'].append(current_user.id)
    matches[room]['completed'][str(current_user.id)] = 0
    session['room'] = room
    return redirect(f'/pvp/room/{room}')

@app.route('/pvp', methods=["GET", "POST"])
@login_required
def pvp_choose():
    open_rooms = []
    for room_id, info in matches.items():
        if len(info['players']) < 2:
            open_rooms.append(room_id)
    return render_template('choose.html', rooms=open_rooms)


@app.route('/training', methods=["GET", "POST"])
@login_required
def training():
    task_id = 1
    db_sess = db_session.create_session()
    task = db_sess.get(Tasks, task_id)
    task_test = db_sess.query(TaskTest).filter(TaskTest.task_id == task.id).all()
    if request.method == "POST":
        file = request.files.get("file")
        if not file or file.filename == "":
            abort(400, "Файл не выбран")
        file.filename = f"submission_{current_user.id}.py"
        os.makedirs(f"submissions_training/submissions_{current_user.id}", exist_ok=True)
        file.save(os.path.join(f"submissions_training/submissions_{current_user.id}", file.filename))

        # judge
        test_passed = 0
        for test in task_test:
            p = subprocess.Popen(
                ["python", f"submission_{current_user.id}.py"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=f"submissions_training/submissions_{current_user.id}/"
            )
            try:
                out, err = p.communicate(test.input_data, timeout=task.time_limit)
                out = out.strip()
                if err:
                    print(err)
                else:
                    if out == test.output.strip():
                        test_passed += 1
            except subprocess.TimeoutExpired:
                print("Превышено максимальное время работы")
                p.kill()
        print(f"Пройдено тестов: {test_passed}")
        if test_passed == 5:
            print("OK")
        else:
            print("неверный ответ")
    return render_template('training.html', task=task, test=task_test[0])


@app.route('/pvp/room/<room>', methods=["GET", "POST"])
@login_required
def pvp_room(room):
    if room not in matches or current_user.id not in matches[room]['players']:
        abort(403)
    task_id = 1
    db_sess = db_session.create_session()
    task = db_sess.get(Tasks, task_id)
    task_test = db_sess.query(TaskTest).filter(TaskTest.task_id == task.id).all()
    if request.method == "POST":
        file = request.files.get("file")
        if not file or file.filename == "":
            abort(400, "Файл не выбран")
        file.filename = f"submission_{current_user.id}.py"
        os.makedirs(f"submissions_pvp/submissions_{current_user.id}", exist_ok=True)
        file.save(os.path.join(f"submissions_pvp/submissions_{current_user.id}", file.filename))

        # judge
        test_passed = 0
        for test in task_test:
            p = subprocess.Popen(
                ["python", f"submission_{current_user.id}.py"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=f"submissions_pvp/submissions_{current_user.id}/"
            )
            try:
                out, err = p.communicate(test.input_data, timeout=task.time_limit)
                out = out.strip()
                if err:
                    print(err)
                else:
                    if out == test.output.strip():
                        test_passed += 1
            except subprocess.TimeoutExpired:
                print("Превышено максимальное время работы")
                p.kill()
        print(f"Пройдено тестов: {test_passed}")
        if test_passed == 5:
            print("OK")
        else:
            print("неверный ответ")

        uid = str(current_user.id)
        if uid not in matches[room]['completed']:
            matches[room]['completed'][uid] = 0
        matches[room]['completed'][uid] += 1
        return redirect(f"/pvp/room/{room}")

    return render_template('Pvp.html', room=room, task=task, test=task_test[0]) # cюда шаблончик бах


@socketio.on('join')
def on_join(data):
    room = data['room']
    join_room(room)

    if room in matches:
        db_sess = db_session.create_session()
        scores = []
        for user_id_str, score in matches[room]['completed'].items():
            user = db_sess.get(User, int(user_id_str))
            name = user.name if user else "???"
            scores.append({'name': name, 'score': score})
        player_count = len(matches[room]['players'])
        emit('update_scores', {
            'scores': scores,
            'player_count': player_count
        })

@socketio.on('submit_code')
def on_submit(data):
    room = data['room']
    if room not in matches:
        return
    if current_user.id not in matches[room]['players']:
        return
    uid = str(current_user.id)
    matches[room]['completed'][uid] = matches[room]['completed'].get(uid, 0) + 1
    db_sess = db_session.create_session()
    scores = []
    for user_id_str, score in matches[room]['completed'].items():
        user = db_sess.query(User).get(int(user_id_str))
        name = user.name if user else "???"
        scores.append({'name': name, 'score': score})

    player_count = len(matches[room]['players'])
    emit('update_scores', {'scores': scores, 'player_count': player_count}, room=room)


if __name__ == '__main__':
    socketio.run(app, port=8025, host='127.0.0.1', allow_unsafe_werkzeug=True, debug=True)
