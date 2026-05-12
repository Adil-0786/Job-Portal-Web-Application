from authlib.integrations.flask_client import OAuth

oauth = OAuth()


def init_oauth(app):
    oauth.init_app(app)
    client_id = app.config.get("GOOGLE_CLIENT_ID")
    client_secret = app.config.get("GOOGLE_CLIENT_SECRET")
    enabled = bool(client_id and client_secret)
    app.config["GOOGLE_OAUTH_ENABLED"] = enabled
    if not enabled:
        return

    oauth.register(
        name="google",
        client_id=client_id,
        client_secret=client_secret,
        server_metadata_url=app.config["GOOGLE_DISCOVERY_URL"],
        client_kwargs={"scope": "openid email profile"},
    )
