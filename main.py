import datetime
import logging
import os
import time
import urllib
import flask
from flask import Flask, jsonify, session
import jwt
import requests

app = Flask(__name__)

APP_BASE_URI = 'https://lesson3.USERNAME.repl.co'
APP_CLIENT_ID = '4fa2099f-ae7d-4f92-8d4b-2a30b6043d84'
APP_SECRET = os.getenv('APP_SECRET')

AUTH_PROVIDER_BASE_URI = 'https://auth.dataporten.no'
AUTH_PROVIDER_NAME = 'Feide'
GROUPS_BASE_URI = 'https://groups-api.dataporten.no'
MY_GROUPS_PATH = 'groups/me/groups'

logger = logging.getLogger(__name__)

# Flask web framework configuration
# See http://flask.pocoo.org/docs/0.12/config/
app.config.update({
    'SECRET_KEY': 'flask_session_key',  # make sure to change this!!
    'JSONIFY_PRETTYPRINT_REGULAR': True,
    'PERMANENT_SESSION_LIFETIME': datetime.timedelta(minutes=1).total_seconds(),
})


def discover_feide_endpoints():
    discpoint = AUTH_PROVIDER_BASE_URI + "/.well-known/openid-configuration"
    logger.info("Discovering Feide endpoints at %s", discpoint)
    res = requests.get(discpoint)
    res.raise_for_status()
    return res.json()


oidcconfig = discover_feide_endpoints()
redirect_uri = APP_BASE_URI + '/redirect_uri'


def get_code():
    params = {
        'response_type': 'code',
        'client_id': APP_CLIENT_ID,
        'redirect_uri': redirect_uri,
        'scope': 'openid profile email userid-feide groups-edu groups-org groups-other',
    }
    authzpoint = oidcconfig['authorization_endpoint']
    logger.info("Redirecting to %s to authenticate and get authorization code", authzpoint)
    return flask.redirect(authzpoint + '?' + urllib.parse.urlencode(params))


def get_token():
    tokenpoint = oidcconfig['token_endpoint']
    code = flask.request.args.get('code')
    params = {
        'code': code,
        'grant_type': 'authorization_code',
        'redirect_uri': redirect_uri,
    }
    now = time.time()
    logger.info("Calling %s to get access token and ID token", tokenpoint)
    res = requests.post(tokenpoint, auth=(APP_CLIENT_ID, APP_SECRET), data=params)
    res.raise_for_status()
    token_response = res.json()
    access_token = token_response['access_token']
    scope = token_response['scope']
    logger.info("Got access_token %s with scope %s", access_token, scope)
    if token_response.get('id_token'):
        logger.info("Got id_token - YOU MUST VERIFY!")
    else:
        logger.info("Did not get id_token")
    session['access_token'] = token_response['access_token']
    session['id_token'] = token_response['id_token']
    session['expires_at'] = now + token_response['expires_in']


def get_userinfo(access_token):
    infopoint = oidcconfig['userinfo_endpoint']
    headers={"Authorization": f"Bearer {access_token}"}
    logger.info("Calling %s to get userinfo", infopoint)
    response = requests.get(infopoint, headers=headers)
    response.raise_for_status()
    return response.json()


def get_my_groups(access_token):
    headers={"Authorization": f"Bearer {access_token}"}
    response = requests.get(GROUPS_BASE_URI + '/' + MY_GROUPS_PATH, headers=headers)
    response.raise_for_status()
    return response.json()


def logged_in():
    return 'access_token' in session and session['expires_at'] > time.time()


@app.route('/')
def login():
    if not logged_in():
        return get_code()

    access_token = session['access_token']
    id_token = session['id_token']
    id_token_payload = jwt.decode(id_token, options={"verify_signature": False})
    userinfo = get_userinfo(access_token)
    mygroups = get_my_groups(access_token)
    return jsonify([
        {'access_token': access_token},
        {'id_token': id_token_payload},
        {'userinfo': userinfo},
        {'mygroups': mygroups}
    ])


@app.route('/redirect_uri')
def callback():
    logger.info('callback received')
    get_token()
    return flask.redirect('/')


@app.route('/logout')
def logout():
    if 'access_token' in session:
        session.pop('access_token')
    return "You've logged out"


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    discover_feide_endpoints()
    app.run(host='0.0.0.0', port=8080)
