from flask import render_template, redirect, url_for
from app import app
from app.forms import LoginForm

@app.route("/")
def route_home():
    return render_template("index.html")

@app.route("/login", methods=['GET', 'POST'])
def route_login():
    form = LoginForm()
    if form.validate_on_submit():
        print('Login from user {}, remember_me={}'.format(form.username.data, form.remember_me.data))
        return redirect("/")
    return render_template("login.html", title="Login", form=form)