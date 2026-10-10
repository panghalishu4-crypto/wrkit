from flask import Flask, render_template, redirect, url_for, request, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from database import db, User, Novel, Chapter, Comment, LibraryItem

app = Flask(__name__)
app.config['SECRET_KEY'] = 'wrkit_super_secret_security_key_9988'
import os

# Render par PostgreSQL aur local PC par SQLite use karne ke liye setup
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///wrkit.db'

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    db.create_all()

@app.route('/')
@login_required
def home():
    filter_type = request.args.get('filter', 'trending')
    if filter_type == 'new':
        novels = Novel.query.order_by(Novel.id.desc()).all()
    elif filter_type == 'latest':
        novels = Novel.query.order_by(Novel.id.desc()).limit(10).all()
    elif filter_type in ['warewolf', 'vampire', 'mafia']:
        novels = Novel.query.filter(Novel.hashtag.ilike(f"%{filter_type}%")).all()
    else:
        novels = Novel.query.order_by(Novel.views.desc()).all()
    return render_template('home.html', novels=novels, active_filter=filter_type)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('home'))
        flash('Invalid username or password!')
    return render_template('login.html')

@app.route('/signup', methods=['POST'])
def signup():
    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    if User.query.filter_by(username=username).first():
        flash('Username already exists!')
        return redirect(url_for('login'))
    new_user = User(username=username, email=email)
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.commit()
    login_user(new_user)
    return redirect(url_for('home'))

@app.route('/novel/<int:novel_id>')
@login_required
def novel_detail(novel_id):
    novel = Novel.query.get_or_404(novel_id)
    chapters = Chapter.query.filter_by(novel_id=novel.id).order_by(Chapter.chapter_number).all()
    comments = Comment.query.filter_by(novel_id=novel.id).all()
    novel.views += 1
    db.session.commit()
    return render_template('description.html', novel=novel, chapters=chapters, comments=comments)

@app.route('/novel/<int:novel_id>/like', methods=['POST'])
@login_required
def like_novel(novel_id):
    novel = Novel.query.get_or_404(novel_id)
    novel.likes += 1
    # Add to library liked
    existing = LibraryItem.query.filter_by(user_id=current_user.id, novel_id=novel.id, type='liked').first()
    if not existing:
        db.session.add(LibraryItem(user_id=current_user.id, novel_id=novel.id, type='liked'))
    db.session.commit()
    return redirect(url_for('novel_detail', novel_id=novel_id))

@app.route('/novel/<int:novel_id>/save', methods=['POST'])
@login_required
def save_novel(novel_id):
    novel = Novel.query.get_or_404(novel_id)
    novel.saves += 1
    existing = LibraryItem.query.filter_by(user_id=current_user.id, novel_id=novel.id, type='saved').first()
    if not existing:
        db.session.add(LibraryItem(user_id=current_user.id, novel_id=novel.id, type='saved'))
    db.session.commit()
    return redirect(url_for('novel_detail', novel_id=novel_id))

@app.route('/novel/<int:novel_id>/comment', methods=['POST'])
@login_required
def add_comment(novel_id):
    text = request.form.get('comment_text')
    if text:
        comment = Comment(novel_id=novel_id, username=current_user.username, text=text)
        db.session.add(comment)
        db.session.commit()
    return redirect(url_for('novel_detail', novel_id=novel_id))

@app.route('/read/<int:chapter_id>')
@login_required
def read_chapter(chapter_id):
    chapter = Chapter.query.get_or_404(chapter_id)
    novel = Novel.query.get(chapter.novel_id)
    
    # Add to reading library
    existing = LibraryItem.query.filter_by(user_id=current_user.id, novel_id=novel.id, type='reading').first()
    if not existing:
        db.session.add(LibraryItem(user_id=current_user.id, novel_id=novel.id, type='reading'))
        db.session.commit()

    next_chapter = Chapter.query.filter(Chapter.novel_id == novel.id, Chapter.chapter_number == chapter.chapter_number + 1).first()
    comments = Comment.query.filter_by(novel_id=novel.id).all()
    similar_novels = Novel.query.filter(Novel.genre == novel.genre, Novel.id != novel.id).limit(3).all()
    return render_template('read.html', chapter=chapter, novel=novel, next_chapter=next_chapter, comments=comments, similar_novels=similar_novels)

@app.route('/search')
@login_required
def search():
    query = request.args.get('q', '')
    genre = request.args.get('genre', '')
    hashtag = request.args.get('hashtag', '')
    
    novels = Novel.query
    if query:
        novels = novels.filter((Novel.title.ilike(f"%{query}%")) | (Novel.hashtag.ilike(f"%{query}%")) | (Novel.genre.ilike(f"%{query}%")))
    if genre:
        novels = novels.filter(Novel.genre.ilike(f"%{genre}%"))
    if hashtag:
        novels = novels.filter(Novel.hashtag.ilike(f"%{hashtag}%"))
        
    results = novels.all()
    return render_template('search.html', novels=results, query=query)

@app.route('/write', methods=['GET', 'POST'])
@login_required
def write():
    if request.method == 'POST':
        title = request.form.get('title')
        writer = request.form.get('writer')
        genre = request.form.get('genre')
        hashtag = request.form.get('hashtag')
        description = request.form.get('description')
        chapter_title = request.form.get('chapter_title')
        content = request.form.get('content')
        status = request.form.get('status') # Continue (On Going) or Complete
        
        novel = Novel.query.filter_by(title=title).first()
        if not novel:
            novel = Novel(title=title, writer=writer, genre=genre, hashtag=hashtag, description=description, status=status)
            db.session.add(novel)
            db.session.commit()
        else:
            novel.status = status
            db.session.commit()
            
        existing_chapters_count = Chapter.query.filter_by(novel_id=novel.id).count()
        ch_num = existing_chapters_count + 1
        ch_title = chapter_title if chapter_title else f"Chapter {ch_num}"
        
        chapter = Chapter(novel_id=novel.id, chapter_number=ch_num, title=ch_title, content=content)
        db.session.add(chapter)
        db.session.commit()
        flash('Story published successfully!')
        return redirect(url_for('write'))
        
    my_novels = Novel.query.all()
    return render_template('write.html', my_novels=my_novels)

@app.route('/library')
@login_required
def library():
    tab = request.args.get('tab', 'reading')
    items = LibraryItem.query.filter_by(user_id=current_user.id, type=tab).all()
    return render_template('library.html', items=items, active_tab=tab)

@app.route('/library/delete/<int:item_id>')
@login_required
def delete_library_item(item_id):
    item = LibraryItem.query.get_or_404(item_id)
    if item.user_id == current_user.id:
        db.session.delete(item)
        db.session.commit()
    return redirect(url_for('library', tab=item.type))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'update':
            current_user.username = request.form.get('username')
            db.session.commit()
            flash('Profile updated successfully!')
        elif action == 'delete_account':
            db.session.delete(current_user)
            db.session.commit()
            logout_user()
            return redirect(url_for('login'))
    return render_template('profile.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)