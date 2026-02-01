from flask import Flask, render_template, redirect, request, abort, session
from data import db_session
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from data.users import User
from data.tasks import Tasks
from data.submissions import Submissions
from data.task_tests import TaskTest
from forms.user import RegisterForm, LoginForm
from flask_socketio import SocketIO, join_room, leave_room, emit
import uuid
import os
import subprocess
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = '65432456uijhgfdsxcvbn'

login_manager = LoginManager()
login_manager.init_app(app)

socketio = SocketIO(app, cors_allowed_origins="*")
matches = {}


@app.errorhandler(403)
def forbidden(e):
    return render_template("403.html"), 403


@login_manager.user_loader
def load_user(user_id):
    db_sess = db_session.create_session()
    return db_sess.get(User, user_id)


db_session.global_init("db/task.db")


def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user.admin:
            abort(403)
        return func(*args, **kwargs)

    return wrapper


def user_ban(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if current_user.ban:
            abort(403)
        return func(*args, **kwargs)

    return wrapper


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
        if user and user.check_password(form.password.data) and user.ban != 1:
            login_user(user, remember=form.remember_me.data)
            return redirect("/")
        return render_template('login.html',
                               message="Неправильный логин или пароль или вы в бане",
                               form=form)
    return render_template('login.html', title='Авторизация', form=form)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect("/")


@app.route('/profile')
@app.route('/profile/<int:user_id>')
@login_required
def profile(user_id=None):
    db_sess = db_session.create_session()
    if user_id is None:
        user = current_user
    else:
        user = db_sess.get(User, user_id)
        if not user:
            abort(404)

    all_submissions = db_sess.query(Submissions).filter(
        Submissions.user_id == user.id
    ).order_by(Submissions.created_at.desc()).all()
    tasks_stats = {}
    for submission in all_submissions:
        task_id = submission.task_id
        if task_id not in tasks_stats:
            tasks_stats[task_id] = {
                'task': submission.tasks,
                'best_submission': submission,
                'attempts': 1,
                'solved': submission.verdict == "OK"
            }
        else:
            tasks_stats[task_id]['attempts'] += 1
            if submission.total_tests > tasks_stats[task_id]['best_submission'].total_tests:
                tasks_stats[task_id]['best_submission'] = submission
            if submission.verdict == "OK":
                tasks_stats[task_id]['solved'] = True

    sorted_tasks = sorted(
        tasks_stats.values(),
        key=lambda x: (not x['solved'], -x['best_submission'].total_tests)
    )

    total_tasks_attempted = len(tasks_stats)
    solved_tasks = sum(1 for t in tasks_stats.values() if t['solved'])
    total_submissions = len(all_submissions)

    return render_template(
        'profile.html',
        user=user,
        tasks_stats=sorted_tasks,
        total_tasks_attempted=total_tasks_attempted,
        solved_tasks=solved_tasks,
        total_submissions=total_submissions,
        is_own_profile=(user.id == current_user.id)
    )


@app.route('/tasks')
@login_required
@user_ban
def tasks():
    db_sess = db_session.create_session()
    sort_by = request.args.get('sort_by')

    if sort_by == 'difficulty':
        tasks = db_sess.query(Tasks).order_by(Tasks.difficulty).all()
    elif sort_by == 'theme':
        tasks = db_sess.query(Tasks).all()
    else:
        tasks = db_sess.query(Tasks).all()

    return render_template('tasks.html', tasks=tasks)


@app.route('/admin', methods=["GET", "POST"])
@login_required
@admin_required
@user_ban
def admin():
    db_sess = db_session.create_session()
    users = db_sess.query(User)
    return render_template("admin_first.html", users=users)


@app.route('/admin/task', methods=["GET", "POST"])
@login_required
@admin_required
@user_ban
def admin_task():
    return render_template("admin_task.html")


@app.route('/pvp/create')
@login_required
@user_ban
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
@user_ban
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
@user_ban
def pvp_choose():
    open_rooms = []
    for room_id, info in matches.items():
        if len(info['players']) < 2:
            open_rooms.append(room_id)
    return render_template('choose.html', rooms=open_rooms)


@app.route('/task/<int:task_id>', methods=["GET", "POST"])
@login_required
@user_ban
def training(task_id):
    db_sess = db_session.create_session()
    task = db_sess.get(Tasks, task_id)
    task_test = db_sess.query(TaskTest).filter(TaskTest.task_id == task.id).all()
    submission = db_sess.query(Submissions).filter(Submissions.task_id == task.id).all()
    submission_id = len(submission) + 1
    if request.method == "POST":
        file = request.files.get("file")
        if not file or file.filename == "":
            abort(400, "Файл не выбран")
        file.filename = f"submission_{submission_id}.py"
        os.makedirs(f"submissions_training/submissions_{current_user.id}/task_{task_id}", exist_ok=True)
        file.save(os.path.join(f"submissions_training/submissions_{current_user.id}/task_{task_id}", file.filename))

        # judge
        test_passed = 0
        f_err = 0
        for test in task_test:
            p = subprocess.Popen(
                ["python", f"submission_{submission_id}.py"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=f"submissions_training/submissions_{current_user.id}/task_{task_id}"
            )
            try:
                out, err = p.communicate(test.input_data, timeout=task.time_limit)
                out = out.strip()
                if err:
                    print(err)
                    submission_result = Submissions(
                        user_id=current_user.id,
                        task_id=task_id,
                        verdict=err.splitlines()[-1],
                        total_tests=test_passed,
                    )
                    f_err = 1
                else:
                    if out == test.output.strip():
                        test_passed += 1
            except subprocess.TimeoutExpired:
                print("Превышено максимальное время работы")
                submission_result = Submissions(
                    user_id=current_user.id,
                    task_id=task_id,
                    verdict="Превышено максимальное время работы",
                    total_tests=test_passed,
                )
                f_err = 1
                p.kill()
        print(f"Пройдено тестов: {test_passed}")
        if test_passed == 5:
            print("OK")
            submission_result = Submissions(
                user_id=current_user.id,
                task_id=task_id,
                verdict="OK",
                total_tests=test_passed,
            )
        elif f_err == 0:
            print("неверный ответ")
            submission_result = Submissions(
                user_id=current_user.id,
                task_id=task_id,
                verdict="Частичное решение",
                total_tests=test_passed,
            )
        db_sess.add(submission_result)
        db_sess.commit()
    last_submission = db_sess.query(Submissions).filter(Submissions.user_id == current_user.id,
                                                        Submissions.task_id == task_id).all()
    if last_submission:
        result = last_submission[-1]
        verdict = result.verdict
        test_passed = result.total_tests
    else:
        verdict = "Нет сданных решений"
        test_passed = None
    return render_template('training.html', task=task, test=task_test[0], verdict=verdict, test_passed=test_passed)


@app.route('/pvp/room/<room>', methods=["GET", "POST"])
@login_required
@user_ban
def pvp_room(room):
    task_id = 2
    db_sess = db_session.create_session()
    task = db_sess.get(Tasks, task_id)
    task_test = db_sess.query(TaskTest).filter(TaskTest.task_id == task.id).all()
    submission = db_sess.query(Submissions).filter(Submissions.task_id == task.id).all()
    submission_id = len(submission) + 1
    if request.method == "POST":
        file = request.files.get("file")
        if not file or file.filename == "":
            abort(400, "Файл не выбран")
        file.filename = f"submission_{submission_id}.py"
        os.makedirs(f"submissions_pvp/submissions_{current_user.id}/task_{task_id}", exist_ok=True)
        file.save(os.path.join(f"submissions_pvp/submissions_{current_user.id}/task_{task_id}", file.filename))

        # judge
        test_passed = 0
        f_err = 0
        for test in task_test:
            p = subprocess.Popen(
                ["python", f"submission_{submission_id}.py"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=f"submissions_pvp/submissions_{current_user.id}/task_{task_id}"
            )
            try:
                out, err = p.communicate(test.input_data, timeout=task.time_limit)
                out = out.strip()
                if err:
                    print(err)
                    submission_result = Submissions(
                        user_id=current_user.id,
                        task_id=task_id,
                        verdict=err.splitlines()[-1],
                        total_tests=test_passed,
                    )
                    f_err = 1
                else:
                    if out == test.output.strip():
                        test_passed += 1
            except subprocess.TimeoutExpired:
                print("Превышено максимальное время работы")
                submission_result = Submissions(
                    user_id=current_user.id,
                    task_id=task_id,
                    verdict="Превышено максимальное время работы",
                    total_tests=test_passed,
                )
                f_err = 1
                p.kill()
        print(f"Пройдено тестов: {test_passed}")
        if test_passed == 5:
            print("OK")
            submission_result = Submissions(
                user_id=current_user.id,
                task_id=task_id,
                verdict="OK",
                total_tests=test_passed,
            )
        elif f_err == 0:
            print("неверный ответ")
            submission_result = Submissions(
                user_id=current_user.id,
                task_id=task_id,
                verdict="Частичное решение",
                total_tests=test_passed,
            )
        db_sess.add(submission_result)
        db_sess.commit()

        uid = str(current_user.id)
        matches[room]['completed'][uid] = max(matches[room]['completed'].get(uid, 0), test_passed)
        if len(matches[room]['completed']) == 2 and not matches[room].get('finished'):
            result = finish_match(room)
            socketio.emit('match_finished', {'result': result}, room=room)

        return redirect(f"/pvp/room/{room}")

    players_info = []
    for uid_str in matches[room]['players']:
        user = db_sess.get(User, int(uid_str))
        players_info.append({'name': user.name, 'elo': user.elo_rating})

    last_submission = db_sess.query(Submissions).filter(Submissions.user_id == current_user.id,
                                                        Submissions.task_id == task_id).all()
    if last_submission:
        result = last_submission[-1]
        verdict = result.verdict
        test_passed = result.total_tests
    else:
        verdict = "Нет сданных решений"
        test_passed = None
    return render_template('Pvp.html', room=room, task=task, test=task_test[0], players_info=players_info,
                           verdict=verdict, test_passed=test_passed)


def finish_match(room):
    db_sess = db_session.create_session()
    players = matches[room]['players']
    completed = matches[room]['completed']

    user1_id, user2_id = players
    user1 = db_sess.get(User, user1_id)
    user2 = db_sess.get(User, user2_id)

    score1 = completed.get(str(user1_id), 0)
    score2 = completed.get(str(user2_id), 0)
    from elo import update_elo
    if score1 > score2:
        user1.elo_rating, user2.elo_rating = update_elo(user1.elo_rating, user2.elo_rating)
        result = f"{user1.name} победил"
    elif score2 > score1:
        user2.elo_rating, user1.elo_rating = update_elo(user2.elo_rating, user1.elo_rating)
        result = f"{user2.name} победил"
    else:
        user1.elo_rating, user2.elo_rating = update_elo(user1.elo_rating, user2.elo_rating, draw=True)
        result = "Ничья"

    db_sess.commit()
    matches[room]['finished'] = True
    matches[room]['result'] = result
    return result


@socketio.on('join')
def on_join(data):
    room = data['room']
    join_room(room)
    if room not in matches:
        return

    db_sess = db_session.create_session()
    scores = []
    for user_id_str, score in matches[room]['completed'].items():
        user = db_sess.get(User, int(user_id_str))
        scores.append({
            'name': user.name if user else "???",
            'score': score,
            'elo': user.elo_rating if user else 1000
        })
    emit('update_scores',
         {'scores': scores,
          'player_count': len(matches[room]['players'])},
         room=room)


@socketio.on('submit_code')
def on_submit(data):
    room = data['room']
    if room not in matches or current_user.id not in matches[room]['players']:
        return

    uid = str(current_user.id)
    matches[room]['completed'][uid] = max(matches[room]['completed'].get(uid, 0), data.get('test_passed', 0))

    db_sess = db_session.create_session()
    scores = []
    for user_id_str, score in matches[room]['completed'].items():
        user = db_sess.get(User, int(user_id_str))
        scores.append({
            'name': user.name if user else "???",
            'score': score,
            'elo': user.elo_rating if user else 1000
        })
    emit('update_scores', {'scores': scores, 'player_count': len(matches[room]['players'])}, room=room)
    if len(matches[room]['completed']) == 2 and not matches[room].get('finished'):
        result = finish_match(room)
        emit('match_finished', {'result': result}, room=room)


if __name__ == '__main__':
    socketio.run(app, port=8025, host='127.0.0.1', allow_unsafe_werkzeug=True, debug=True)
