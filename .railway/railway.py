"""Railway Infrastructure as Code for this project.

Not read on deploy. Pushing to main redeploys using the settings already stored
on the service. Run `railway config plan` / `railway config apply` only when you
change something in this file (requires `pip install railway-sdk`).
"""

from railway_sdk import define_railway, github, project, service


@define_railway
def main(ctx=None):
    web = service(
        "vibecode",
        source=github("wwiens/vibecode", branch="main"),
        # Railway injects PORT; always bind to it rather than a fixed port.
        start="gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --access-logfile -",
        healthcheck="/health",
        healthcheckTimeout=60,
        # Restart policy defaults to ON_FAILURE; just cap the retries.
        deploy={"restartPolicyMaxRetries": 5},
        networking={
            "serviceDomains": {"vibecode-production-652a.up.railway.app": {}},
        },
    )
    return project("vibecode", resources=[web])
