"""
Central home for shared Flask extensions in AcxiomCRM.

Extensions are instantiated here without binding to a specific application instance.
They are subsequently initialized inside the application factory (create_app()) via .init_app().
This pattern avoids circular imports between the application factory and module blueprints.
"""

from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# CSRF protection extension for state-changing HTTP requests
csrf = CSRFProtect()

# Rate limiter extension using client remote IP address as the identifier.
# In-memory storage is used to keep the architecture simple without external dependencies like Redis.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri="memory://",
)
