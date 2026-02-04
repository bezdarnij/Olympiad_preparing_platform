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


@app.route('/favicon.ico')
def favicon():
    return '', 204


@app.route("/")
@app.route("/<subject>/")
def index(subject=None):
    if request.path == '/' or 'subject' in request.path:
        return redirect('/subject')

    db_sess = db_session.create_session()
    sort_by = request.args.get('sort_by')

    difficulties = db_sess.query(Tasks.difficulty).filter(Tasks.subject == subject).distinct().all()
    difficulties = [d[0] for d in difficulties if d[0]]
    themes = db_sess.query(Tasks.theme).filter(Tasks.subject == subject).distinct().all()
    themes = [t[0] for t in themes if t[0]]
    selected_difficulties = request.args.getlist('difficulty')
    selected_themes = request.args.getlist('theme')

    query = db_sess.query(Tasks).filter(Tasks.subject == subject)
    if selected_difficulties:
        query = query.filter(Tasks.difficulty.in_(selected_difficulties))
    if selected_themes:
        query = query.filter(Tasks.theme.in_(selected_themes))
    if sort_by == 'difficulty':
        tasks = query.order_by(Tasks.difficulty).all()
    elif sort_by == 'theme':
        tasks = query.all()
    else:
        tasks = query.all()
    return render_template('tasks.html', tasks=tasks, subject=subject,
                           difficulties=difficulties, themes=themes, selected_difficulties=selected_difficulties,
                           selected_themes=selected_themes, sort_by=sort_by)


@app.route("/<subject>", methods=['GET', 'POST'])
def subject(subject):
    session['subject'] = "subject"
    path = request.path.split('/')
    if path[1] != 'subject':
        session['subject'] = path[1]
        return redirect(f"/{subject}/")
    return render_template('subject.html',  subject=subject)


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
@user_ban
def profile(user_id=None):
    subject = session.get('subject')
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
        is_own_profile=(user.id == current_user.id),
        subject=subject
    )


@app.route('/admin', methods=["GET", "POST"])
@login_required
@admin_required
@user_ban
def admin():
    subject = session.get('subject')
    db_sess = db_session.create_session()
    users = db_sess.query(User)
    if request.method == "POST":
        for user in users:
            admin_value = request.form.get(f"admin_{user.id}")
            ban_value = request.form.get(f"ban_{user.id}")
            if admin_value == "admin":
                user.admin = 1
            if admin_value == "user":
                user.admin = 0
            if ban_value == "banned":
                user.ban = 1
            if ban_value == "unbanned":
                user.ban = 0
        db_sess.commit()
        return redirect('/admin')
    return render_template("admin_first.html", users=users, subject=subject)


@app.route('/admin/task', methods=["GET", "POST"])
@login_required
@admin_required
@user_ban
def subject_admin():
    subject = session['subject']
    return render_template("subject_admin.html", subject=subject)


@app.route('/admin/task/<subject_admin>', methods=["GET", "POST"])
@login_required
@admin_required
@user_ban
def admin_task(subject_admin):
    subject = session['subject']
    if subject_admin == 'информатика':
        if request.method == "POST":
            db_sess = db_session.create_session()
            subject_name = request.form.get("subject")
            task_name = request.form.get("task_name")
            memory_limit = request.form.get("memory_limit")
            time_limit = request.form.get("time_limit")
            task_description = request.form.get("task_description")
            input_data = request.form.get("input_data")
            output_data = request.form.get("output_data")
            level = request.form.get("level")
            theme = request.form.get("theme")
            test_list = []
            test_list.append((request.form.get("test1_input"), request.form.get("test1_output")))
            test_list.append((request.form.get("test2_input"), request.form.get("test2_output")))
            test_list.append((request.form.get("test3_input"), request.form.get("test3_output")))
            test_list.append((request.form.get("test4_input"), request.form.get("test4_output")))
            test_list.append((request.form.get("test5_input"), request.form.get("test5_output")))
            task = Tasks(
                subject=subject_name,
                title=task_name,
                statement=task_description,
                input_format=input_data,
                output_format=output_data,
                memory_limit=memory_limit,
                time_limit=time_limit,
                difficulty=level,
                theme=theme
            )
            task_id = db_sess.query(Tasks).all()[-1].id + 1
            for i in range(5):
                task_test = TaskTest(
                    task_id=task_id,
                    input_data=test_list[i][0],
                    output=test_list[i][1],
                )
                db_sess.add(task_test)
            db_sess.add(task)
            db_sess.commit()
    return render_template("admin_task.html", subject_admin=subject_admin, subject=subject)


