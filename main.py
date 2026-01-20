from flask import Flask, render_template, redirect, request, abort, session
from data import db_session
from data.news import News
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from data.users import User
from data.tasks import Tasks
from data.submissions import Submissions
from data.submission_results import SubmissionResults
from data.task_tests import TaskTest
from forms.news import NewsForm
from data.tasks import Tasks
from data.submissions import Submissions
from data.submission_results import SubmissionResults
from data.task_tests import TaskTest
from forms.user import RegisterForm, LoginForm
from flask_socketio import SocketIO, join_room, leave_room, emit
import uuid

app = Flask(__name__)
app.config['SECRET_KEY'] = '65432456uijhgfdsxcvbn'

login_manager = LoginManager()
login_manager.init_app(app)

socketio = SocketIO(app, cors_allowed_origins="*")
matches = {}

@login_manager.user_loader
def load_user(user_id):
    db_sess = db_session.create_session()
    return db_sess.query(User).get(user_id)

db_session.global_init("db/task.db")

@app.route("/")
def index():
    db_sess = db_session.create_session()
    if current_user.is_authenticated:
        news = db_sess.query(News).filter(
            (News.user == current_user) | (News.is_private != True))
    else:
        news = db_sess.query(News).filter(News.is_private != True)
    return render_template("index.html", news=news)

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

@app.route('/news', methods=['GET', 'POST'])
@login_required
def add_news():
    form = NewsForm()
    if form.validate_on_submit():
        db_sess = db_session.create_session()
        news = News()
        news.title = form.title.data
        news.content = form.content.data
        news.is_private = form.is_private.data
        current_user.news.append(news)
        db_sess.merge(current_user)
        db_sess.commit()
        return redirect('/')
    return render_template('news.html', title='Добавление новости',
                           form=form)

@app.route('/news/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_news(id):
    form = NewsForm()
    if request.method == "GET":
        db_sess = db_session.create_session()
        news = db_sess.query(News).filter(News.id == id,
                                          News.user == current_user
                                          ).first()
        if news:
            form.title.data = news.title
            form.content.data = news.content
            form.is_private.data = news.is_private
        else:
            abort(404)
    if form.validate_on_submit():
        db_sess = db_session.create_session()
        news = db_sess.query(News).filter(News.id == id,
                                          News.user == current_user
                                          ).first()
        if news:
            news.title = form.title.data
            news.content = form.content.data
            news.is_private = form.is_private.data
            db_sess.commit()
            return redirect('/')
        else:
            abort(404)
    return render_template('news.html',
                           title='Редактирование новости',
                           form=form
                           )

@app.route('/news_delete/<int:id>', methods=['GET', 'POST'])
@login_required
def news_delete(id):
    db_sess = db_session.create_session()
    news = db_sess.query(News).filter(News.id == id,
                                      News.user == current_user
                                      ).first()
    if news:
        db_sess.delete(news)
        db_sess.commit()
    else:
        abort(404)
    return redirect('/')


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

@app.route('/pvp/room/<room>')
@login_required
def pvp_room(room):
    if room not in matches or current_user.id not in matches[room]['players']:
        abort(403)
    return render_template('Pvp.html') # cюда шаблончик бах

@socketio.on('join')
def on_join(data):
    room = data['room']
    join_room(room)
    emit('status', {'msg': f'{current_user.name} присоединился к комнате.'}, room=room)

@socketio.on('submit_code')
def on_submit(data):
    room = data['room']
    if room not in matches:
        return
    uid = str(current_user.id)
    if uid not in matches[room]['completed']:
        matches[room]['completed'][uid] = 0
    matches[room]['completed'][uid] += 1
    emit('update_scores', {
        'scores': matches[room]['completed']
    }, room=room)

if __name__ == '__main__':
    socketio.run(app, port=8025, host='127.0.0.1', allow_unsafe_werkzeug=True)