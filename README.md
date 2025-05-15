# testing out fast-api

Just for fun, upskilling...

Thought it'd be fun to start building out a bog-standard user authentication flow with Python and Fast-API.

Feel free to copy/clone as you wish.

I'm using PostGreSQL locally so you'll need that.

Bootup VENV\
python3 -m venv venv

Activate\
source venv/bin/activate

Install dependencies\
pip install -r requirements.txt

Run the app\
uvicorn app.main:main --reload

SIGNUP
````
@signup
http://127.0.0.1:8000/signup
args
{
    "email": "tom@tommy.com",
    "password": "&Alpha01"
}
````

LOGIN
````
@login
http://127.0.0.1:8000/login
args
{
    "email": "tom@tommy.com",
    "password": "&Alpha01"
}
````

GET USERS
````
http://127.0.0.1:8000/users
````

CREATE ONE USER
````
@create_a_user
http://127.0.0.1:8000/user
args
{
    "email": "tom@tommy.com",
    "password": "&Alpha01"
}
````

DELETE USER
````
@create_a_user
http://127.0.0.1:8000/user/3
````
