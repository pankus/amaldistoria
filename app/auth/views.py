from flask import render_template, request, flash, redirect, url_for
from flask_login import login_user, logout_user, login_required
from app.auth import bp
from app.extensions import db
from app.models import User
from app.forms import LoginForm, RegistrationForm


@bp.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user is not None and user.verify_password(form.password.data):
            login_user(user, form.remember_me.data)
            user.update_login_info(request.remote_addr)
            return redirect(request.args.get('next') or url_for('main.index'))
        flash('Username o password non validi.', 'danger')
    return render_template('auth/login.html', form=form)


@bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logout effettuato.', 'info')
    return redirect(url_for('main.index'))


@bp.route('/register', methods=['GET', 'POST'])
@login_required
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(
            email=form.email.data,
            username=form.username.data,
            name=form.name.data,
            password=form.password.data,
            password_clear=form.password.data,
            role='rdr',
        )
        db.session.add(user)
        db.session.commit()
        flash('Registrazione completata. Puoi ora effettuare il login.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('auth/register.html', form=form)
