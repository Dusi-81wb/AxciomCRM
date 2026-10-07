"""
Application Factory for AcxiomCRM.

This module implements the Flask application factory pattern via create_app().
In Phase 0, it:
1. Instantiates the Flask application.
2. Loads configuration settings.
3. Initializes core extensions (CSRFProtect, Limiter).
4. Initializes database connection teardown handlers.
5. Registers a minimal startup/health verification endpoint (/health).
6. Returns the configured Flask application instance.

No authentication or CRM business routes are registered in Phase 0.
"""

import os
from flask import Flask, jsonify, render_template
from config import config_by_name, DevelopmentConfig
from extensions import csrf, limiter
import database


def create_app(config_name=None, config_object=None):
    """
    Construct and configure the Flask application instance.

    :param config_name: String name of configuration ('development', 'testing', 'production').
    :param config_object: Optional configuration class directly passed (overrides config_name).
    :return: Configured Flask application instance.
    """
    app = Flask(__name__)

    # Load configuration
    if config_object is not None:
        app.config.from_object(config_object)
    elif config_name is not None and config_name in config_by_name:
        app.config.from_object(config_by_name[config_name])
    else:
        env = os.environ.get("FLASK_ENV", "development").lower()
        app.config.from_object(config_by_name.get(env, DevelopmentConfig))

    # Initialize shared extensions
    csrf.init_app(app)
    limiter.init_app(app)

    # Initialize database connection lifecycle
    database.init_app(app)

    # Initialize authentication security context processor
    import security.authentication as auth_security
    auth_security.init_app(app)

    # Register authentication blueprint (Phase 2)
    from routes.auth_routes import auth_bp
    app.register_blueprint(auth_bp)

    # Register customer management blueprint (Phase 5)
    from routes.customer_routes import customers_bp
    app.register_blueprint(customers_bp)

    # Register lead management & conversion blueprint (Phase 6)
    from routes.lead_routes import leads_bp
    app.register_blueprint(leads_bp)

    # Register opportunity management blueprint (Phase 7)
    from routes.opportunity_routes import opportunities_bp
    app.register_blueprint(opportunities_bp)


    # Phase 4 Centralized HTTP Error Handlers
    @app.errorhandler(400)
    def bad_request_error(error):
        return render_template("errors/400.html"), 400

    @app.errorhandler(401)
    def unauthorized_error(error):
        return render_template("errors/401.html"), 401

    @app.errorhandler(403)
    def forbidden_error(error):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found_error(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_server_error(error):
        return render_template("errors/500.html"), 500


    # Phase 0 Development/Startup Verification Endpoint
    # Simple verification route to confirm that the app factory and server start correctly.
    @app.route("/health", methods=["GET"])
    def health_check():
        """Development and startup verification endpoint."""
        return jsonify({
            "status": "healthy",
            "phase": "Phase 0 — Project Foundation",
            "message": "AcxiomCRM application factory initialized successfully."
        }), 200

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="127.0.0.1", port=5000)