@app.route('/<subject>/pvp/create')
@login_required
@user_ban
def create_pvp(subject):
    room = str(uuid.uuid4())
    session['room'] = room
    matches[room] = {
        'players': [current_user.id],
        'completed': {str(current_user.id): 0}
    }
    return redirect(f'/{subject}/pvp/room/{room}')


@app.route('/<subject>/pvp/join/<room>')
@login_required
@user_ban
def join_pvp(subject, room):
    if room not in matches:
        abort(404)
    if len(matches[room]['players']) >= 2:
        return "комната заполнена", 400
    if current_user.id in matches[room]['players']:
        return redirect(f'/{subject}/pvp/room/{room}')
    matches[room]['players'].append(current_user.id)
    matches[room]['completed'][str(current_user.id)] = 0
    session['room'] = room
    return redirect(f'/{subject}/pvp/room/{room}')


@app.route('/<subject>/pvp', methods=["GET", "POST"])
@login_required
@user_ban
def pvp_choose(subject):
    open_rooms = []
    for room_id, info in matches.items():
        if len(info['players']) < 2:
            open_rooms.append(room_id)
    return render_template('choose.html', rooms=open_rooms, subject=subject)


@app.route('/<subject>/task/<int:task_id>', methods=["GET", "POST"])
@login_required
@user_ban
def training(subject, task_id):
    db_sess = db_session.create_session()
    task = db_sess.get(Tasks, task_id)
    task_test = db_sess.query(TaskTest).filter(TaskTest.task_id == task.id).all()
    submission = db_sess.query(Submissions).filter(Submissions.task_id == task.id).all()
    submission_id = len(submission) + 1
    if subject == 'информатика':
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
        return render_template('training.html', task=task, test=task_test[0], verdict=verdict, test_passed=test_passed, subject=subject)
    else:
        if request.method == "POST":
            answer = request.form.get("answer")
            if task_test[0].input_data == answer:
                submission_result = Submissions(
                    user_id=current_user.id,
                    task_id=task_id,
                    verdict="OK",
                )
            else:
                submission_result = Submissions(
                    user_id=current_user.id,
                    task_id=task_id,
                    verdict="Неверный ответ, попробуйте снова",
                )
            db_sess.add(submission_result)
            db_sess.commit()
        last_submission = db_sess.query(Submissions).filter(Submissions.user_id == current_user.id,
                                                    Submissions.task_id == task_id).all()
        if last_submission:
            result = last_submission[-1]
            verdict = result.verdict
        else:
            verdict = "Нет сданных решений"
        return render_template('training_other.html', task=task, verdict=verdict, subject=subject)


@app.route('/<subject>/pvp/room/<room>', methods=["GET", "POST"])
@login_required
@user_ban
def pvp_room(subject, room):
    task_id = 2
    db_sess = db_session.create_session()
    task = db_sess.get(Tasks, task_id)
    task_test = db_sess.query(TaskTest).filter(TaskTest.task_id == task.id).all()
    submission = db_sess.query(Submissions).filter(Submissions.task_id == task.id).all()
    submission_id = len(submission) + 1
    if subject == 'информатика':
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
                    ["python3", f"submission_{submission_id}.py"],
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

            return redirect(f"/{subject}/pvp/room/{room}")

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
                            verdict=verdict, test_passed=test_passed, subject=subject)
    else:
        if request.method == "POST":
            answer = request.form.get("answer")
            if task_test[0].input_data == answer:
                submission_result = Submissions(
                    user_id=current_user.id,
                    task_id=task_id,
                    verdict="OK",
                )
            else:
                submission_result = Submissions(
                    user_id=current_user.id,
                    task_id=task_id,
                    verdict="Неверный ответ, попробуйте снова",
                )
        last_submission = db_sess.query(Submissions).filter(Submissions.user_id == current_user.id,
                                                    Submissions.task_id == task_id).all()
        if last_submission:
            result = last_submission[-1]
            verdict = result.verdict
        else:
            verdict = "Нет сданных решений"
        return render_template('training_other.html', task=task, verdict=verdict, subject=subject)


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
    socketio.run(app, port=8080, host='127.0.0.1', allow_unsafe_werkzeug=True, debug=True)
